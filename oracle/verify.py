"""
assess() — the full KYA verdict pipeline in one place, so the server and CLI
gather the same evidence: marketplace record + endpoint liveness + malicious-host
scan (A1) + reviewer-integrity audit (A2).
"""
from __future__ import annotations

from .data import fetch_agent, probe_endpoints, scan_malicious, fetch_feedback
from .engine import score_agent, Verdict


def assess(agent_id: str) -> Verdict:
    info, services = fetch_agent(agent_id)
    probes = probe_endpoints(services)
    malicious = scan_malicious(services)
    feedback = fetch_feedback(agent_id)
    owner = [str(info.get("ownerAddress") or "").lower(),
             str(info.get("agentWalletAddress") or "").lower()]
    return score_agent(info, services, probes, agent_id=agent_id,
                       malicious_hosts=malicious, feedback=feedback, owner_addrs=owner)
