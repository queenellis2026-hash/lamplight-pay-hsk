"""Settlement receipts for Lamplight Pay.

A Receipt is the audit record both agents keep after a job settles: who paid
whom, how much, for what, on which chain, and the on-chain proof (tx hash).
It is hash-stable so either side can prove the other agreed to the same facts.
"""
from __future__ import annotations

import hashlib
import json


def build_receipt(*, job_id: int, quote_id: str, service: str, payer: str,
                  agent: str, token: str, token_symbol: str, amount: int,
                  network: str, chain_id: int, escrow_contract: str,
                  outcome: str, tx_hash: str, delivery_hash: str = "") -> dict:
    receipt = {
        "protocol": "lamplight-pay/1",
        "type": "settlement-receipt",
        "job_id": job_id,
        "quote_id": quote_id,
        "service": service,
        "payer": payer,
        "agent": agent,
        "token": token,
        "token_symbol": token_symbol,
        "amount": amount,
        "network": network,
        "chain_id": chain_id,
        "escrow_contract": escrow_contract,
        "outcome": outcome,           # "released" | "refunded" | "cancelled"
        "tx_hash": tx_hash,
        "delivery_hash": delivery_hash,
    }
    blob = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    receipt["receipt_hash"] = "0x" + hashlib.sha256(blob).hexdigest()
    return receipt


def to_json(receipt: dict) -> str:
    return json.dumps(receipt, indent=2, sort_keys=True)
