---
name: bill-scanner
description: Turn a photo, PDF or screenshot of a bill/receipt/invoice into a validated receipt JSON file in data/receipts/, then rebuild the spending dashboard. Use whenever the user shares a receipt or bill image, says "scan this bill/receipt", asks to log a purchase, or asks to update their spending dashboard. Handles Hebrew (RTL) supermarket receipts and ILS/VAT layouts.
---

# Bill scanner

Read a bill image, write one JSON file per receipt, rebuild the dashboard. Accuracy
first: this data feeds price comparisons, so a mis-read digit becomes a fake price
trend that is hard to spot later.

## Steps

1. **Read the image** with the Read tool. If the user gave several photos of one long
   receipt, read them all before writing anything — items continue across photos.
2. **Transcribe every line exactly as printed.** Keep Hebrew as-is, do not translate
   in place, do not tidy spelling or expand abbreviations. Put your best-effort
   English in `name_en`; that field is for charts and search only.
3. **Write the file** to `data/receipts/<YYYY-MM-DD>_<merchant-slug>_<doc number>.json`
   following `schema/receipt.schema.json`. Reuse the merchant `slug` an existing
   receipt already uses for the same store — comparisons group on it.
4. **Validate and rebuild**: `python3 scripts/build_dashboard.py`. It checks the file
   against the schema and the arithmetic, then regenerates `dashboard/index.html`.
   Fix anything it reports; never hand-edit the generated dashboard.
5. **Report** the total, the item count, and every field you flagged as uncertain.

## Reading rules that matter

- **Weighed lines take two printed rows.** A name row, then `0.321 X 6.90` with the
  line total. That is `quantity: 0.321, unit: "kg", unit_price: 6.90` — the big number
  is price *per kg*, not what was paid. Getting this backwards is the most common and
  most damaging error, because it poisons per-kg comparisons.
- **Hebrew receipts print right-to-left**, so a row reads: total (leftmost), name,
  barcode/PLU (rightmost). Digits inside the row still read left-to-right.
- **Repeated identical lines are separate items.** Keep them as separate lines with the
  same barcode; quantity stays 1 each. The dashboard sums them.
- **Never invent a barcode.** Internal PLUs (4–6 digits) are fine to record as printed;
  if no code is printed, use `null`.
- **Keep the printed total.** If your line totals do not sum to it, do not "fix" a line
  to force a match — re-read the photo, and if it is genuinely unreadable say so and
  record the line with `confidence` below 0.5 plus a note.
- **Card numbers: last 4 digits only.** Never store a full PAN, and never store the
  UID/RRN/AID EMV blocks — they are not useful here.
- **Set `confidence` honestly** per item (below 0.8 = creased, blurred or ambiguous) and
  list those paths in `review.needs_human_check`.

## Currency, VAT, dates

- Israeli receipts: `currency: "ILS"`, VAT (`מע"מ`) is usually 18% in 2026. Record
  `vat_amount`, `vat_taxable` and `vat_exempt` exactly as printed — do not recompute.
- Dates print as `DD/MM/YYYY`. `18/09/2026` is 18 September, never 9 September.
- `לתשלום` = amount to pay, `סה"כ`/`סכום` = total, `עודף` = change, `פריטים` = items.

## Category list

Use exactly one of: `produce`, `bakery`, `dairy_eggs`, `meat_fish`, `deli_prepared`,
`frozen`, `pantry`, `snacks_sweets`, `beverages`, `alcohol`, `household`,
`personal_care`, `baby`, `pet`, `other`. See `references/hebrew-receipts.md` for the
Hebrew keyword → category mapping and a glossary of printed receipt terms.

## Non-grocery bills

Utility, telecom and restaurant bills fit the same schema: one `items` entry per charge
line, `unit: "each"`, `category: "other"` unless a better one applies. Keep the billing
period in `document.number` or `review.notes` so it is not lost.
