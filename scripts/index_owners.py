#!/usr/bin/env python3
"""
Owner index sweep — map every discoverable OKX.AI agent to the WALLET that controls it.

Why this exists: OKX's `agent search` (what the marketplace UI shows a buyer) does NOT
return ownerAddress. Only `agent get-agents` does. So a buyer browsing OKX.AI cannot see
that dozens of "independent providers" are one wallet. KYA can. This builds the index that
makes the supply-side sybil signal (engine.py, `owner_fleet`) possible.

Cheap on purpose: no endpoint probing, no scoring. Discovery via the same keyword-union
sweep seed_all.py uses, then `get-agents` in batches of 20 (the API's hard cap).

Usage:
  ./.venv/bin/python scripts/index_owners.py            # build the index, print concentration
  ./.venv/bin/python scripts/index_owners.py --report   # report from the existing index only
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from oracle import store  # noqa: E402

ONCHAINOS = os.environ.get("ONCHAINOS_BIN", os.path.expanduser("~/.local/bin/onchainos"))
BATCH = 20  # API hard cap: "agentIdList size must not exceed 20"

QUERIES = [
    "data", "trading", "ai", "oracle", "price", "market", "analytics", "token", "defi",
    "news", "sentiment", "security", "search", "image", "research", "report", "onchain",
    "wallet", "nft", "social", "agent", "yield", "signal", "risk", "meme", "chain",
    "desk", "pulse", "edge", "cycle", "depth",  # template stems seen in the wild
]
PAGES = 4


def _cli(args: list[str]) -> dict:
    try:
        p = subprocess.run([ONCHAINOS] + args, capture_output=True, text=True, timeout=90)
        return json.loads(p.stdout or "{}")
    except Exception:
        return {}


def discover_ids() -> set[str]:
    found: set[str] = set()
    for q in QUERIES:
        for page in range(1, PAGES + 1):
            d = _cli(["agent", "search", "--query", q, "--page", str(page)])
            lst = ((d.get("data") or {}).get("list")) or []
            if not lst:
                break
            for a in lst:
                if a.get("agentId"):
                    found.add(str(a["agentId"]))
    return found


def index(ids: set[str]) -> int:
    """Resolve owners in batches of 20 and record them. Returns agents indexed."""
    ordered = sorted(ids, key=lambda x: int(x) if x.isdigit() else 0)
    n = 0
    for i in range(0, len(ordered), BATCH):
        chunk = ordered[i:i + BATCH]
        d = _cli(["agent", "get-agents", "--agent-ids", ",".join(chunk)])
        for a in (d.get("data") or []):
            owner = str(a.get("ownerAddress") or "").lower()
            if not owner:
                continue
            store.record_owner(str(a.get("agentId")), owner,
                               name=a.get("name"), sold=a.get("soldCount"))
            n += 1
        print(f"  indexed {n}/{len(ordered)}", end="\r", flush=True)
    print()
    return n


def report() -> None:
    import sqlite3
    with store._conn() as con:
        rows = con.execute(
            "SELECT owner, COUNT(*) c, SUM(COALESCE(sold,0)) s FROM agent_owners"
            " GROUP BY owner ORDER BY c DESC LIMIT 8"
        ).fetchall()
        total = con.execute("SELECT COUNT(*) c FROM agent_owners").fetchone()["c"]
        owners = con.execute("SELECT COUNT(DISTINCT owner) c FROM agent_owners").fetchone()["c"]
    if not total:
        print("index empty — run without --report first")
        return
    print(f"\n{total} agents indexed across {owners} distinct wallets\n")
    print(f"  {'wallet':<24} {'agents':>7} {'% of mkt':>9} {'sales':>7}")
    print("  " + "-" * 50)
    for r in rows:
        pct = 100.0 * r["c"] / total
        print(f"  {r['owner'][:10]+'…'+r['owner'][-6:]:<24} {r['c']:>7} {pct:>8.1f}% {r['s']:>7}")
    top = rows[0]
    print(f"\n  Top wallet controls {100.0*top['c']/total:.0f}% of the discoverable marketplace.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="report from the existing index only")
    ap.add_argument("--enumerate", nargs=2, type=int, metavar=("FROM", "TO"),
                    help="sweep a contiguous agentId range instead of keyword search. "
                         "Agent ids are sequential, so this is the only COMPLETE discovery: "
                         "search is keyword-matched and never returns unlisted agents, which "
                         "is exactly where a sybil farm hides.")
    a = ap.parse_args()
    if a.enumerate:
        lo, hi = a.enumerate
        ids = {str(i) for i in range(lo, hi + 1)}
        print(f"enumerating agentIds {lo}..{hi} ({len(ids)} ids, batches of {BATCH})…")
        index(ids)
    elif not a.report:
        print("discovering agent ids (keyword-union sweep)…")
        ids = discover_ids()
        print(f"  {len(ids)} ids discovered")
        print("resolving owners (get-agents, batches of 20)…")
        index(ids)
    report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
