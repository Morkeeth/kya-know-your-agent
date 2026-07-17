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
# self-payment — the exact wash pattern KYA itself flags.
#
# NO DEFAULT, deliberately (2026-07-17): this used to default to #5290's ownerAddress, i.e.
# the buyer wallet. Any deploy that forgot KYA_AUDIT_PAYTO would have quietly settled money
# to itself — KYA faking its own revenue, the precise pattern it penalises others for. An
# unset payTo now refuses to mount /audit instead (the free tier is unaffected), because a
# paid tier that cannot name a distinct payee should not take money.
AUDIT_PAYTO = os.environ.get("KYA_AUDIT_PAYTO")
BUYER_WALLET = "0x88f53629d84abe6dffbacb15f6e1eb5464e2761b"  # #5290 ownerAddress
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
    if not AUDIT_PAYTO:
        return None, ("KYA_AUDIT_PAYTO unset — /audit not mounted. Refusing to take money "
                      "without a distinct payee (free tier unaffected).")
    if AUDIT_PAYTO.lower() == BUYER_WALLET.lower():
        return None, ("KYA_AUDIT_PAYTO is the buyer wallet — that is a self-payment, the "
                      "wash pattern KYA penalises. /audit not mounted.")
    try:
        # ASYNC facilitator — the FastAPI middleware builds the async x402ResourceServer,
        # which does `await facilitator.verify(...)` / `.settle(...)`. The Sync client's
        # verify returns a plain VerifyResponse, so awaiting it throws
        # "object VerifyResponse can't be used in 'await'" (the settle 500 on Jul 16).
        from x402.http import (OKXFacilitatorClient, OKXFacilitatorConfig,
                               OKXAuthConfig, PaymentOption, RouteConfig)
        from x402.http.middleware.fastapi import payment_middleware_from_config
    except Exception as e:  # SDK not installed / import error
        return None, f"x402 SDK unavailable: {e}"

    try:
        auth = OKXAuthConfig(api_key=key, secret_key=secret, passphrase=passphrase)
        facilitator = OKXFacilitatorClient(OKXFacilitatorConfig(auth=auth))
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
    """The premium payload — the DEPTH behind the verdict, not a relabelled /verify.

    What earns the $0.10 (checked against the free tier, 2026-07-17): /verify already
    returns the verdict, score, max_safe_usd, reasons, signals and evidence. Those are NOT
    the product here — reprinting them and calling it premium would be the exact
    "published != true" failure KYA exists to catch, and a buyer diffing the two payloads
    would find it in seconds.

    The paid tier answers what a snapshot cannot: **has this agent always been this?**
      - `timeline`  — every verdict KYA has ever issued for it, with the state hash that
                      moved. A clean agent that flipped BLOCK->SAFE last week is not the
                      same counterparty as one that has been SAFE for a month.
      - `uptime`    — measured from real probe samples, not the listing's self-reported
                      onlineStatus.
      - `fleet`     — the operator's FULL agent list. /verify returns a cluster summary
                      (fleet_size, risk); this returns the actual siblings, so a buyer can
                      see WHICH other agents the same wallet runs.
    A regression test pins this: the paid payload must stay a strict superset of the free
    one (tests/test_audit_paid.py). It was not, until this fix.
    """
    from oracle import store  # local import: keeps the module importable without a DB

    v = verdict
    owner = ((v.evidence or {}).get("cluster") or {}).get("owner")
    return {
        "agent_id": agent_id,
        "verdict": v.verdict,
        "score": v.score,
        "confidence": v.confidence,
        "max_safe_usd": v.max_safe_usd,
        "volume_basis": (v.evidence or {}).get("volumeBasis"),
        "settled_volume": (v.evidence or {}).get("settledVolume"),
        "reasons": v.reasons,
        "signals": v.signals,
        "evidence": v.evidence,         # owner-fleet summary, endpoints, fee spread, caps
        "digest": v.digest,             # the signed passport digest
        "signature": env,               # signed + TTL-bound, verifiable at /pubkey
        # ── the depth the free tier does NOT return ──────────────────────────────
        "timeline": store.history(agent_id, limit=50),
        "uptime": store.uptime(agent_id),
        "fleet": store.fleet_for(owner) if owner else None,
        "tier": "full-audit (paid)",
    }
