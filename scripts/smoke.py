#!/usr/bin/env python3
"""Smoke test: run the verdict engine against a spread of real live agents and
print a one-line summary each. Proves the engine DISCRIMINATES, not rubber-stamps.

    python scripts/smoke.py 2118 3733 2971 3820 3369 1771
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from oracle import fetch_agent, probe_endpoints, score_agent, AgentNotFound  # noqa: E402


def main(ids: list[str]) -> int:
    for aid in ids:
        try:
            info, services = fetch_agent(aid)
            v = score_agent(info, services, probe_endpoints(services), agent_id=aid)
            print(f"  #{aid:5} {v.name[:26]:26} -> {v.verdict:7} score={v.score:3}  ({info.get('salesCount') or 0} sales)")
            for r in v.reasons[:2]:
                print(f"          {r}")
        except AgentNotFound:
            print(f"  #{aid:5} (not found)")
        except Exception as e:  # noqa: BLE001
            print(f"  #{aid:5} ERROR: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["2118", "3733", "2971", "3820", "3369", "1771"]))
