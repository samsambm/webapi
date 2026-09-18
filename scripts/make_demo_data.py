#!/usr/bin/env python3
"""Generate clearly-marked synthetic receipts into data/demo/.

Every file it writes carries "demo": true and the dashboard badges them. They exist so
the comparison and trend views have something to show before you have scanned a few
months of real bills. Delete data/demo/ whenever you want; nothing depends on it.

Deterministic: same seed in, same files out.
"""
from __future__ import annotations

import json
import random
import shutil
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "demo"

MERCHANTS = [
    {"slug": "family-market", "name": 'י.א. פמילי מרקט בע"מ', "name_en": "Y.A. Family Market Ltd",
     "branch": "ניצני עוז", "tax_id": "515847747", "level": 1.00},
    {"slug": "rami-levy", "name": "רמי לוי שיווק השקמה", "name_en": "Rami Levy",
     "branch": "נתניה", "tax_id": "512534303", "level": 0.88},
    {"slug": "shufersal", "name": "שופרסל שלי", "name_en": "Shufersal Sheli",
     "branch": "כפר יונה", "tax_id": "520022732", "level": 1.07},
]

# (barcode, name, name_en, category, unit, base price, size) — base price is the
# September price at family-market; other stores and earlier months move off it.
CATALOG = [
    ("7290013558718", "פטריות שמפניון א.א 300", "Champignon mushrooms 300g", "produce", "each", 11.90, {"value": 300, "unit": "g"}),
    ("4066600999614", 'פאולנר בקבוק זכ\' 500 מ"ל', "Paulaner bottle 500ml", "alcohol", "each", 12.90, {"value": 500, "unit": "ml"}),
    ("7290112498915", "מאגדת מיני מגנום שקדים", "Mini Magnum almond multipack", "frozen", "each", 34.90, None),
    ("7290000537566", "נקניקיות עוף 400 גרם", "Chicken sausages 400g", "meat_fish", "each", 15.90, {"value": 400, "unit": "g"}),
    ("7290011462000", "חומוס ביתי /מטבחה/ירושל", "Home-style hummus", "deli_prepared", "each", 12.90, None),
    ("7290000554532", "צפתית מעודנת 5%", "Tzfatit cheese, light 5%", "dairy_eggs", "each", 18.90, None),
    ("14033", "בצל יבש ישראל", "Dry onion, Israel", "produce", "kg", 6.90, None),
    ("122269", "קבב הבית", "House kebab", "meat_fish", "kg", 64.90, None),
    ("654959", "עמק תנובה ישראל", "Emek cheese, Tnuva", "dairy_eggs", "kg", 52.85, None),
    ("100103", "בגט", "Baguette", "bakery", "each", 5.90, None),
    ("7290004131074", "חלב תנובה 3% ליטר", "Tnuva milk 3% 1L", "dairy_eggs", "each", 6.60, {"value": 1, "unit": "l"}),
    ("7290000066318", "ביצים L תבנית 12", "Eggs L, tray of 12", "dairy_eggs", "each", 16.40, None),
    ("7290004720018", "קוטג' תנובה 5%", "Cottage cheese 5%", "dairy_eggs", "each", 7.90, None),
    ("7290110114923", "עגבניות שרי 250 גרם", "Cherry tomatoes 250g", "produce", "each", 8.90, {"value": 250, "unit": "g"}),
    ("14201", "מלפפון", "Cucumber", "produce", "kg", 7.40, None),
    ("14210", "עגבניות", "Tomatoes", "produce", "kg", 6.20, None),
    ("7290008757775", "שניצל עוף טרי", "Fresh chicken schnitzel", "meat_fish", "kg", 44.90, None),
    ("7290102393916", "אורז בסמטי 1 ק\"ג", "Basmati rice 1kg", "pantry", "each", 14.50, {"value": 1, "unit": "kg"}),
    ("7290000208831", "שמן זית 750 מ\"ל", "Olive oil 750ml", "pantry", "each", 39.90, {"value": 750, "unit": "ml"}),
    ("7290103992873", "נייר טואלט 32 גליל", "Toilet paper, 32 rolls", "household", "each", 49.90, None),
    ("7290000119946", "במבה אסם 80 גרם", "Bamba 80g", "snacks_sweets", "each", 4.90, {"value": 80, "unit": "g"}),
    ("7290019049920", "קולה זירו 1.5 ליטר", "Cola Zero 1.5L", "beverages", "each", 8.40, {"value": 1.5, "unit": "l"}),
]

MONTHLY_DRIFT = 0.006  # ~0.6% a month, so a six-month history shows a visible trend


def price_for(product, merchant, months_before_now, rng):
    base = product[5] * merchant["level"]
    drifted = base / ((1 + MONTHLY_DRIFT) ** months_before_now)
    jitter = rng.uniform(-0.03, 0.03)
    promo = 0.82 if rng.random() < 0.08 else 1.0
    return round(drifted * (1 + jitter) * promo, 2)


def build(seed: int = 20260918) -> list:
    rng = random.Random(seed)
    today = datetime(2026, 9, 18)
    written = []
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    # Two shops a month for six months, rotating the store.
    trips = []
    for months_back in range(6, 0, -1):
        for which in (0, 1):
            day = 4 + which * 14 + rng.randint(0, 3)
            when = (today.replace(day=1) - timedelta(days=30 * (months_back - 1))).replace(day=1)
            when = when.replace(day=min(day, 27), hour=rng.choice([9, 11, 17, 19]), minute=rng.choice([5, 14, 27, 44, 52]))
            if when > today:  # never generate a shop in the future
                continue
            trips.append((when, MERCHANTS[(months_back + which) % len(MERCHANTS)], months_back))

    for index, (when, merchant, months_back) in enumerate(trips):
        basket = rng.sample(CATALOG, rng.randint(7, 12))
        items, total = [], 0.0
        for line, product in enumerate(basket, start=1):
            barcode, name, name_en, category, unit, _, size = product
            unit_price = price_for(product, merchant, months_back, rng)
            qty = round(rng.uniform(0.25, 1.4), 3) if unit == "kg" else float(rng.choice([1, 1, 1, 2]))
            line_total = round(qty * unit_price, 2)
            total += line_total
            items.append({
                "line": line, "barcode": barcode, "name": name, "name_en": name_en,
                "category": category, "quantity": qty, "unit": unit,
                "unit_price": unit_price, "total": line_total, "size": size,
                "discount": None, "vat_exempt": False, "confidence": 0.95, "notes": None,
            })
        total = round(total, 2)
        vat_rate = 0.18
        taxable = round(total / (1 + vat_rate), 2)
        doc = f"D{index + 1:04d}{when.strftime('%m%d')}"
        receipt_id = f"{when:%Y-%m-%d}_{merchant['slug']}_{doc}"
        payload = {
            "schema_version": "1.0",
            "receipt_id": receipt_id,
            "demo": True,
            "source_image": None,
            "scanned_at": when.isoformat(timespec="seconds"),
            "merchant": {
                "name": merchant["name"], "name_en": merchant["name_en"], "slug": merchant["slug"],
                "branch": merchant["branch"], "tax_id": merchant["tax_id"], "phone": None, "address": None,
            },
            "document": {"type": "invoice_receipt", "number": doc, "is_copy": False, "register": "1"},
            "purchased_at": when.isoformat(timespec="minutes"),
            "currency": "ILS",
            "items": items,
            "totals": {
                "items_count": len(items), "subtotal": total, "discount_total": 0, "total": total,
                "vat_rate": vat_rate, "vat_amount": round(total - taxable, 2),
                "vat_taxable": taxable, "vat_exempt": 0,
            },
            "payment": {"method": "credit", "amount": total, "change": 0, "card_brand": "ויזה כאל",
                        "card_last4": "7462", "terminal": "2656917", "auth_code": None},
            "review": {"overall_confidence": 1.0, "needs_human_check": [],
                       "notes": "Synthetic demo receipt generated by scripts/make_demo_data.py — not a real purchase."},
        }
        path = OUT / f"{receipt_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    files = build()
    print(f"wrote {len(files)} demo receipts to {OUT.relative_to(ROOT)}/")
