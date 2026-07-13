"""
assess() — the full KYA verdict pipeline in one place, so the server and CLI
gather the same evidence: marketplace record + endpoint liveness + malicious-host
scan (A1) + reviewer-integrity audit (A2) + persisted history (uptime + re-run-
on-patch). A verdict is only trustworthy inside its signed TTL, so every assess()
records what it saw and flags when the agent has CHANGED since we last looked.
"""
from __future__ import annotations

from . import store
from .data import fetch_agent, probe_endpoints, scan_malicious, fetch_feedback
from .engine import score_agent, Verdict


def assess(agent_id: str, *, persist: bool = True) -> Verdict:
    info, services = fetch_agent(agent_id)
    probes = probe_endpoints(services)
    malicious = scan_malicious(services)
    feedback = fetch_feedback(agent_id)
    owner = [str(info.get("ownerAddress") or "").lower(),
             str(info.get("agentWalletAddress") or "").lower()]
    hist = store.uptime(agent_id) if persist else None

    v = score_agent(info, services, probes, agent_id=agent_id,
                    malicious_hosts=malicious, feedback=feedback, owner_addrs=owner,
                    history=hist)

    if persist:
        sh = store.state_hash(info, services, feedback)
        store.record_probes(agent_id, probes)
        change = store.record(v, sh)
        # Surface "re-verified / it moved" on the verdict itself so the caller (and
        # the demo) can see a patched agent flip instead of a silent overwrite.
        v.evidence["revalidated"] = change["previous"] is not None
        v.evidence["state_changed"] = change["changed"]
        if change["previous"] and change["previous"] != v.verdict:
            v.evidence["previous_verdict"] = change["previous"]
        if change["transition"]:
            t = change["transition"]
            v.reasons.insert(0, f"🔄 Re-verified: {t['from']} → {t['to']} "
                                f"(agent changed since last check).")
    return v
