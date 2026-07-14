#!/usr/bin/env python3
"""
Full-marketplace sweep — evaluate every public OKX.AI agent through KYA and leave
the verdicts sitting in the deployed store, so the Watchtower is comprehensive and
any agent that later calls /verify hits an already-warm, recently re-verified result.

The OKX marketplace has no "list all" endpoint (search REQUIRES a query), so this
does a keyword-union sweep across many category terms + pages and dedupes the ids.
That is broad but NOT provably exhaustive — the coverage line at the end reports how
many ids were discovered so a thin sweep can't masquerade as "the whole marketplace".

Usage:
  ./.venv/bin/python scripts/seed_all.py                 # against the live deployed URL
  KYA_URL=http://localhost:8000 python scripts/seed_all.py
  python scripts/seed_all.py --limit 40                  # cap the number verified (smoke)

Idempotent and safe to re-run (this is what a freshness cron would call).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import subprocess
import sys
import urllib.request

KYA_URL = os.environ.get("KYA_URL", "https://kya-production-f846.up.railway.app").rstrip("/")
ONCHAINOS = os.environ.get("ONCHAINOS_BIN", os.path.expanduser("~/.local/bin/onchainos"))

# Category terms cast a wide net over a marketplace that is mostly data/trading/AI agents.
QUERIES = [
    "data", "trading", "ai", "oracle", "price", "market", "analytics", "token", "defi",
    "news", "sentiment", "security", "search", "image", "research", "report", "onchain",
    "wallet", "nft", "social", "agent", "yield", "signal", "risk", "meme", "chain",
]
PAGES = 4
PAGE_SIZE = 50


def discover_ids() -> dict[str, str]:
    """Return {agentId: name} across the keyword-union sweep."""
    found: dict[str, str] = {}
    for q in QUERIES:
        for page in range(1, PAGES + 1):
            try:
                out = subprocess.run(
                    [ONCHAINOS, "agent", "search", "--query", q,
                     "--page-size", str(PAGE_SIZE), "--page", str(page)],
                    capture_output=True, text=True, timeout=40,
                )
                if out.returncode != 0:
                    continue
                lst = (json.loads(out.stdout).get("data") or {}).get("list") or []
            except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
                continue
            if not lst:
                break
            for x in lst:
                aid = str(x.get("agentId") or "").strip()
                if aid and aid.isdigit():
                    found.setdefault(aid, (x.get("name") or "")[:40])
    return found


def verify(aid: str) -> tuple[str, str, object, object]:
    try:
        with urllib.request.urlopen(f"{KYA_URL}/verify?agentId={aid}", timeout=35) as r:
            d = json.load(r)
        return (aid, d.get("verdict", "?"), d.get("score"), (d.get("name") or "")[:36])
    except Exception as e:  # noqa: BLE001 — a sweep tolerates individual failures
        return (aid, "ERR", None, str(e)[:40])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap agents verified (0 = all)")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    print(f"KYA full-marketplace sweep → {KYA_URL}")
    print("discovering public agents (keyword-union across "
          f"{len(QUERIES)} terms × {PAGES} pages)…")
    ids = discover_ids()
    order = sorted(ids)
    if args.limit:
        order = order[: args.limit]
    print(f"discovered {len(ids)} unique public agents; verifying {len(order)}\n")

    dist: dict[str, int] = {}
    done = 0
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for aid, verdict, score, name in ex.map(verify, order):
            done += 1
            dist[verdict] = dist.get(verdict, 0) + 1
            if done % 20 == 0 or verdict in ("BLOCK", "ERR"):
                print(f"  [{done}/{len(order)}] #{aid} {verdict} {score if score is not None else ''} {name}")

    print("\n=== sweep complete ===")
    print(f"discovered: {len(ids)}   verified: {len(order)}")
    for k in ("SAFE", "CAUTION", "BLOCK", "ERR"):
        if k in dist:
            print(f"  {k}: {dist[k]}")
    print(f"\nboard: {KYA_URL}/watchtower")
    # A sweep that errors on more than a quarter of agents is not a healthy seed.
    errs = dist.get("ERR", 0)
    if order and errs > len(order) // 4:
        print(f"⚠️  {errs} errors — deployed service may be rate-limited; re-run to fill gaps.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
