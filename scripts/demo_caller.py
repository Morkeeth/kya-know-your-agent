#!/usr/bin/env python3
"""
KYA in the loop — a reference CALLER.

This is how you actually USE KYA: a buyer agent, before it pays or hires a
counterparty ASP, calls KYA, cryptographically verifies the signed verdict
against a PINNED oracle key, and refuses to transact on BLOCK. Reputation is not
advice here — it gates the payment.

Runs against the live deployment (a real client of the real service). Point it at
any OKX.AI agent id:  ./.venv/bin/python scripts/demo_caller.py 2118 3820

Trust model: fetch the oracle key ONCE from /pubkey and pin it. Then every verdict
is checked with verify_envelope against that pinned key (a rogue oracle can't ship
its own key and self-sign SAFE) and against the signed freshness window.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from oracle.signing import verify_envelope, digest_for_body  # noqa: E402

HOST = "https://kya-production-f846.up.railway.app"


def pin_oracle_key(host: str) -> str:
    """Fetch the oracle's Ed25519 key ONCE and pin it. In a real client this is
    hardcoded after first fetch; here we fetch live for the demo."""
    return httpx.get(f"{host}/pubkey", timeout=10).json()["pubkey"]


def ask_kya(host: str, agent_id: str) -> dict:
    return httpx.get(f"{host}/verify", params={"agentId": agent_id}, timeout=20).json()


def gate_transaction(host: str, pinned_key: str, agent_id: str, amount_usd: float) -> str:
    """Gate ONE payment of `amount_usd` on the signed verdict AND the signed ceiling.

    The ceiling is the product. A rating tells you "this one is good"; `max_safe_usd` tells
    you *how much* good — the largest single payment this counterparty has EARNED, derived
    from settled volume. So the decision is a function of (verdict, amount), never of the
    verdict alone. That is the whole difference between rating and pricing, and until
    2026-07-17 this reference caller ignored the ceiling entirely and branched on the
    verdict string — the exact behaviour the README mocks. It happily paid 5 USDC to an
    agent whose signed ceiling was $0.66.

    Returns one of PROCEED / HOLD / REFUSE.
    """
    body = ask_kya(host, agent_id)
    verdict, env = body["verdict"], body["signature"]
    ceiling = float(body.get("max_safe_usd") or 0.0)

    # 1) Is the verdict AUTHENTIC + FRESH? (pinned key, signed expiry)
    #    RECOMPUTE the digest from the bytes we received — never trust body["digest"].
    #    The signature covers the digest, not the body, so an attacker who rewrites
    #    evidence.cluster (99 -> 1) and replays the original digest+signature would sail
    #    through a naive verify_envelope(body["digest"], ...). This caller did exactly that
    #    until 2026-07-17. Recomputing is what binds the signature to THIS payload.
    digest = digest_for_body(body)
    authentic = verify_envelope(digest, env, pinned_key) and digest == body.get("digest")
    name = body.get("name") or f"#{agent_id}"
    print(f"\n▸ Buyer agent wants to pay {name} (#{agent_id}) ${amount_usd:,.2f}.")
    print(f"  KYA verdict: {verdict} (score {body['score']}) · earned ceiling "
          f"${ceiling:,.2f} · signature {'VALID ✓' if authentic else 'INVALID ✗'}")
    if not authentic:
        print("  DECISION: REFUSE — verdict signature failed to verify. Treat as untrusted.")
        return "REFUSE"

    print(f"  why: {(body.get('reasons') or ['—'])[0]}")

    # 2) A hard verdict refuses at ANY price.
    if verdict == "BLOCK":
        print("  DECISION: REFUSE — BLOCK. Abort the transaction, do NOT send funds.")
        return "REFUSE"

    # 3) THE CEILING. Even a SAFE counterparty is only safe up to what it has earned.
    #    This is the branch a star rating cannot express.
    if amount_usd > ceiling:
        print(f"  DECISION: HOLD — ${amount_usd:,.2f} exceeds the ${ceiling:,.2f} this agent "
              f"has earned. Split it, or route to manual review.")
        return "HOLD"

    # 4) Unproven counterparties never auto-pay, regardless of amount.
    if verdict == "CAUTION":
        print("  DECISION: HOLD — unproven counterparty; route to manual review.")
        return "HOLD"

    print(f"  DECISION: PROCEED — ${amount_usd:,.2f} is within the earned ceiling. Pay it.")
    return "PROCEED"


# Each beat is (agentId, amount_usd) — the SAME counterparty at two prices is the point.
DEFAULT_BEATS = [
    ("2118", 0.50),   # Otto AI, SAFE, ceiling $0.66  -> PROCEED (under)
    ("2118", 5.00),   # Otto AI, SAFE, ceiling $0.66  -> HOLD    (over) <- the whole thesis
    ("3345", 5.00),   # Eat This?, SAFE, ceiling $16.50 -> PROCEED (earned more, gets more)
    ("3820", 5.00),   # Sentiment Oracle, BLOCK        -> REFUSE  (at any price)
]


def _parse(args: list[str]) -> list[tuple[str, float]]:
    """`2118:0.50` pairs; a bare id defaults to $5.00."""
    out = []
    for a in args:
        aid, _, amt = a.partition(":")
        out.append((aid, float(amt) if amt else 5.00))
    return out


def main():
    beats = _parse(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_BEATS
    print("== KYA in the loop: pricing payments on signed trust verdicts ==")
    print("   (the decision is a function of verdict AND amount — that is what a rating cannot do)")
    key = pin_oracle_key(HOST)
    print(f"pinned oracle key: {key[:16]}…")

    tally = {"PROCEED": 0, "HOLD": 0, "REFUSE": 0}
    errors = 0
    for aid, amt in beats:
        try:
            tally[gate_transaction(HOST, key, aid, amt)] += 1
        except (httpx.HTTPError, KeyError, ValueError) as e:
            print(f"  #{aid}: could not verify ({e})")
            errors += 1
    print(f"\nSummary: {tally['PROCEED']} paid · {tally['HOLD']} held (over ceiling or unproven) "
          f"· {tally['REFUSE']} refused.")
    # HOLD and REFUSE are the product WORKING. An ERROR is not: it means the reference
    # integration could not reach a verdict. Exit non-zero so a broken caller can never
    # report green — this script silently exited 0 while failing every call (Jul 17).
    if errors:
        print(f"✗ {errors} agent(s) errored — the caller could not obtain a verdict.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
