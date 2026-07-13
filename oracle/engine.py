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
import json
from dataclasses import dataclass, field, asdict
from typing import Any

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
    digest: str = ""   # sha256 of the canonical core; what the Ed25519 layer signs

    def to_dict(self) -> dict:
        return asdict(self)

    def canonical_core(self) -> str:
        """The stable payload that identifies this verdict — signed by the service."""
        return json.dumps(
            {"agent_id": self.agent_id, "verdict": self.verdict,
             "score": self.score, "confidence": self.confidence},
            sort_keys=True, separators=(",", ":"),
        )


def _live_label(probe: dict) -> str:
    if probe.get("reachable"):
        code = probe.get("status")
        return "live (x402 paywall)" if code == 402 else f"live (HTTP {code})"
    return "unreachable"


def score_agent(agent_info: dict | None, services: list[dict], probes: dict[str, dict],
                agent_id: str | None = None, *, malicious_hosts: list[str] | None = None,
                feedback: dict | None = None, owner_addrs: list[str] | None = None,
                history: dict | None = None, identity: dict | None = None) -> Verdict:
    """
    agent_info    : the `agentInfo` from `onchainos agent service-list` (may be None).
    services      : the `list` array (each has endpoint, fee, serviceType, ...).
    probes        : { endpoint_url: {"reachable": bool, "healthy": bool, ...} }.
    malicious_hosts : endpoint hosts flagged by OKX's phishing/blacklist scan (A1).
    feedback      : {reviewers:[addr], distribution, count} for reviewer audit (A2).
    owner_addrs   : the agent's own owner/wallet addresses (to catch self-review).
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
        v.digest = _digest(v)
        return v

    name = str(agent_info.get("name") or "").strip()
    aid = str(agent_info.get("agentId") or agent_id or "")
    signals: list[Signal] = []

    # ---- Liveness (a dead endpoint is the #1 real-world failure) ----
    # "healthy" (2xx/402, on-host) is what counts — a parked domain, a 404, or a
    # redirect off to google.com is NOT a working service. "reachable but not
    # healthy" and "timeout" are treated more softly than an outright refusal.
    endpoints = [s.get("endpoint") for s in services if s.get("endpoint")]
    if endpoints:
        n = len(endpoints)
        # An endpoint that resolves to internal / cloud-metadata space is refused by
        # the prober (SSRF guard) — a strong BLOCK signal: it can't be a real service
        # and is most likely a drainer probing the oracle's own infra.
        blocked = [e for e in endpoints if probes.get(e, {}).get("category") == "blocked"]
        if blocked:
            signals.append(Signal("ssrf", -50,
                f"{len(blocked)}/{n} endpoint(s) point at internal / non-public infrastructure — "
                f"refused to probe (SSRF-blocked); malicious or badly misconfigured.",
                "critical", cap=20))
        live = [e for e in endpoints if e not in blocked]  # scored for liveness
        m = len(live)
        healthy = [e for e in live if probes.get(e, {}).get("healthy")]
        reachable = [e for e in live if probes.get(e, {}).get("reachable")]
        got_402 = any(probes.get(e, {}).get("status") == 402 for e in live)
        kinds = {probes.get(e, {}).get("down_kind") for e in live}
        if m and len(healthy) == m:
            signals.append(Signal("liveness", +18, f"All {m} service endpoint(s) serving (2xx/402).", "good"))
        elif healthy:
            signals.append(Signal("liveness", +2,
                f"Only {len(healthy)}/{m} endpoints actually serving — partial outage.", "warn", cap=62))
        elif reachable:
            # Hosts answer but with 404/5xx or an off-host redirect: present, not serving.
            signals.append(Signal("liveness", -15,
                f"Endpoints respond but none serve a valid response (404/redirect) — likely broken.",
                "critical", cap=45))
        elif "timeout" in kinds and "refused" not in kinds:
            # Couldn't reach, but only via timeout — could be WAF/cold-start. Unverified, not proven-dead.
            signals.append(Signal("liveness", -12,
                f"Could not reach {m} endpoint(s) (timeout) — liveness unverified.", "warn", cap=58))
        elif m:
            signals.append(Signal("liveness", -40,
                f"None of {m} endpoint(s) reachable (connection refused) — service is DOWN.",
                "critical", cap=25))
        if got_402:
            signals.append(Signal("x402", +4,
                "Paid endpoint returns a proper 402 challenge (x402 correctly implemented).", "good"))

        # ---- Rolling uptime / latency from probe HISTORY (single-shot is a lie) ----
        # A single lucky probe can't tell a rock-solid endpoint from a flapping one.
        # Once we have samples, a low rolling availability caps SAFE and a slow P95
        # is a soft warning — this is the signal that only exists because we persist.
        if history:
            worst = min((h.get("uptime", 1.0) for h in history.values()), default=1.0)
            if worst < 0.95:
                signals.append(Signal("uptime", -14,
                    f"Rolling endpoint availability {worst:.0%} (<95%) — flapping/unreliable over time.",
                    "warn", cap=62))
            slow = max((h.get("p95_latency_ms") or 0 for h in history.values()), default=0)
            if slow >= 4000:
                signals.append(Signal("latency", -4,
                    f"P95 endpoint latency {slow}ms — degraded, technically-up service.", "warn"))
    else:
        signals.append(Signal("liveness", 0,
            "No callable endpoint (A2A-only or incomplete listing) — cannot verify delivery.",
            "warn", cap=60))

    # ---- OKX review + status (types coerced; ABSENT != inactive — treat as unknown) ----
    approval = _to_int(agent_info.get("approvalStatus"))
    if approval == 4:
        signals.append(Signal("review", +6, "Passed OKX listing review.", "good"))
    elif approval is not None:
        signals.append(Signal("review", -12,
            f"Has NOT passed OKX review (approvalStatus={approval}).", "warn", cap=55))

    online = _to_int(agent_info.get("onlineStatus"))
    if online == 1:
        signals.append(Signal("online", +3, "Marked online.", "good"))
    elif online is not None:
        signals.append(Signal("online", -8, "Marked offline.", "warn"))

    status = _to_int(agent_info.get("status"))
    if status is not None and status != 1:
        signals.append(Signal("active", -25, "Agent is not active.", "critical", cap=25))

    # ---- Reputation — EARNED settled VOLUME, not a raw (wash-tradeable) count ----
    # Raw salesCount is the cheapest signal to fake: wash-buy a 0.001-USDT service
    # 10x for ~$0.01 and you'd clear a count-based gate. So SAFE is gated on
    # settled volume (sales x median fee), and sub-cent sales cap at CAUTION.
    sales = _to_int(agent_info.get("salesCount")) or 0
    # Use the CHEAPEST fee you actually PAY (min non-zero), never the median: a
    # median is trivially inflated by listing an expensive decoy service that's
    # never sold, while the real wash-traded service stays sub-cent.
    paid_fees = [f for f in (_to_float(s.get("fee")) for s in services) if f is not None and f > 0]
    eff_fee = min(paid_fees) if paid_fees else None
    volume = sales * eff_fee if eff_fee is not None else 0.0
    vtxt = f" (~{volume:.2f} USDT settled @ ≥{eff_fee:g})" if eff_fee is not None else " (no paid pricing)"

    if sales == 0:
        signals.append(Signal("sales", 0,
            "No completed sales yet — live but UNPROVEN. Nobody has actually used it.",
            "warn", cap=64))
    elif sales < 10:
        signals.append(Signal("sales", +4,
            f"Only {sales} completed sale(s){vtxt} — barely proven.", "warn", cap=69))
    elif eff_fee is None:
        # Only free services — a free "sale" costs gas, so a count proves nothing.
        signals.append(Signal("sales", +2,
            f"{sales} sales but only free services — no paid track record to trust.", "warn", cap=69))
    elif eff_fee < 0.01:
        # Sub-cent pricing: USDT is cheap, so require a COUNT that's costly/effortful
        # to wash (100+ txs, likely distinct buyers) before it can clear SAFE.
        if sales >= 100:
            signals.append(Signal("sales", +22,
                f"{sales} sales{vtxt} — high count offsets sub-cent pricing.", "good"))
        else:
            signals.append(Signal("sales", +6,
                f"{sales} sub-cent sales{vtxt} — cheap to wash-trade at this count; unconvincing.",
                "warn", cap=69))
    else:
        # Real pricing (≥0.01): settled volume is the earned signal.
        if volume >= 5 and sales >= 20:
            signals.append(Signal("sales", +26,
                f"{sales} sales{vtxt} — strong, earned track record.", "good"))
        elif volume >= 0.5:
            signals.append(Signal("sales", +16, f"{sales} sales{vtxt} — real track record.", "good"))
        else:
            signals.append(Signal("sales", +6,
                f"{sales} sales but thin volume{vtxt} — unconvincing.", "warn", cap=69))

    sec_rate = _to_float(agent_info.get("securityRate"))
    if sec_rate is not None:
        delta = round((sec_rate - 3.0) * 6)
        signals.append(Signal("security_rating", delta,
            f"Security rating {sec_rate:.2f}/5.", "good" if delta >= 0 else "warn"))

    # ---- Reputation by SAMPLE-SIZE-AWARE positive fraction (Wilson lower bound) ----
    # A star AVERAGE hides its sample size: 2 perfect reviews should never look as
    # trustworthy as 100 consistent ones, yet a mean can't tell them apart. The
    # Wilson score lower bound is pulled toward zero when evidence is thin, so a
    # thinly- or mixed-reviewed agent CANNOT clear SAFE on reviews alone — "SAFE
    # must be EARNED" as a property of the estimator, not a hand-tuned delta.
    rc = _review_counts(feedback)
    if rc is not None:
        pos, n = rc
        wlb = wilson_lower_bound(pos, n)
        p = pos / n
        # REWARD only deep, consistent positives (the bound clears 0.55 only with
        # real volume behind it); thin-but-positive reviews add ~0 and let the
        # settled-volume gate decide — they must not PENALISE an honest new agent.
        delta = round(max(0.0, wlb - 0.55) * 26)          # 0 .. ~+12
        # CAP only on a genuine NEGATIVE proportion (real bad reviews with enough
        # sample to mean it), never on small-n uncertainty. This is the signal a
        # volume-only gate misses: 100 reviews that are 40% negative is risky even
        # with sales behind it.
        cap = 62 if (n >= 5 and p < 0.80) else None
        sev = "warn" if (cap is not None) else "good"
        detail = (f"{p:.0%} positive — mixed, capped below SAFE" if cap is not None
                  else f"Wilson-adjusted trust {wlb:.2f}")
        signals.append(Signal("reputation", delta,
            f"{pos}/{n} positive reviews — {detail}.", sev, cap=cap))

    # ---- A1: malicious endpoint (a LIVE endpoint can still be a drainer) ----
    if malicious_hosts:
        signals.append(Signal("malicious", -60,
            f"Endpoint flagged MALICIOUS by OKX security scan (phishing/drainer): {malicious_hosts[0]}.",
            "critical", cap=15))

    # ---- Anti-impersonation: endpoint-borrowing & fund-diversion (identity) ----
    # A LISTED, live, well-reviewed endpoint can belong to someone ELSE. KYA is
    # blind to that unless it checks who the endpoint says it is, and where it
    # sends the money. Absent evidence is neutral; a positive CONTRADICTION bites.
    if identity:
        if identity.get("domain_binding") == "match":
            signals.append(Signal("domain_binding", +6,
                "Endpoint is domain-bound to this agent (.well-known/agent-registration).", "good"))
        elif identity.get("domain_binding") == "mismatch":
            signals.append(Signal("domain_binding", -45,
                "Endpoint's .well-known registration names a DIFFERENT agent — "
                "endpoint-borrowing / impersonation.", "critical", cap=25))
        if identity.get("payto") == "match":
            signals.append(Signal("payto", +6,
                "x402 payment routes to the agent's registered wallet (payTo verified).", "good"))
        elif identity.get("payto") == "mismatch":
            signals.append(Signal("payto", -40,
                "x402 payment routes to a wallet that ISN'T the agent's registered one — "
                "fund diversion.", "critical", cap=25))

    # ---- A2: audit reputation by WHO reviewed, not the aggregate star average ----
    if feedback:
        reviewers = feedback.get("reviewers") or []
        owners = {a for a in (owner_addrs or []) if a}
        if owners and any(r in owners for r in reviewers):
            signals.append(Signal("self_review", -45,
                "Self-reviewed — a review comes from the agent's own wallet. Reputation is self-dealt.",
                "critical", cap=25))
        distinct = len(set(reviewers))
        if len(reviewers) >= 3 and distinct <= 2:
            signals.append(Signal("review_ring", -12,
                f"All {len(reviewers)} reviews come from only {distinct} address(es) — possible review ring.",
                "warn", cap=66))

    # ---- Anomaly detection (what a raw star-rating won't tell you) ----
    if sec_rate is not None and sec_rate >= 4.5 and sales == 0:
        signals.append(Signal("anomaly_rating", -6,
            "High rating with zero sales — reputation not earned through real usage.", "warn"))

    if not (agent_info.get("profileDescription") or "").strip():
        signals.append(Signal("effort", -4, "No profile description — low-effort or placeholder listing.", "warn"))

    # Test-marker only BLOCKs when also unproven, so a legit high-sales agent that
    # merely contains a marker word (e.g. "RiskControl Analytics") isn't nuked.
    lname = name.lower()
    if any(m in lname for m in _TEST_MARKERS) and sales == 0:
        signals.append(Signal("test_account", -30,
            "Name resembles a test / placeholder account and has no sales.", "critical", cap=20))

    # ---- Price sanity (per A2MCP service) ----
    for s in services:
        fee = _to_float(s.get("fee"))
        if fee is not None and fee > _FEE_SANE_MAX:
            signals.append(Signal("price", -8,
                f"Service '{s.get('serviceName')}' at {fee} USDT — well above marketplace norm.", "warn"))
            break

    # ---- Confidence gates the verdict: thin evidence can't earn SAFE ----
    confidence = _confidence(agent_info, services, endpoints)
    if confidence < 50:
        signals.append(Signal("low_confidence", 0,
            f"Only {confidence}% of trust signals available — too little evidence to clear.",
            "warn", cap=69))

    # ---- Aggregate: additive, then apply the lowest cap ----
    raw = 50 + sum(s.delta for s in signals)
    caps = [s.cap for s in signals if s.cap is not None]
    ceiling = min(caps) if caps else 100
    score = max(0, min(100, min(raw, ceiling)))
    verdict = SAFE if score >= 70 else CAUTION if score >= 45 else BLOCK

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
    v.digest = _digest(v)
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


def _digest(v: Verdict) -> str:
    return hashlib.sha256(v.canonical_core().encode()).hexdigest()


def _to_float(x: Any) -> float | None:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _to_int(x: Any) -> int | None:
    """Tolerant int: handles 4, "4", "4.0", 4.0 — anything the CLI might emit."""
    f = _to_float(x)
    return int(f) if f is not None else None


def wilson_lower_bound(pos: int, n: int, z: float = 1.96) -> float:
    """Lower bound of the Wilson score interval for a positive-rating fraction.

    Sample-size aware: with few reviews the uncertainty term dominates and the
    bound is pulled toward 0, so a 2/2 agent scores far below a 100/100 one even
    though both have a 100% average. Returns 0.0 for n <= 0. Range [0, 1].
    """
    if n <= 0:
        return 0.0
    p = pos / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = p + z2 / (2 * n)
    margin = z * (((p * (1 - p)) + z2 / (4 * n)) / n) ** 0.5
    return max(0.0, (centre - margin) / denom)


def _review_counts(feedback: dict | None) -> tuple[int, int] | None:
    """Extract (positive, total) review counts from a feedback payload, tolerating
    a few shapes so the Wilson term works regardless of exactly how OKX returns
    reviews: explicit {positive,total}, a star map {'5':x,'4':y,...} (4-5 = positive),
    or a good/bad split. Returns None when no rating counts are present (e.g. the
    A2 reviewer-integrity payload that only carries reviewer addresses)."""
    if not feedback:
        return None
    pos, tot = feedback.get("positive"), feedback.get("total")
    if pos is not None and tot:
        pos, tot = _to_int(pos), _to_int(tot)
        if pos is not None and tot:
            return max(0, pos), tot
    dist = feedback.get("distribution")
    if isinstance(dist, dict) and dist:
        stars: dict[int, int] = {}
        good = bad = None
        for k, val in dist.items():
            digits = "".join(ch for ch in str(k) if ch.isdigit())
            c = _to_int(val) or 0
            if digits:
                stars[int(digits)] = stars.get(int(digits), 0) + c
            elif str(k).lower() in ("good", "positive", "up"):
                good = (good or 0) + c
            elif str(k).lower() in ("bad", "negative", "down"):
                bad = (bad or 0) + c
        if stars:
            n = sum(stars.values())
            if n > 0:
                return sum(c for s, c in stars.items() if s >= 4), n
        if good is not None or bad is not None:
            n = (good or 0) + (bad or 0)
            if n > 0:
                return (good or 0), n
    return None


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2
