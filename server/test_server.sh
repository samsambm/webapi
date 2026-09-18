#!/usr/bin/env bash
# Smoke test against a dev-mode server: quota, upgrade, and the refusals.
# Usage: server/test_server.sh [port]
set -euo pipefail
PORT="${1:-8799}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMG="$ROOT/data/images/2026-09-18_family-market_1005071700.jpg"

BW_DEV=1 BILLING_WEBHOOK_SECRET=test-secret CHECKOUT_URL=https://pay.example.com \
  python3 -m uvicorn server.app:app --port "$PORT" --log-level warning &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
for _ in $(seq 20); do curl -sf "http://127.0.0.1:$PORT/health" >/dev/null && break; sleep 0.5; done

fail() { echo "FAIL: $1"; exit 1; }
code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
scan() { curl -s -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:$PORT/scan" \
           -H "Authorization: Bearer dev" -F "image=@$IMG;type=image/jpeg"; }

[ "$(code "http://127.0.0.1:$PORT/me")" = 401 ] || fail "/me allowed an anonymous caller"
[ "$(code -H 'Authorization: Bearer dev' "http://127.0.0.1:$PORT/me")" = 200 ] || fail "/me refused the dev token"

for i in 1 2 3 4 5; do [ "$(scan)" = 200 ] || fail "free scan $i was refused"; done
[ "$(scan)" = 402 ] || fail "the 6th free scan was allowed"

[ "$(code -X POST -H 'content-type: application/json' -d '{"email":"dev@example.com","plan":"pro"}' \
     "http://127.0.0.1:$PORT/billing/webhook")" = 401 ] || fail "the webhook accepted a missing secret"
curl -sf -X POST "http://127.0.0.1:$PORT/billing/webhook" -H "content-type: application/json" \
  -H "X-Billing-Secret: test-secret" \
  -d '{"email":"dev@example.com","plan":"pro","status":"active"}' >/dev/null || fail "the upgrade webhook failed"
[ "$(scan)" = 200 ] || fail "a paid user was still blocked"

echo "not an image" > /tmp/bw-not-an-image.txt
[ "$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$PORT/scan" \
     -H "Authorization: Bearer dev" -F "image=@/tmp/bw-not-an-image.txt;type=text/plain")" = 400 ] \
  || fail "a text file was accepted as a receipt"

echo "all server checks passed"
