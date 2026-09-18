"""Basket Watch API — the one piece that must not run on the customer's phone.

It exists for three reasons:
  1. It holds the Anthropic API key. An app can be unpacked; a server cannot.
  2. It counts scans per user, so one person cannot run up the bill.
  3. It writes the anonymous price index, which no client should be trusted with.

Everything else — reading and writing a user's own receipts — goes straight from
the app to Supabase, where Row Level Security does the access control.

Run locally:   BW_DEV=1 uvicorn server.app:app --reload
Deploy:        any container host; see server/README.md
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))                       # so `auth` resolves however uvicorn is invoked
sys.path.insert(0, str(_HERE.parent / "scripts"))    # the normalisation the dashboard already uses

import receipts as rc  # noqa: E402
from auth import AuthError, verify  # noqa: E402

# --------------------------------------------------------------------- config
DEV = os.environ.get("BW_DEV") == "1"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BILLING_SECRET = os.environ.get("BILLING_WEBHOOK_SECRET", "")
CHECKOUT_URL = os.environ.get("CHECKOUT_URL", "")
MODEL = os.environ.get("SCAN_MODEL", "claude-sonnet-5")
FREE_SCANS = int(os.environ.get("FREE_SCANS_PER_MONTH", "5"))
PRO_SCANS = int(os.environ.get("PRO_SCANS_PER_MONTH", "1000"))  # a ceiling against runaway use, not a product limit
MAX_IMAGE_BYTES = int(os.environ.get("MAX_IMAGE_BYTES", str(8 * 1024 * 1024)))
ALLOWED_ORIGINS = [o for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o]

# $ per million tokens, so a scan's real cost lands in the telemetry.
PRICES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

app = FastAPI(title="Basket Watch API", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["authorization", "content-type"],
)

_dev_state: dict = {"profiles": {}, "scans": [], "receipts": []}

SCAN_PROMPT = (Path(__file__).resolve().parent / "scan_prompt.txt").read_text(encoding="utf-8")


# ------------------------------------------------------------------ helpers
def current_user(authorization: str | None) -> dict:
    """Identify the caller, or refuse. Never falls through to an anonymous user."""
    token = (authorization or "").removeprefix("Bearer ").strip()
    if DEV and token == "dev":
        return {"id": "00000000-0000-0000-0000-000000000001", "email": "dev@example.com"}
    try:
        claims = verify(token, JWT_SECRET)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"id": claims["sub"], "email": claims.get("email")}


async def sb(method: str, path: str, **kwargs) -> list | dict:
    """Call Supabase with the service key. Every caller passes an explicit user_id."""
    if DEV:
        raise RuntimeError("supabase is not called in dev mode")
    headers = {
        "apikey": SERVICE_KEY,
        "authorization": f"Bearer {SERVICE_KEY}",
        "content-type": "application/json",
        "prefer": kwargs.pop("prefer", "return=representation"),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.request(method, f"{SUPABASE_URL}/rest/v1{path}", headers=headers, **kwargs)
    if res.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"database said {res.status_code}: {res.text[:300]}")
    return res.json() if res.content else []


async def get_profile(user: dict) -> dict:
    if DEV:
        return _dev_state["profiles"].setdefault(
            user["id"], {"id": user["id"], "email": user["email"], "plan": "free", "plan_status": "active"})
    rows = await sb("GET", f"/profiles?id=eq.{user['id']}&select=*")
    if rows:
        return rows[0]
    created = await sb("POST", "/profiles", json={"id": user["id"], "email": user["email"]})
    return created[0] if created else {"id": user["id"], "plan": "free", "plan_status": "active"}


async def scans_used(user_id: str) -> int:
    if DEV:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        return sum(1 for s in _dev_state["scans"] if s["user_id"] == user_id and s["ok"] and s["month"] == month)
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    rows = await sb("GET", f"/scan_events?user_id=eq.{user_id}&ok=is.true&created_at=gte.{start}&select=id",
                    prefer="count=exact")
    return len(rows)


def quota_for(profile: dict) -> int:
    paid = profile.get("plan") == "pro" and profile.get("plan_status") == "active"
    return PRO_SCANS if paid else FREE_SCANS


async def record_scan(user_id: str, ok: bool, usage: dict | None = None, error: str | None = None) -> None:
    usage = usage or {}
    price_in, price_out = PRICES.get(MODEL, (0.0, 0.0))
    cost = round(usage.get("input_tokens", 0) / 1e6 * price_in + usage.get("output_tokens", 0) / 1e6 * price_out, 5)
    row = {
        "user_id": user_id, "ok": ok, "model": MODEL,
        "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
        "cost_usd": cost, "error": error,
    }
    if DEV:
        row["month"] = datetime.now(timezone.utc).strftime("%Y-%m")
        _dev_state["scans"].append(row)
        return
    await sb("POST", "/scan_events", json=row, prefer="return=minimal")


# -------------------------------------------------------------------- claude
async def read_receipt(image: bytes, media_type: str) -> tuple[dict, dict]:
    """Ask Claude to transcribe the photo. Returns (receipt, token usage)."""
    if DEV:
        canned = json.loads((Path(__file__).resolve().parent / "dev_receipt.json").read_text(encoding="utf-8"))
        return canned, {"input_tokens": 2500, "output_tokens": 3000}

    body = {
        "model": MODEL,
        "max_tokens": 16000,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                             "data": base64.b64encode(image).decode("ascii")}},
                {"type": "text", "text": SCAN_PROMPT},
            ],
        }],
    }
    async with httpx.AsyncClient(timeout=300) as client:
        res = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"content-type": "application/json", "x-api-key": ANTHROPIC_KEY,
                     "anthropic-version": "2023-06-01"},
            json=body,
        )
    payload = res.json()
    if res.status_code >= 400 or "error" in payload:
        message = (payload.get("error") or {}).get("message", f"HTTP {res.status_code}")
        raise HTTPException(status_code=502, detail=f"could not read the receipt: {message}")

    text = "\n".join(b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text")
    return parse_json(text), payload.get("usage", {})


def parse_json(text: str) -> dict:
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    body = fence.group(1) if fence else text
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise HTTPException(status_code=502, detail="the model did not return JSON")
    try:
        return json.loads(body[start:end + 1])
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"the model's JSON did not parse: {exc}") from exc


def check_arithmetic(receipt: dict) -> list[str]:
    """The same checks the Python validator and the app both run."""
    problems = []
    items = receipt.get("items") or []
    if not items:
        problems.append("no items were read")
    for item in items:
        try:
            expect = round(float(item["quantity"]) * float(item["unit_price"]), 2)
        except (KeyError, TypeError, ValueError):
            problems.append(f"line {item.get('line')} is missing a number")
            continue
        if abs(expect - float(item.get("total", 0))) > 0.02:
            problems.append(f"line {item.get('line')}: {expect:.2f} != {float(item.get('total', 0)):.2f}")
    stated = (receipt.get("totals") or {}).get("total")
    if stated:
        line_sum = round(sum(float(i.get("total", 0)) for i in items), 2)
        if abs(line_sum - float(stated)) > 0.05:
            problems.append(f"lines sum to {line_sum:.2f}, receipt says {float(stated):.2f}")
    return problems


# --------------------------------------------------------------------- routes
@app.get("/health")
async def health():
    return {"ok": True, "dev": DEV, "model": MODEL}


@app.get("/me")
async def me(authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    profile = await get_profile(user)
    used = await scans_used(user["id"])
    limit = quota_for(profile)
    return {
        "email": profile.get("email") or user["email"],
        "plan": profile.get("plan", "free"),
        "plan_status": profile.get("plan_status", "active"),
        "plan_renews_at": profile.get("plan_renews_at"),
        "scans_used": used,
        "scans_limit": limit,
        "scans_left": max(0, limit - used),
        "checkout_url": CHECKOUT_URL or None,
    }


@app.post("/scan")
async def scan(
    authorization: str | None = Header(default=None),
    image: UploadFile = File(...),
    save: str = Form(default="1"),
):
    user = current_user(authorization)
    profile = await get_profile(user)

    used, limit = await scans_used(user["id"]), quota_for(profile)
    if used >= limit:
        raise HTTPException(
            status_code=402,
            detail={"error": "quota_exhausted", "scans_used": used, "scans_limit": limit,
                    "checkout_url": CHECKOUT_URL or None},
        )

    blob = await image.read()
    if not blob:
        raise HTTPException(status_code=400, detail="no image was uploaded")
    if len(blob) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="that image is too large — resize it on the device first")
    media_type = image.content_type or "image/jpeg"
    if not media_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="that file is not an image")

    try:
        receipt, usage = await read_receipt(blob, media_type)
    except HTTPException as exc:
        await record_scan(user["id"], ok=False, error=str(exc.detail)[:200])
        raise
    # The photo is never written anywhere: `blob` goes out of scope here.

    problems = check_arithmetic(receipt)
    await record_scan(user["id"], ok=True, usage=usage)

    stored = None
    if save == "1":
        stored = await store_receipt(user["id"], receipt)

    return {"receipt": receipt, "problems": problems, "stored": stored,
            "scans_used": used + 1, "scans_limit": limit}


async def store_receipt(user_id: str, receipt: dict) -> dict:
    """Write the numbers to the user's tables and the anonymous price index."""
    merchant = receipt.get("merchant") or {}
    totals = receipt.get("totals") or {}
    head = {
        "user_id": user_id,
        "merchant_name": merchant.get("name") or "Unknown",
        "merchant_slug": merchant.get("slug") or "unknown",
        "branch": merchant.get("branch"),
        "purchased_at": receipt.get("purchased_at"),
        "currency": receipt.get("currency", "ILS"),
        "total": totals.get("total"),
        "vat_amount": totals.get("vat_amount"),
        "vat_rate": totals.get("vat_rate"),
        "items_count": totals.get("items_count") or len(receipt.get("items") or []),
        "document_number": (receipt.get("document") or {}).get("number"),
    }

    rows = []
    prices = []
    observed_on = str(receipt.get("purchased_at") or "")[:10]
    for index, item in enumerate(receipt.get("items") or [], start=1):
        base_price, base_unit = rc.base_price(item)
        rows.append({
            "line": item.get("line", index), "barcode": item.get("barcode"),
            "name": item.get("name", ""), "name_en": item.get("name_en"),
            "category": item.get("category", "other"),
            "quantity": item.get("quantity"), "unit": item.get("unit"),
            "unit_price": item.get("unit_price"), "total": item.get("total"),
            "base_price": base_price, "base_qty": rc.base_quantity(item), "base_unit": base_unit,
            "product_key": rc.product_key(item), "confidence": item.get("confidence"),
        })
        prices.append({
            "product_key": rc.product_key(item), "barcode": item.get("barcode"),
            "name": item.get("name"), "merchant_slug": head["merchant_slug"],
            "observed_on": observed_on, "base_price": base_price, "base_unit": base_unit,
        })

    if DEV:
        _dev_state["receipts"].append({"head": head, "items": rows})
        return {"receipt_id": "dev-" + str(len(_dev_state["receipts"])), "items": len(rows)}

    created = await sb("POST", "/receipts", json=head,
                       prefer="return=representation,resolution=merge-duplicates")
    receipt_id = created[0]["id"] if created else None
    if receipt_id:
        await sb("DELETE", f"/receipt_items?receipt_id=eq.{receipt_id}", prefer="return=minimal")
        for row in rows:
            row["receipt_id"] = receipt_id
            row["user_id"] = user_id
        if rows:
            await sb("POST", "/receipt_items", json=rows, prefer="return=minimal")
    if prices:
        await sb("POST", "/price_points", json=prices,
                 prefer="return=minimal,resolution=merge-duplicates")
    return {"receipt_id": receipt_id, "items": len(rows)}


@app.post("/billing/webhook")
async def billing_webhook(payload: dict, x_billing_secret: str | None = Header(default=None)):
    """Provider-agnostic on purpose.

    Whichever processor you sign with, its webhook is translated into this one
    shape by a thin adapter, so swapping provider never touches the app or the
    quota logic:

        {"email": "a@b.c", "plan": "pro", "status": "active",
         "renews_at": "2026-10-18T00:00:00Z", "provider": "...", "customer_id": "..."}
    """
    if not BILLING_SECRET or x_billing_secret != BILLING_SECRET:
        raise HTTPException(status_code=401, detail="bad webhook secret")

    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="the webhook carried no email")
    plan = payload.get("plan", "pro")
    status = payload.get("status", "active")
    if plan not in ("free", "pro") or status not in ("active", "past_due", "cancelled"):
        raise HTTPException(status_code=400, detail="unknown plan or status")

    patch = {"plan": plan, "plan_status": status, "plan_renews_at": payload.get("renews_at"),
             "billing_provider": payload.get("provider"), "billing_customer_id": payload.get("customer_id")}
    if DEV:
        for profile in _dev_state["profiles"].values():
            if (profile.get("email") or "").lower() == email:
                profile.update(patch)
                return {"updated": True, "email": email}
        return {"updated": False, "email": email}

    updated = await sb("PATCH", f"/profiles?email=eq.{email}", json=patch)
    return {"updated": bool(updated), "email": email}
