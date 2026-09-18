"""Verifying a Supabase access token.

Supabase signs its access tokens HS256 with the project's JWT secret, which is
plain HMAC-SHA256 — so this needs nothing but the standard library. Keeping it
dependency-free means one less thing to keep patched on a server that holds an
API key.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time


class AuthError(Exception):
    """The token is missing, malformed, expired or not signed by us."""


def _b64url(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def verify(token: str, secret: str, audience: str = "authenticated") -> dict:
    """Return the token's claims, or raise AuthError. Never returns on failure."""
    if not token or not secret:
        raise AuthError("missing token or secret")

    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("not a JWT")
    header_b64, payload_b64, signature_b64 = parts

    try:
        header = json.loads(_b64url(header_b64))
        claims = json.loads(_b64url(payload_b64))
        signature = _b64url(signature_b64)
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError(f"undecodable token: {exc}") from exc

    if header.get("alg") != "HS256":
        # Anything else — including "none" — is refused rather than trusted.
        raise AuthError(f"unsupported algorithm {header.get('alg')!r}")

    signed = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, signature):
        raise AuthError("bad signature")

    now = int(time.time())
    if int(claims.get("exp", 0)) < now:
        raise AuthError("token expired")
    if claims.get("aud") not in (audience, None):
        raise AuthError(f"wrong audience {claims.get('aud')!r}")
    if not claims.get("sub"):
        raise AuthError("token carries no subject")

    return claims
