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
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from oracle.signing import verify_envelope  # noqa: E402

HOST = "https://kya-production-f846.up.railway.app"

# The listed /verify speaks x402 (oracle/x402.py): an unpaid call MUST answer 402 + terms,
# because that is the marketplace's hire path. A real caller therefore presents X-PAYMENT.
# At the free tier's amount "0" nothing settles on-chain — this is the zero-value payload a
# real x402 client sends against a fee-0 challenge, not a simulated payment.
X_PAYMENT = base64.b64encode(json.dumps({
    "x402Version": 2,
    "scheme": "exact",
    "network": "eip155:196",
    "payload": {"amount": "0"},
}, separators=(",", ":")).encode()).decode()

# What a caller does with each verdict — reputation gating a real payment decision.
POLICY = {
    "SAFE":    ("PROCEED", "pay the counterparty"),
    "CAUTION": ("HOLD", "route to manual review — unproven, do not auto-pay"),
    "BLOCK":   ("REFUSE", "abort the transaction — do NOT send funds"),
}


def pin_oracle_key(host: str) -> str:
    """Fetch the oracle's Ed25519 key ONCE and pin it. In a real client this is
    hardcoded after first fetch; here we fetch live for the demo."""
    return httpx.get(f"{host}/pubkey", timeout=10).json()["pubkey"]


def ask_kya(host: str, agent_id: str) -> dict:
    return httpx.get(
        f"{host}/verify",
        params={"agentId": agent_id},
        headers={"X-PAYMENT": X_PAYMENT},
        timeout=20,
    ).json()


def gate_transaction(host: str, pinned_key: str, agent_id: str, amount: str = "5 USDC") -> bool:
    body = ask_kya(host, agent_id)
    verdict, digest, env = body["verdict"], body["digest"], body["signature"]

    # 1) Is the verdict AUTHENTIC + FRESH? (pinned key, signed expiry)
    authentic = verify_envelope(digest, env, pinned_key)
    name = body.get("name") or f"#{agent_id}"
    print(f"\n▸ Buyer agent wants to pay {name} (#{agent_id}) {amount}.")
    print(f"  KYA verdict: {verdict} (score {body['score']}) · signature "
          f"{'VALID ✓' if authentic else 'INVALID ✗'}")
    if not authentic:
        print("  DECISION: REFUSE — verdict signature failed to verify. Treat as untrusted.")
        return False

    # 2) Apply policy — reputation gates the payment.
    action, why = POLICY.get(verdict, ("REFUSE", "unknown verdict"))
    top = (body.get("reasons") or ["—"])[0]
    print(f"  why: {top}")
    print(f"  DECISION: {action} — {why}.")
    return action == "PROCEED"


def main():
    ids = sys.argv[1:] or ["2118", "3820"]  # default: a SAFE one and a BLOCK one
    print("== KYA in the loop: gating payments on signed trust verdicts ==")
    key = pin_oracle_key(HOST)
    print(f"pinned oracle key: {key[:16]}…")
    paid, refused, errors = 0, 0, 0
    for aid in ids:
        try:
            (paid := paid + 1) if gate_transaction(HOST, key, aid) else (refused := refused + 1)
        except (httpx.HTTPError, KeyError) as e:
            print(f"  #{aid}: could not verify ({e})")
            errors += 1
    print(f"\nSummary: {paid} payment(s) allowed, {refused} refused/held by KYA.")
    # A REFUSE is a success (that is the product working). An ERROR is not: it means the
    # reference integration could not reach a verdict. Exit non-zero so a broken caller can
    # never report green — this script silently exited 0 while failing every call (Jul 17).
    if errors:
        print(f"✗ {errors} agent(s) errored — the caller could not obtain a verdict.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
