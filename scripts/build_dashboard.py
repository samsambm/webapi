#!/usr/bin/env python3
"""Validate every receipt, then regenerate the dashboard.

    python3 scripts/build_dashboard.py            # validate + build
    python3 scripts/build_dashboard.py --check     # validate only, no write

Writes dashboard/index.html (open it in a browser) and dashboard/artifact.html
(the same page as a body fragment, for publishing as a Claude Artifact).
Exit code is non-zero when a receipt has a fatal problem.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import receipts as rc  # noqa: E402

ROOT = rc.ROOT
TEMPLATE = ROOT / "dashboard" / "template.html"
OUT_PAGE = ROOT / "dashboard" / "index.html"
OUT_FRAGMENT = ROOT / "dashboard" / "artifact.html"
# A build carrying an embedded API key is written here instead, never to
# index.html, because index.html is committed. local.html is gitignored.
OUT_LOCAL = ROOT / "dashboard" / "local.html"

PAGE_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="Spending, price trends and store-by-store comparison built from scanned receipts.">
<style>
  :root { color-scheme: light dark; padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); }
  body { margin: 0; }
  img { max-width: 100%; }
  [hidden] { display: none !important; }
</style>
</head>
<body>
"""
PAGE_TAIL = "\n</body>\n</html>\n"


def build_payload(loaded: rc.LoadResult) -> dict:
    rows = rc.flatten(loaded.receipts)
    cards = []
    for r in loaded.receipts:
        totals = r.get("totals", {})
        cards.append({
            "receipt_id": r.get("receipt_id"),
            "date": r.get("purchased_at", "")[:10],
            "merchant_slug": r.get("merchant", {}).get("slug", "unknown"),
            "merchant_name": r.get("merchant", {}).get("name", "Unknown"),
            "total": rc.money(totals.get("total", 0)),
            "items_count": totals.get("items_count") or len(r.get("items", [])),
            "vat_amount": rc.money(totals.get("vat_amount") or 0),
        })
    cards.sort(key=lambda c: c["date"], reverse=True)
    return {
        "rows": rows,
        "receipts": cards,
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "currency": (loaded.receipts[0].get("currency") if loaded.receipts else "ILS"),
            # Public configuration only. The anon key is designed to be shipped;
            # the service key and the Anthropic key live on the server alone.
            "cloud": {
                "api_url": os.environ.get("BW_API_URL", "").rstrip("/"),
                "supabase_url": os.environ.get("BW_SUPABASE_URL", "").rstrip("/"),
                "supabase_anon_key": os.environ.get("BW_SUPABASE_ANON_KEY", ""),
            },
            "scan_model": os.environ.get("BW_SCAN_MODEL", "claude-sonnet-5"),
            "category_labels": rc.CATEGORY_LABELS,
            "category_labels_he": rc.CATEGORY_LABELS_HE,
            "receipt_count": len(loaded.receipts),
            "last_date": max((c["date"] for c in cards), default=""),
        },
    }


def render(payload: dict) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    marker = "/*__DATA__*/ { rows: [], receipts: [], meta: {} }"
    if marker not in template:
        raise SystemExit("dashboard/template.html no longer contains the data placeholder")
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # Keep the JSON from ever closing the surrounding <script> element.
    blob = blob.replace("</", "<\\/")
    return template.replace(marker, blob)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="validate only, do not write the dashboard")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    loaded = rc.load_receipts()
    if not loaded.receipts:
        print("No receipts found in data/receipts/. Scan a bill first.", file=sys.stderr)
        return 1

    for problem in loaded.problems:
        print(problem, file=sys.stderr)
    if loaded.errors:
        print(f"\n{len(loaded.errors)} error(s) — fix the receipt JSON, nothing was written.", file=sys.stderr)
        return 1

    payload = build_payload(loaded)
    meta = payload["meta"]
    baked_key = os.environ.get("BW_ANTHROPIC_KEY", "").strip()
    if not args.check:
        fragment = render(payload)
        OUT_FRAGMENT.write_text(fragment, encoding="utf-8")
        OUT_PAGE.write_text(PAGE_HEAD + fragment + PAGE_TAIL, encoding="utf-8")
        if baked_key:
            # Same page, with the key in it. Kept out of git and out of CI so a
            # published APK can never carry it.
            keyed = dict(payload)
            keyed["meta"] = dict(payload["meta"], embedded_key=baked_key)
            OUT_LOCAL.write_text(PAGE_HEAD + render(keyed) + PAGE_TAIL, encoding="utf-8")
        elif OUT_LOCAL.exists():
            OUT_LOCAL.unlink()   # a stale keyed build must not outlive the key

    if not args.quiet:
        spend = sum(c["total"] for c in payload["receipts"])
        print(f"{meta['receipt_count']} receipt(s) · {len(payload['rows'])} line items · "
              f"spend {spend:,.2f} {meta['currency']}")
        if loaded.warnings:
            print(f"{len(loaded.warnings)} warning(s) above — worth a look, not blocking.")
        if args.check:
            print("--check: validation only, dashboard not rewritten.")
        else:
            print(f"wrote {OUT_PAGE.relative_to(ROOT)} and {OUT_FRAGMENT.relative_to(ROOT)}")
            if baked_key:
                print(f"wrote {OUT_LOCAL.relative_to(ROOT)} WITH AN EMBEDDED API KEY.")
                print("  Install that build yourself only. Anyone holding it holds your key,")
                print("  so never publish it, never commit it, never put it in a release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
