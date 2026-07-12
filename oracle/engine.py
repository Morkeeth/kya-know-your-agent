"""
Trust-verdict engine for OKX.AI ASPs.

Pure functions: given an agent's marketplace record + endpoint liveness probes,
produce a signed GO/NO-GO verdict. No I/O here so it stays unit-testable.

Design philosophy — SAFE must be EARNED, not defaulted
------------------------------------------------------
Every *listed* ASP has passed OKX review, is marked online, and has a live
endpoint — that is table stakes, not a reason to trust it with your money. So
the engine is GATED, not purely additive:

  * Hard failures (dead endpoint, inactive, test account) CAP the score low → BLOCK.
  * Unproven (0 sales) CAPS at CAUTION — "live but nobody has actually used it".
  * SAFE (>=70) is only reachable with a real, earned track record + clean signals.

Verdict scale:
    SAFE     score >= 70   — proven, live, clean
    CAUTION  45..69        — live but unproven, or soft flags
    BLOCK    < 45          — dead endpoint, failed review, anomalous, or no ASP record
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field, asdict
from typing import Any

# A shared demo key; real Ed25519 signing lives in oracle/signing.py and is used
# by the service layer. This HMAC keeps the pure engine dependency-free and its
# verdicts tamper-evident on their own.
_SIGNING_KEY = b"oracle-demo-signing-key-v0"

# Observed A2MCP fee range on the live marketplace (USDT): 0.001 .. 0.50.
_FEE_SANE_MAX = 2.0

_TEST_MARKERS = ("测试", "riskcontrol", "test buyer", "testbuyer", "demo agent")

SAFE, CAUTION, BLOCK = "SAFE", "CAUTION", "BLOCK"


@dataclass
class Signal:
    """One scored observation that moves (or caps) the verdict, with a reason."""
    key: str
    delta: int
    reason: str
    severity: str  # "good" | "info" | "warn" | "critical"
    cap: int | None = None  # if set, the final score may not exceed this


@dataclass
class Verdict:
    agent_id: str
    name: str
    verdict: str
    score: int
    confidence: int = 0            # 0..100 — how much evidence we actually had
    reasons: list[str] = field(default_factory=list)
    signals: list[dict] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    signature: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _live_label(probe: dict) -> str:
    if probe.get("reachable"):
        code = probe.get("status")
        return "live (x402 paywall)" if code == 402 else f"live (HTTP {code})"
    return "unreachable"


def score_agent(agent_info: dict | None, services: list[dict], probes: dict[str, dict],
                agent_id: str | None = None) -> Verdict:
    """
    agent_info : the `agentInfo` object from `onchainos agent service-list` (may be None).
    services   : the `list` array (each has endpoint, fee, serviceType, ...).
    probes     : { endpoint_url: {"reachable": bool, "status": int|None} }.
    """
    # ---- No ASP record at all (User/buyer identity, or unregistered) ----
    if not agent_info:
        v = Verdict(
            agent_id=str(agent_id or ""), name="", verdict=BLOCK, score=20, confidence=15,
            reasons=["⛔ No registered ASP services for this ID — not a provider you can transact with."],
            signals=[asdict(Signal("no_record", 0,
                "Target is not a listed ASP (no agentInfo / zero services).", "critical", cap=25))],
            evidence={"isAsp": False},
        )
        v.signature = _sign(v)
        return v

    name = str(agent_info.get("name") or "").strip()
    aid = str(agent_info.get("agentId") or agent_id or "")
    signals: list[Signal] = []

    # ---- Liveness (a dead endpoint is the #1 real-world failure) ----
    endpoints = [s.get("endpoint") for s in services if s.get("endpoint")]
    if endpoints:
        reachable = [e for e in endpoints if probes.get(e, {}).get("reachable")]
        got_402 = any(probes.get(e, {}).get("status") == 402 for e in endpoints)
        if len(reachable) == len(endpoints):
            signals.append(Signal("liveness", +18,
                f"All {len(endpoints)} service endpoint(s) responding.", "good"))
        elif reachable:
            signals.append(Signal("liveness", +2,
                f"{len(reachable)}/{len(endpoints)} endpoints responding — partial outage.",
                "warn", cap=60))
        else:
            signals.append(Signal("liveness", -40,
                f"None of {len(endpoints)} listed endpoint(s) reachable — service is DOWN.",
                "critical", cap=25))
        if got_402:
            signals.append(Signal("x402", +4,
                "Paid endpoint returns a proper 402 challenge (x402 correctly implemented).", "good"))
    else:
        signals.append(Signal("liveness", 0,
            "No callable endpoint (A2A-only or incomplete listing) — cannot verify delivery.",
            "warn", cap=60))

    # ---- OKX review + status (table stakes — small credit, big penalty if missing) ----
    approval = agent_info.get("approvalStatus")
    if approval == 4:
        signals.append(Signal("review", +6, "Passed OKX listing review.", "good"))
    else:
        signals.append(Signal("review", -12,
            f"Has NOT passed OKX review (approvalStatus={approval}).", "warn", cap=55))

    if agent_info.get("onlineStatus") == 1:
        signals.append(Signal("online", +3, "Marked online.", "good"))
    else:
        signals.append(Signal("online", -8, "Marked offline.", "warn"))

    if agent_info.get("status") != 1:
        signals.append(Signal("active", -25, "Agent is not active.", "critical", cap=25))

    # ---- Reputation — the EARNED signal that gates SAFE ----
    sales = int(agent_info.get("salesCount") or 0)
    if sales >= 100:
        signals.append(Signal("sales", +26, f"{sales} completed sales — strong, earned track record.", "good"))
    elif sales >= 10:
        signals.append(Signal("sales", +16, f"{sales} completed sales — real track record.", "good"))
    elif sales >= 1:
        signals.append(Signal("sales", +4,
            f"Only {sales} completed sale(s) — barely proven.", "warn", cap=69))
    else:
        signals.append(Signal("sales", 0,
            "No completed sales yet — live but UNPROVEN. Nobody has actually used it.",
            "warn", cap=64))

    sec_rate = _to_float(agent_info.get("securityRate"))
    if sec_rate is not None:
        delta = round((sec_rate - 3.0) * 6)
        signals.append(Signal("security_rating", delta,
            f"Security rating {sec_rate:.2f}/5.", "good" if delta >= 0 else "warn"))

    # ---- Anomaly detection (what a raw star-rating won't tell you) ----
    if sec_rate is not None and sec_rate >= 4.5 and sales == 0:
        signals.append(Signal("anomaly_rating", -6,
            "High rating with zero sales — reputation not earned through real usage.", "warn"))

    if not (agent_info.get("profileDescription") or "").strip():
        signals.append(Signal("effort", -4, "No profile description — low-effort or placeholder listing.", "warn"))

    lname = name.lower()
    if any(m in lname for m in _TEST_MARKERS):
        signals.append(Signal("test_account", -30,
            "Name resembles a test / placeholder account.", "critical", cap=20))

    # ---- Price sanity (per A2MCP service) ----
    for s in services:
        fee = _to_float(s.get("fee"))
        if fee is not None and fee > _FEE_SANE_MAX:
            signals.append(Signal("price", -8,
                f"Service '{s.get('serviceName')}' at {fee} USDT — well above marketplace norm.", "warn"))
            break

    # ---- Aggregate: additive, then apply the lowest cap ----
    raw = 50 + sum(s.delta for s in signals)
    caps = [s.cap for s in signals if s.cap is not None]
    ceiling = min(caps) if caps else 100
    score = max(0, min(100, min(raw, ceiling)))
    verdict = SAFE if score >= 70 else CAUTION if score >= 45 else BLOCK

    confidence = _confidence(agent_info, services, endpoints)
    reasons = _headline_reasons(signals, score, ceiling)
    evidence = {
        "isAsp": True,
        "sales": sales,
        "securityRate": sec_rate,
        "approvalStatus": approval,
        "onlineStatus": agent_info.get("onlineStatus"),
        "serviceCount": len(services),
        "endpoints": {e: _live_label(probes.get(e, {})) for e in endpoints},
        "cappedAt": ceiling if ceiling < raw else None,
    }

    v = Verdict(agent_id=aid, name=name, verdict=verdict, score=score,
                confidence=confidence, reasons=reasons,
                signals=[asdict(s) for s in signals], evidence=evidence)
    v.signature = _sign(v)
    return v


def _confidence(agent_info: dict, services: list[dict], endpoints: list) -> int:
    c = 0
    if agent_info.get("salesCount") is not None:
        c += 25
    if _to_float(agent_info.get("securityRate")) is not None:
        c += 20
    if endpoints:
        c += 25
    if agent_info.get("approvalStatus") is not None:
        c += 15
    if services:
        c += 15
    return min(100, c)


def _headline_reasons(signals: list[Signal], score: int, ceiling: int) -> list[str]:
    """The sharp, human-readable 'why' — criticals first, then the rest."""
    order = {"critical": 0, "warn": 1, "good": 2, "info": 3}
    ranked = sorted(signals, key=lambda s: (order.get(s.severity, 9), -abs(s.delta)))
    out = []
    for s in ranked:
        if s.delta == 0 and s.cap is None and s.severity == "info":
            continue
        mark = {"critical": "⛔", "warn": "⚠️", "good": "✅", "info": "ℹ️"}.get(s.severity, "•")
        out.append(f"{mark} {s.reason}")
    return out[:6]


def _sign(v: Verdict) -> str:
    payload = json.dumps(
        {"agent_id": v.agent_id, "verdict": v.verdict, "score": v.score},
        sort_keys=True, separators=(",", ":"),
    ).encode()
    return hmac.new(_SIGNING_KEY, payload, hashlib.sha256).hexdigest()[:32]


def _to_float(x: Any) -> float | None:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None
