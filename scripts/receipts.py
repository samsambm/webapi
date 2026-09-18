"""Load, validate and normalise receipt JSON files.

Stdlib only. `jsonschema` is used when installed, otherwise the structural checks
below run on their own — they cover what actually breaks the dashboard.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "receipt.schema.json"
RECEIPT_DIRS = [ROOT / "data" / "receipts"]

CATEGORIES = [
    "produce", "bakery", "dairy_eggs", "meat_fish", "deli_prepared", "frozen",
    "pantry", "snacks_sweets", "beverages", "alcohol", "household",
    "personal_care", "baby", "pet", "other",
]

CATEGORY_LABELS = {
    "produce": "Produce", "bakery": "Bakery", "dairy_eggs": "Dairy & eggs",
    "meat_fish": "Meat & fish", "deli_prepared": "Deli & prepared", "frozen": "Frozen",
    "pantry": "Pantry", "snacks_sweets": "Snacks & sweets", "beverages": "Beverages",
    "alcohol": "Alcohol", "household": "Household", "personal_care": "Personal care",
    "baby": "Baby", "pet": "Pet", "other": "Other",
}

CATEGORY_LABELS_HE = {
    "produce": "פירות וירקות", "bakery": "מאפים", "dairy_eggs": "חלב וביצים",
    "meat_fish": "בשר ודגים", "deli_prepared": "סלטים ומוכן", "frozen": "קפואים",
    "pantry": "מזווה", "snacks_sweets": "חטיפים ומתוקים", "beverages": "משקאות",
    "alcohol": "אלכוהול", "household": "מוצרי בית", "personal_care": "טיפוח",
    "baby": "תינוקות", "pet": "חיות מחמד", "other": "אחר",
}

UNITS = {"each", "kg", "g", "l", "ml"}

# Package size -> base unit for per-kg / per-litre comparison.
TO_BASE = {"g": ("kg", 0.001), "kg": ("kg", 1.0), "ml": ("l", 0.001), "l": ("l", 1.0)}


@dataclass
class Problem:
    receipt: str
    where: str
    message: str
    fatal: bool = True

    def __str__(self) -> str:
        mark = "ERROR" if self.fatal else "warn "
        return f"  {mark}  {self.receipt}  {self.where}: {self.message}"


@dataclass
class LoadResult:
    receipts: list = field(default_factory=list)
    problems: list = field(default_factory=list)

    @property
    def errors(self):
        return [p for p in self.problems if p.fatal]

    @property
    def warnings(self):
        return [p for p in self.problems if not p.fatal]


def slugify(text: str) -> str:
    """Slug that survives Hebrew: keeps letters/digits, collapses everything else."""
    text = unicodedata.normalize("NFKC", (text or "").strip().lower())
    out = re.sub(r"[^\w֐-׿]+", "-", text, flags=re.UNICODE)
    return out.strip("-") or "unknown"


def money(value) -> float:
    return round(float(value), 2)


def _check_arithmetic(r: dict, rid: str, problems: list) -> None:
    for item in r.get("items", []):
        line = item.get("line", "?")
        where = f"items[line {line}]"
        try:
            expected = round(float(item["quantity"]) * float(item["unit_price"]), 2)
        except (KeyError, TypeError, ValueError):
            continue
        actual = float(item.get("total", 0))
        discount = float(item.get("discount") or 0)
        if abs(expected - discount - actual) > 0.02:
            problems.append(Problem(
                rid, where,
                f"quantity x unit_price = {expected:.2f} but total = {actual:.2f}. "
                "On a weighed line the big number is the price per kg — check it is not swapped.",
            ))

    totals = r.get("totals", {})
    if "total" in totals and r.get("items"):
        line_sum = round(sum(float(i.get("total", 0)) for i in r["items"]), 2)
        stated = float(totals["total"])
        slack = abs(float(totals.get("discount_total") or 0)) + 0.05
        if abs(line_sum - stated) > slack:
            problems.append(Problem(
                rid, "totals.total",
                f"line totals sum to {line_sum:.2f}, receipt says {stated:.2f}",
            ))
    count = totals.get("items_count")
    if count is not None and r.get("items") and int(count) != len(r["items"]):
        problems.append(Problem(
            rid, "totals.items_count",
            f"printed count is {count} but {len(r['items'])} lines were captured",
            fatal=False,
        ))
    # On Israeli receipts `חייב מע"מ` is the pre-VAT taxable base, so the identity is
    # taxable base + VAT + exempt = total.
    taxable, exempt, vat = totals.get("vat_taxable"), totals.get("vat_exempt"), totals.get("vat_amount")
    if None not in (taxable, exempt, vat) and "total" in totals:
        if abs(float(taxable) + float(vat) + float(exempt) - float(totals["total"])) > 0.05:
            problems.append(Problem(
                rid, "totals",
                "vat_taxable + vat_amount + vat_exempt does not equal total", fatal=False))
    if taxable is not None and vat is not None and totals.get("vat_rate"):
        if abs(float(taxable) * float(totals["vat_rate"]) - float(vat)) > 0.05:
            problems.append(Problem(
                rid, "totals.vat_amount",
                f"{float(vat):.2f} is not {totals['vat_rate']:.0%} of the taxable base", fatal=False))


def _check_structure(r: dict, rid: str, path: Path, problems: list) -> None:
    for key in ("schema_version", "receipt_id", "merchant", "purchased_at", "currency", "items", "totals"):
        if key not in r:
            problems.append(Problem(rid, key, "required field is missing"))
    if r.get("receipt_id") and r["receipt_id"] != path.stem:
        problems.append(Problem(
            rid, "receipt_id", f"does not match the filename ({path.stem})", fatal=False))
    if "slug" not in r.get("merchant", {}):
        problems.append(Problem(rid, "merchant.slug", "required — comparisons group on it"))
    try:
        datetime.fromisoformat(r.get("purchased_at", ""))
    except ValueError:
        problems.append(Problem(rid, "purchased_at", "not an ISO 8601 date-time"))
    for item in r.get("items", []):
        where = f"items[line {item.get('line', '?')}]"
        if item.get("category") not in CATEGORIES:
            problems.append(Problem(rid, where, f"unknown category {item.get('category')!r}"))
        if item.get("unit") not in UNITS:
            problems.append(Problem(rid, where, f"unknown unit {item.get('unit')!r}"))
        if float(item.get("quantity", 0)) <= 0:
            problems.append(Problem(rid, where, "quantity must be greater than zero"))
    last4 = (r.get("payment") or {}).get("card_last4")
    if last4 and not re.fullmatch(r"\d{4}", str(last4)):
        problems.append(Problem(rid, "payment.card_last4", "store the last 4 digits only"))


def _jsonschema_check(r: dict, rid: str, problems: list) -> None:
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for err in validator.iter_errors(r):
        where = "/".join(str(p) for p in err.absolute_path) or "(root)"
        problems.append(Problem(rid, where, err.message))


def load_receipts() -> LoadResult:
    result = LoadResult()
    seen: dict[str, Path] = {}
    for directory in RECEIPT_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            rid = path.stem
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                result.problems.append(Problem(rid, "(file)", f"invalid JSON: {exc}"))
                continue
            _check_structure(data, rid, path, result.problems)
            _check_arithmetic(data, rid, result.problems)
            _jsonschema_check(data, rid, result.problems)
            key = data.get("receipt_id", rid)
            if key in seen:
                result.problems.append(Problem(
                    rid, "receipt_id", f"duplicate of {seen[key].name}"))
            seen[key] = path
            result.receipts.append(data)
    result.receipts.sort(key=lambda r: r.get("purchased_at", ""))
    return result


def product_key(item: dict) -> str:
    """Identity used to follow one product across receipts and stores."""
    barcode = (item.get("barcode") or "").strip()
    # Internal PLUs are store-specific, so only real barcodes (8+ digits) join across stores.
    if barcode and len(barcode) >= 8 and barcode.isdigit():
        return f"ean:{barcode}"
    return f"name:{slugify(item.get('name', ''))}"


def base_price(item: dict):
    """(price, unit) on a comparable basis: per kg, per litre, or per item."""
    unit, qty, unit_price = item.get("unit"), float(item["quantity"]), float(item["unit_price"])
    if unit in TO_BASE:
        base, factor = TO_BASE[unit]
        return round(unit_price / factor if base != unit else unit_price, 4), base
    size = item.get("size")
    if size and size.get("unit") in TO_BASE and float(size.get("value") or 0) > 0:
        base, factor = TO_BASE[size["unit"]]
        amount = float(size["value"]) * factor
        if amount > 0:
            return round(unit_price / amount, 4), base
    return round(unit_price, 4), "each"


def base_quantity(item: dict) -> float:
    """Amount bought expressed in the item's base unit (kg, litres or pieces)."""
    unit, qty = item.get("unit"), float(item["quantity"])
    if unit in TO_BASE:
        _, factor = TO_BASE[unit]
        return round(qty * factor, 4)
    size = item.get("size")
    if size and size.get("unit") in TO_BASE and float(size.get("value") or 0) > 0:
        _, factor = TO_BASE[size["unit"]]
        return round(qty * float(size["value"]) * factor, 4)
    return round(qty, 4)


def flatten(receipts: list) -> list:
    """One row per purchased line, with everything the dashboard aggregates on."""
    rows = []
    for r in receipts:
        merchant = r.get("merchant", {})
        bought = r.get("purchased_at", "")
        for item in r.get("items", []):
            price, unit = base_price(item)
            rows.append({
                "receipt_id": r.get("receipt_id"),
                "date": bought[:10],
                "month": bought[:7],
                "merchant_slug": merchant.get("slug", "unknown"),
                "merchant_name": merchant.get("name", "Unknown"),
                "line": item.get("line"),
                "barcode": item.get("barcode"),
                "name": item.get("name", ""),
                "name_en": item.get("name_en") or "",
                "category": item.get("category", "other"),
                "quantity": round(float(item["quantity"]), 3),
                "unit": item.get("unit"),
                "unit_price": money(item["unit_price"]),
                "total": money(item.get("total", 0)),
                "product_key": product_key(item),
                "base_price": price,
                "base_qty": base_quantity(item),
                "base_unit": unit,
                "confidence": item.get("confidence"),
            })
    return rows
