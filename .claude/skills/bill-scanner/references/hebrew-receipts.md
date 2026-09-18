# Hebrew receipt reference

## Printed terms

| Hebrew | Meaning |
|---|---|
| חשבונית מס / קבלה | Tax invoice / receipt |
| העתק | Copy (reprint, not a second purchase — set `document.is_copy: true`) |
| ח.פ / ע.מ | Company / dealer tax id |
| תאריך קניה | Purchase date |
| ברקוד | Barcode |
| שם פריט | Item name |
| סכום | Amount |
| פריטים | Items (the count line, e.g. `16 פריטים`) |
| לתשלום | To pay (the grand total) |
| מע"מ | VAT |
| חייב מע"מ | VAT-taxable portion |
| פטור מע"מ | VAT-exempt portion |
| תשלום / אשראי / מזומן | Payment / credit / cash |
| עודף | Change |
| ק"ג | kg |
| מבצע / הנחה | Promotion / discount |
| זיכוי | Credit (negative line — record `total` as a negative number) |

## Weighed-goods block

```
בצל יבש ישראל          14033
2.21        0.321 X 6.90
```

→ `quantity: 0.321, unit: "kg", unit_price: 6.90, total: 2.21`.
Sanity check every weighed line: `round(quantity * unit_price, 2)` must equal `total`
within ±0.02 (registers round differently). `build_dashboard.py` enforces this.

## Category keywords

| Category | Hebrew cues |
|---|---|
| produce | ירקות, פירות, בצל, עגבני, מלפפון, תפוח, בננה, פטריות, גזר, סלט (raw) |
| bakery | לחם, בגט, לחמניה, פיתה, חלה, מאפה, בורקס |
| dairy_eggs | חלב, גבינה, צפתית, קוטג', יוגורט, שמנת, חמאה, ביצים, עמק, תנובה, טרה |
| meat_fish | עוף, בשר, קבב, נקניקיות, שניצל, אמנון, סלמון, דג, כבד, הודו |
| deli_prepared | חומוס, טחינה, מטבחה, סלטים מוכנים, מוכן |
| frozen | קפוא, גלידה, מגנום, שלגון, אפונה קפואה |
| pantry | סוכר, קמח, אורז, פסטה, שמן, מלח, קופסת שימורים, רוטב, קטשופ |
| snacks_sweets | חטיף, במבה, ביסלי, שוקולד, עוגיות, גרעינים, אגוזים |
| beverages | מים, קולה, מיץ, סודה, תה, קפה, משקה |
| alcohol | בירה, יין, וודקה, ויסקי, ערק, פאולנר, ריגל, קרלסברג |
| household | ניקוי, אקונומיקה, נייר טואלט, מגבונים, שקיות, סבון כלים |
| personal_care | שמפו, משחת שיניים, דאודורנט, תחבושות, קרם |
| baby | חיתולים, מטרנה, מגבוני תינוק |
| pet | חתול, כלב, מזון לחיות |
| other | כללי, פיקדון, שקית, unreadable lines |

`כללי` ("general") is a generic register key — always `other`, and say so in the item
`notes` so it is obvious later why the line has no product name.

## Deposit and bag lines

`פיקדון` (bottle deposit) and `שקית` (bag) are real charges: record them as items in
`other`, never fold them into another line.
