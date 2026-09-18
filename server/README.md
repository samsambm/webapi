# Basket Watch API

The part that cannot live on the customer's phone. It holds the Anthropic key,
counts scans per user, and writes the anonymous price index.

Everything else — a user reading and writing their own receipts — goes straight
from the app to Supabase, where Row Level Security does the access control. That
keeps this service small: three routes, no ORM, no session state.

```
phone ──scan──►  this server  ──►  api.anthropic.com
  │                    │
  │                    └──────────►  Supabase (writes the rows)
  └──everything else──────────────►  Supabase (RLS: only your own rows)
```

## What it does with a photo

Reads it, and throws it away. The image is held in memory for the length of one
request and is never written to disk or to storage. Only the numbers survive.

## Routes

| | |
|---|---|
| `GET /health` | liveness, and which model is configured |
| `GET /me` | the caller's plan, scans used this month, and the upgrade link |
| `POST /scan` | multipart `image` → the parsed receipt, saved to their tables |
| `POST /billing/webhook` | flips a plan after a payment; guarded by a shared secret |

`/scan` returns `402` with `{"error": "quota_exhausted", "checkout_url": ...}` once
a free user is out of scans. The app turns that into an upgrade prompt.

## Setting it up

**1. Supabase** — create a project, then run `db/001_schema.sql` in the SQL editor.
Under Authentication → Providers, turn on Email, and Google if you want it
(Google sign-in will not work inside the Android WebView; it works on the web).

**2. Environment** — copy `.env.example` to `.env` and fill it in. The three keys
and where to find them:

| | |
|---|---|
| `SUPABASE_JWT_SECRET` | Settings → API → JWT Secret. Used to verify who is calling. |
| `SUPABASE_SERVICE_KEY` | Settings → API → `service_role`. Bypasses RLS — **server only, never in the app**. |
| `ANTHROPIC_API_KEY` | console.anthropic.com |

**3. Run it**

```bash
pip install -r server/requirements.txt
uvicorn server.app:app --reload            # with .env exported
```

**4. Deploy** — any container host:

```bash
gcloud run deploy basket-watch-api --source . --region europe-west1 --allow-unauthenticated
```

Set the same environment variables as secrets there. `--allow-unauthenticated`
means Cloud Run does not add its own auth layer; the service still refuses every
request without a valid Supabase token.

**5. Point the app at it** — rebuild the dashboard with the public values:

```bash
BW_API_URL=https://your-api.run.app \
BW_SUPABASE_URL=https://xxxx.supabase.co \
BW_SUPABASE_ANON_KEY=eyJ... \
python3 scripts/build_dashboard.py
```

The anon key is meant to be public — RLS is what protects the data, not the key.
With these unset the app has no account screen at all, which is the state the
repository is committed in.

## Testing it without any of that

```bash
server/test_server.sh
```

Runs the service in dev mode — no Supabase, no Anthropic, a canned receipt — and
checks the things that must not break: anonymous callers refused, five free scans
allowed and the sixth refused, an unsigned billing webhook rejected, a paid user
unblocked, a non-image refused.

## Payments

`/billing/webhook` takes one normalised shape, whatever the processor:

```json
{"email": "a@b.c", "plan": "pro", "status": "active",
 "renews_at": "2026-10-18T00:00:00Z", "provider": "...", "customer_id": "..."}
```

with the shared secret in `X-Billing-Secret`. Adding a provider means writing a
small adapter that receives its webhook and POSTs this — the app and the quota
logic never change. `CHECKOUT_URL` is the page the app opens when someone taps
Upgrade.

An Israeli processor (Grow, Cardcom, PayPlus) issues the חשבונית מס and handles
VAT; Stripe leaves both to you. That choice is the only thing still open.

## Costs

Every scan writes a `scan_events` row with the token counts and what it cost, so
spend per user is a query, not a guess:

```sql
select user_id, count(*), round(sum(cost_usd), 2) as usd
from scan_events where ok and created_at >= date_trunc('month', now())
group by user_id order by usd desc;
```
