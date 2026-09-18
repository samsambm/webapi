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
- Python is stdlib-only by design; `jsonschema` is used if present but never required. Keep
  it that way so the repo runs anywhere.
- Never commit full card numbers or EMV data. Last 4 digits only.
