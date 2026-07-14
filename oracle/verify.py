"""
assess() — the full KYA verdict pipeline in one place, so the server and CLI
gather the same evidence: marketplace record + endpoint liveness + malicious-host
scan (A1) + reviewer-integrity audit (A2) + persisted history (uptime + re-run-
on-patch). A verdict is only trustworthy inside its signed TTL, so every assess()
records what it saw and flags when the agent has CHANGED since we last looked.
"""
from __future__ import annotations

from . import store, settlement as _settlement
from .content import scan_injection, gather_texts
from .data import (fetch_agent, probe_endpoints, scan_malicious, fetch_feedback,
                   fetch_identity, fetch_domain_intel)
from .engine import score_agent, Verdict


def assess(agent_id: str, *, persist: bool = True) -> Verdict:
    info, services = fetch_agent(agent_id)
    probes = probe_endpoints(services)
    malicious = scan_malicious(services)
    feedback = fetch_feedback(agent_id)
    identity = fetch_identity(agent_id, info, services)
    domain_intel = fetch_domain_intel(services)
    content = scan_injection(gather_texts(info, services))
    owner = [str(info.get("ownerAddress") or "").lower(),
             str(info.get("agentWalletAddress") or "").lower()]
    hist = store.uptime(agent_id) if persist else None
    # Default-OFF; only reads on-chain settlements when explicitly enabled + keyed.
    settle = None
    if _settlement.enabled():
        wallet = str(info.get("agentWalletAddress") or "")
        settle = _settlement.fetch_settlements(wallet) if wallet else None

    v = score_agent(info, services, probes, agent_id=agent_id,
                    malicious_hosts=malicious, feedback=feedback, owner_addrs=owner,
                    history=hist, identity=identity, settlement=settle, content=content,
                    domain_intel=domain_intel)

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
