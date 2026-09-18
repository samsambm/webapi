# Working in this repo

Bill scanning → receipt JSON → spending dashboard. See README.md for the shape of it.

- **Scanning a bill**: follow `.claude/skills/bill-scanner/SKILL.md`. Never invent a value
  that is unreadable on the photo — flag it with a low `confidence` and a note instead. A
  guessed price becomes a fake price trend that nobody will catch later.
- **`dashboard/index.html` and `dashboard/artifact.html` are generated.** Edit
  `dashboard/template.html`, then run `python3 scripts/build_dashboard.py`.
- **Always rebuild after touching `data/`** — the build validates every receipt and fails
  loudly rather than writing a dashboard from broken data.
- **Comparisons must stay like-for-like**: normalise to per kg / per litre / per item, and
  only compare a product with itself at the same store when showing a price *trend*.
- **The page has three screens** (dashboard / scan / ask) and two languages. Every piece
  of UI text goes through `t()` and lives in the `I18N` table in `dashboard/template.html`
  — add both `en` and `he` when you add a string, and use CSS logical properties
  (`margin-inline`, `text-align: start`) so the Hebrew layout keeps mirroring.
- **Never invent an exchange rate.** Amounts are recorded in shekels; another currency is
  shown only once the viewer supplies a rate.
- The scan and ask screens need Artifact runtime capabilities (`sample`, `db`, `assets`,
  `downloads`), so they only work in the published artifact. They must degrade to a clear
  note when `window.claude` is absent — `dashboard/index.html` has to stay useful offline.
- `flattenReceipt`/`basePrice`/`baseQty` in the template mirror `scripts/receipts.py`. If
  you change the normalisation in one, change it in the other or the two disagree.
- Python is stdlib-only by design; `jsonschema` is used if present but never required. Keep
  it that way so the repo runs anywhere.
- Never commit full card numbers or EMV data. Last 4 digits only.
