"""
The PAID premium tier: /audit, gated by real x402 via OKX's facilitator.

Freemium split (deliberate — see NIGHTRUN + the peer's demo notes):
  /verify  = FREE quick scan (SAFE/CAUTION/BLOCK + score). The service under OKX review.
             Untouched by this module. Stays free forever.
  /audit   = PAID full audit ($0.10 USDT). Everything the engine computes: every signal,
             the owner-fleet analysis, max_safe_usd with its basis, the signed passport
             digest, and the verdict timeline. You pay for the depth, not the yes/no.

This uses the REAL OKX server SDK (okxweb3-app-x402), not a stub. An unpaid call gets a
402 challenge minted by OKX's facilitator; a paid call is verified on-chain by the
facilitator before we serve. Credentials come from .env (gitignored) — NEVER committed.

Guarded: if creds are absent or the SDK can't init, /audit simply isn't mounted and the
rest of the app (crucially the free /verify under review) is unaffected.
"""
from __future__ import annotations

import os

# Receiving wallet for the (real) 0.10 USDT. MUST differ from the buyer wallet or it is a
# self-payment — the exact wash pattern KYA itself flags. Set KYA_AUDIT_PAYTO to a wallet
# you control that is NOT the buyer before running a real settle.
AUDIT_PAYTO = os.environ.get("KYA_AUDIT_PAYTO", "0x88f53629d84abe6dffbacb15f6e1eb5464e2761b")
AUDIT_PRICE = os.environ.get("KYA_AUDIT_PRICE", "$0.10")
NETWORK_XLAYER = "eip155:196"


def build_paid_middleware():
    """Return (middleware_fn, reason). middleware_fn is None if the paid tier can't mount
    (no creds / SDK missing) — caller then serves the app without the paid gate."""
    key = os.environ.get("OKX_API_KEY")
    secret = os.environ.get("OKX_SECRET_KEY")
    passphrase = os.environ.get("OKX_PASSPHRASE")
    if not (key and secret and passphrase):
        return None, "no OKX creds in env — /audit not mounted (free tier unaffected)"
    try:
        from x402.http import (OKXFacilitatorClientSync, OKXFacilitatorConfig,
                               OKXAuthConfig, PaymentOption, RouteConfig)
        from x402.http.middleware.fastapi import payment_middleware_from_config
    except Exception as e:  # SDK not installed / import error
        return None, f"x402 SDK unavailable: {e}"

    try:
        auth = OKXAuthConfig(api_key=key, secret_key=secret, passphrase=passphrase)
        facilitator = OKXFacilitatorClientSync(OKXFacilitatorConfig(auth=auth))
        route = RouteConfig(
            accepts=[PaymentOption(
                scheme="exact",
                pay_to=AUDIT_PAYTO,
                price=AUDIT_PRICE,
                network=NETWORK_XLAYER,
            )],
            resource="/audit",
            description="KYA full audit: every signal, owner-fleet analysis, priced trust "
                        "(max_safe_usd), and the signed verdict timeline for one agent.",
            mime_type="application/json",
        )
        # The server needs the exact-EVM scheme mechanism registered for XLayer — the
        # facilitator supporting it isn't enough, the resource server must know how to
        # verify an `exact` payload locally. (Undocumented in the OKX quickstart; found
        # in the SDK's own examples: server.register("eip155:196", ExactEvmServerScheme()).)
        from x402.mechanisms.evm.exact import ExactEvmServerScheme
        mw = payment_middleware_from_config(
            routes={"/audit": route},
            facilitator_client=facilitator,
            schemes=[{"network": NETWORK_XLAYER, "server": ExactEvmServerScheme()}],
        )
        return mw, f"paid /audit mounted (price {AUDIT_PRICE}, payTo {AUDIT_PAYTO[:10]}…)"
    except Exception as e:
        return None, f"failed to build paid middleware: {e}"


def full_audit(agent_id: str, verdict, env) -> dict:
    """The premium payload — everything, not just the headline verdict."""
    v = verdict
    return {
        "agent_id": agent_id,
        "verdict": v.verdict,
        "score": v.score,
        "confidence": v.confidence,
        "max_safe_usd": v.max_safe_usd,
        "volume_basis": v.evidence.get("volumeBasis"),
        "settled_volume": v.evidence.get("settledVolume"),
        "reasons": v.reasons,
        "signals": v.signals,          # the full breakdown the free tier withholds
        "evidence": v.evidence,         # owner-fleet, endpoints, fee spread, caps
        "signature": env,               # signed + TTL-bound, verifiable at /pubkey
        "tier": "full-audit (paid)",
    }
