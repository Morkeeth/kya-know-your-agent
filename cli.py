#!/usr/bin/env python3
"""Local verification harness — verdict for a real OKX.AI agent, no server needed.

    python cli.py 2118        # Otto AI
    python cli.py 3733        # Scope
"""
import json
import sys

from oracle import fetch_agent, probe_endpoints, score_agent, AgentNotFound
from oracle.persona import pronounce


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python cli.py <agentId>", file=sys.stderr)
        return 2
    agent_id = sys.argv[1]
    try:
        info, services = fetch_agent(agent_id)
    except AgentNotFound as e:
        print(f"not found: {e}", file=sys.stderr)
        return 1
    probes = probe_endpoints(services)
    verdict = score_agent(info, services, probes, agent_id=agent_id)
    out = verdict.to_dict()
    out["pronouncement"] = pronounce(verdict)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
