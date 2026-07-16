"""
x402 payment layer for the listed /verify service.

Why this exists, measured not assumed (2026-07-16): OKX.AI's marketplace routes an
A2MCP hire through x402. An unpaid request to the listed endpoint MUST answer HTTP 402
with a base64 `payment-required` header carrying the payment terms; only a request that
presents an `X-PAYMENT` header gets the result. Serving 200 to an unpaid call (what KYA
did after the first fix) is "live and wrong": the marketplace probe reports valid:false
and the hire is blocked.

"Free" here does NOT mean "no payment layer". The true comparable — SlowMist #2155, fee 0,
A2MCP, APPROVED — returns a 402 whose challenge is `amount: "0"` in USDT on XLayer. So KYA
stays genuinely free (nothing settles) while still speaking x402 so the marketplace can
route it. This mirrors SlowMist's approved challenge byte-for-byte in structure.

Pricing the service (a nonzero amount → Revenue Rocket) is a separate, deliberate decision
for Oscar; this module keeps amount 0 and never invents a price.
"""
from __future__ import annotations

import base64
import json
import os

# XLayer USDT — the asset SlowMist's approved fee-0 challenge uses, verified live.
USDT_XLAYER = "0x779ded0c9e1022225f8e0630b35a9b54be713736"
NETWORK_XLAYER = "eip155:196"

# Where a (zero) payment would be directed: KYA's own owner wallet (#5290's ownerAddress).
PAY_TO = os.environ.get("KYA_PAYTO", "0x88f53629d84abe6dffbacb15f6e1eb5464e2761b")
# "0" = genuinely free. Override to price the service (Revenue Rocket) — Oscar's call.
AMOUNT = os.environ.get("KYA_PRICE", "0")


def challenge(resource_url: str) -> dict:
    """The x402 payment-required object, shaped exactly like the approved SlowMist one."""
    return {
        "x402Version": 2,
        "error": "Payment required",
        "resource": {
            "url": resource_url,
            "description": "A signed SAFE / CAUTION / BLOCK trust verdict on any OKX.AI agent, "
                           "plus the max USD it has earned the right to be trusted with.",
            "mimeType": "application/json",
        },
        "accepts": [{
            "scheme": "exact",
            "network": NETWORK_XLAYER,
            "asset": USDT_XLAYER,
            "amount": AMOUNT,
            "payTo": PAY_TO,
            "maxTimeoutSeconds": 300,
            "extra": {"name": "USDT", "version": "1"},
        }],
    }


def challenge_header(resource_url: str) -> str:
    """base64(JSON) for the `payment-required` response header (SlowMist's exact encoding)."""
    blob = json.dumps(challenge(resource_url), separators=(",", ":")).encode()
    return base64.b64encode(blob).decode()


def is_paid(headers) -> bool:
    """Has the caller presented payment? At amount 0 there is nothing to settle on-chain,
    so a present, non-empty X-PAYMENT header is sufficient — we never claim to have
    verified a settlement we did not require. If AMOUNT ever becomes nonzero, this MUST be
    replaced with real facilitator verification (documented, not silently trusted)."""
    xp = headers.get("x-payment") or headers.get("X-PAYMENT")
    return bool(xp and xp.strip())
