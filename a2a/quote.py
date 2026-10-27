"""Quote / invoice objects for Lamplight Pay.

A Quote is the off-chain half of a payment: it tells the requester exactly
what to fund, where, and by when. It is JSON-serialisable and hash-stable
(keys sorted, no timestamps inside the hash input except expiry).
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid


def new_quote(*, service: str, price: int, token: str, token_symbol: str,
              network: str, chain_id: int, escrow: str, pay_to: str,
              ttl_seconds: int = 3600) -> dict:
    """Build a quote. `price` is in the token's smallest unit (mUSDC: 6 dp)."""
    now = int(time.time())
    quote = {
        "protocol": "lamplight-pay/1",
        "quote_id": str(uuid.uuid4()),
        "service": service,
        "price": price,
        "token": token,
        "token_symbol": token_symbol,
        "network": network,
        "chain_id": chain_id,
        "escrow_contract": escrow,
        "pay_to": pay_to,          # the worker agent's address
        "issued_at": now,
        "expires_at": now + ttl_seconds,
        "nonce": uuid.uuid4().hex[:16],
    }
    quote["quote_hash"] = _hash(quote)
    return quote


def _hash(quote: dict) -> str:
    payload = {k: v for k, v in quote.items() if k != "quote_hash"}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "0x" + hashlib.sha256(blob).hexdigest()


def quote_expired(quote: dict, now: int | None = None) -> bool:
    return (now or int(time.time())) > quote["expires_at"]


def to_json(quote: dict) -> str:
    return json.dumps(quote, indent=2, sort_keys=True)
