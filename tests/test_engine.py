"""
Verdict-engine tests — pure, no network. Each fixture is a hand-built marketplace
record + probe map, so these lock in the SCORING behavior (and the security
regressions the adversarial review surfaced).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle.engine import (  # noqa: E402
    score_agent, wilson_lower_bound, _review_counts, SAFE, CAUTION, BLOCK,
)


def _healthy(url): return {url: {"reachable": True, "status": 402, "healthy": True, "category": "x402"}}
def _down(url):    return {url: {"reachable": False, "status": None, "healthy": False, "category": "down", "down_kind": "refused"}}
def _parked(url):  return {url: {"reachable": True, "status": 200, "healthy": False, "category": "parked"}}


def _asp(**over):
    base = dict(agentId="999", name="Test Provider", approvalStatus=4,
                onlineStatus=1, status=1, salesCount=0, securityRate="4.0",
                profileDescription="does a thing")
    base.update(over)
    return base


def _svc(endpoint="https://svc.example.com/api", fee="0.10"):
    return [{"endpoint": endpoint, "fee": fee, "serviceType": "A2MCP", "serviceName": "Thing"}]


# ---------------------------------------------------------------- proven -> SAFE
def test_proven_high_volume_is_safe():
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=169, securityRate="4.75"), _svc(ep, "0.10"), _healthy(ep))
    assert v.verdict == SAFE and v.score >= 70


def test_high_count_even_if_cheap_is_safe():
    # 656 sales is expensive to wash even at sub-cent price -> earned.
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=656), _svc(ep, "0.001"), _healthy(ep))
    assert v.verdict == SAFE


# ------------------------------------------------------------- unproven -> CAUTION
def test_zero_sales_live_is_caution_not_safe():
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=0), _svc(ep), _healthy(ep))
    assert v.verdict == CAUTION and v.score < 70


def test_one_sale_is_caution():
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=1), _svc(ep), _healthy(ep))
    assert v.verdict == CAUTION


# --------------------------------------------------- SECURITY REGRESSION: wash-trade
def test_wash_traded_cheap_sales_do_not_reach_safe():
    """10 x 0.001-USDT sales (~1 cent) must NOT unlock SAFE. This is the headline attack."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=10, securityRate="5.0"), _svc(ep, "0.001"), _healthy(ep))
    assert v.verdict != SAFE, f"wash-trade reached {v.verdict} ({v.score})"


def test_decoy_median_inflation_does_not_reach_safe():
    """Red-team #1: list an expensive DECOY service (never sold) to inflate the
    median, while wash-trading a sub-cent one. Must still not reach SAFE."""
    ep = "https://svc.example.com/api"
    services = [
        {"endpoint": ep, "fee": "0.001", "serviceType": "A2MCP", "serviceName": "Cheap (washed)"},
        {"endpoint": ep, "fee": "0.10", "serviceType": "A2MCP", "serviceName": "Decoy (never sold)"},
    ]
    v = score_agent(_asp(salesCount=10, securityRate="5.0"), services, _healthy(ep))
    assert v.verdict != SAFE, f"decoy-median wash reached {v.verdict} ({v.score})"


def test_free_service_high_count_does_not_reach_safe():
    """Red-team #4: 50 FREE 'sales' cost ~gas only — a count must not buy SAFE."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=50, securityRate="5.0"), _svc(ep, "0"), _healthy(ep))
    assert v.verdict != SAFE, f"free-service count reached {v.verdict} ({v.score})"


def test_real_priced_volume_is_safe():
    """Legit: 30 sales x 0.10 USDT = real settled volume -> SAFE."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=30), _svc(ep, "0.10"), _healthy(ep))
    assert v.verdict == SAFE


def _blocked(url): return {url: {"reachable": False, "status": None, "healthy": False,
                                 "category": "blocked", "down_kind": "blocked"}}


# --------------------------------------------- SSRF: internal-target endpoint (slice 2)
def test_ssrf_blocked_endpoint_forces_block_even_if_proven():
    """An endpoint the prober refused (resolves to internal/metadata infra) is a
    drainer/misconfig signal — BLOCK even on a high-sales agent."""
    ep = "http://169.254.169.254/latest/meta-data/"
    v = score_agent(_asp(salesCount=500), _svc(ep), _blocked(ep))
    assert v.verdict == BLOCK
    assert any(s["key"] == "ssrf" for s in v.signals)


# ------------------------------------------ anti-impersonation identity (slice 6)
def test_endpoint_borrowing_mismatch_forces_block():
    """The endpoint's .well-known names a DIFFERENT agent — B borrowed A's live
    endpoint to inherit its score. Caught -> BLOCK even with sales+liveness."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=300), _svc(ep), _healthy(ep),
                    identity={"domain_binding": "mismatch", "payto": "absent"})
    assert v.verdict == BLOCK
    assert any(s["key"] == "domain_binding" for s in v.signals)


def test_paytO_mismatch_is_neutral_not_block():
    """A payTo differing from the identity wallet is legit facilitator routing, not
    fund diversion — must NOT BLOCK a proven agent (regression: #2023 false BLOCK)."""
    ep = "https://svc.example.com/api"
    base = score_agent(_asp(salesCount=300), _svc(ep, "0.10"), _healthy(ep))
    mism = score_agent(_asp(salesCount=300), _svc(ep, "0.10"), _healthy(ep),
                       identity={"domain_binding": "absent", "payto": "mismatch"})
    assert mism.verdict == SAFE and mism.score == base.score


def test_identity_match_flags_but_stays_safe():
    """A verified domain-binding + payTo is a positive — agent stays SAFE, with flags."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=300), _svc(ep, "0.10"), _healthy(ep),
                    identity={"domain_binding": "match", "payto": "match"})
    assert v.verdict == SAFE
    keys = {s["key"] for s in v.signals}
    assert "domain_binding" in keys and "payto" in keys


def test_identity_absent_is_neutral_no_regression():
    """The common 2026 case: neither implemented. Must NOT change the verdict."""
    ep = "https://svc.example.com/api"
    base = score_agent(_asp(salesCount=300), _svc(ep, "0.10"), _healthy(ep))
    withid = score_agent(_asp(salesCount=300), _svc(ep, "0.10"), _healthy(ep),
                         identity={"domain_binding": "absent", "payto": "absent"})
    assert base.verdict == withid.verdict == SAFE and base.score == withid.score


# ----------------------------------------------------- A1: malicious endpoint
def test_malicious_endpoint_forces_block_even_if_proven():
    """A LIVE endpoint flagged by the phishing/blacklist scan must BLOCK, even on a
    500-sale, all-serving agent — liveness alone never catches a drainer."""
    ep = "https://drainer.example.com/api"
    v = score_agent(_asp(salesCount=500), _svc(ep), _healthy(ep),
                    malicious_hosts=["drainer.example.com"])
    assert v.verdict == BLOCK


# ------------------------------------------------ priced trust (max_safe_usd)
def test_max_safe_usd_earned_from_volume():
    """The dollar ceiling: BLOCK -> $0, unproven -> $0, a proven SAFE agent -> a positive
    amount scaled to its settled volume. Earned, never invented, and signed (in the digest)."""
    ep = "https://svc.example.com/api"
    blocked = score_agent(_asp(salesCount=500), _svc(ep), _down(ep))
    assert blocked.verdict == BLOCK and blocked.max_safe_usd == 0.0
    unproven = score_agent(_asp(salesCount=0), _svc(ep, "0.10"), _healthy(ep))
    assert unproven.max_safe_usd == 0.0                      # 0 sales -> 0 volume -> $0
    proven = score_agent(_asp(salesCount=300), _svc(ep, "0.10"), _healthy(ep))
    assert proven.verdict == SAFE and proven.max_safe_usd > 0
    # bigger proven volume -> bigger ceiling (monotonic in earned volume)
    bigger = score_agent(_asp(salesCount=900), _svc(ep, "0.10"), _healthy(ep))
    assert bigger.max_safe_usd > proven.max_safe_usd
    # the ceiling is inside the SIGNED payload (tamper-proof)
    assert "max_safe_usd" in proven.canonical_core()


# ------------------------------------------------ newly-registered-domain risk
def test_new_domain_caps_at_caution_not_block():
    """A <30d endpoint domain can't earn SAFE outright (phishing prior) but is NOT
    auto-blocked - a proven agent on a young domain lands CAUTION, not BLOCK/SAFE."""
    ep = "https://svc.example.com/api"
    assert score_agent(_asp(salesCount=300), _svc(ep), _healthy(ep)).verdict == SAFE
    young = score_agent(_asp(salesCount=300), _svc(ep), _healthy(ep),
                        domain_intel={"domain": "example.com", "age_days": 5, "source": "rdap"})
    assert young.verdict == CAUTION
    assert any(s["key"] == "domain_age" for s in young.signals)


def test_old_domain_no_penalty():
    ep = "https://svc.example.com/api"
    old = score_agent(_asp(salesCount=300), _svc(ep), _healthy(ep),
                      domain_intel={"domain": "example.com", "age_days": 800, "source": "rdap"})
    assert old.verdict == SAFE
    assert not any(s["key"] == "domain_age" for s in old.signals)


def test_domain_intel_absent_is_neutral():
    ep = "https://svc.example.com/api"
    base = score_agent(_asp(salesCount=300), _svc(ep), _healthy(ep))
    withn = score_agent(_asp(salesCount=300), _svc(ep), _healthy(ep),
                        domain_intel={"domain": "example.com", "age_days": None, "source": None})
    assert base.verdict == withn.verdict == SAFE and base.score == withn.score


# ------------------------------------------------ A2: reviewer-integrity audit
def test_self_review_is_not_safe():
    """A review coming from the agent's own wallet = self-dealt reputation -> not SAFE."""
    ep = "https://svc.example.com/api"
    owner = "0xabc"
    v = score_agent(_asp(salesCount=200, ownerAddress=owner), _svc(ep), _healthy(ep),
                    feedback={"reviewers": [owner, "0xother"], "count": 2},
                    owner_addrs=[owner])
    assert v.verdict != SAFE


def test_review_ring_caps_at_caution_when_unproven():
    """Many reviews from 1-2 addresses on a NOT-sales-proven agent = a ring -> CAUTION."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=2), _svc(ep, "0.10"), _healthy(ep),
                    feedback={"reviewers": ["0x1", "0x1", "0x1", "0x2"], "count": 4},
                    owner_addrs=["0xowner"])
    assert v.verdict == CAUTION


def test_review_ring_not_flagged_when_sales_proven():
    """Regression (Newsliquid #2135, 389 sales / 9 reviews from 2): a sales-proven agent
    is NOT flagged for a small concentrated review set - sales are the trust, not reviews."""
    ep = "https://svc.example.com/api"
    reviewers = ["0x1"] * 7 + ["0x2"] * 2                    # 9 reviews, 2 distinct
    v = score_agent(_asp(salesCount=389), _svc(ep, "0.10"), _healthy(ep),
                    feedback={"reviewers": reviewers, "count": len(reviewers)},
                    owner_addrs=["0xowner"])
    assert v.verdict == SAFE
    assert not any(s["key"] in ("review_ring", "review_concentration") for s in v.signals)


def test_proven_a2a_agent_not_capped_for_no_endpoint():
    """Regression (WorldCupCaller #1891, 174 sales, A2A-only): an A2A agent has no HTTP
    endpoint to probe, but real settled sales prove delivery - it must not cap at CAUTION."""
    v = score_agent(_asp(salesCount=174, securityRate="4.7"),
                    [{"serviceType": "A2A", "fee": "0.5"}], {})
    assert v.verdict == SAFE
    assert not any(s.get("cap") == 60 for s in v.signals)


def test_review_concentration_caps_larger_ring_when_unproven():
    """The gap the <=2 rule missed: 12 reviews from 4 wallets on a NOT-sales-proven agent
    (leaning on reviews) caps at CAUTION."""
    ep = "https://svc.example.com/api"
    reviewers = (["0x1"] * 5 + ["0x2"] * 4 + ["0x3"] * 2 + ["0x4"])  # 12 reviews, 4 distinct
    v = score_agent(_asp(salesCount=2), _svc(ep, "0.10"), _healthy(ep),
                    feedback={"reviewers": reviewers, "count": len(reviewers)},
                    owner_addrs=["0xowner"])
    assert v.verdict == CAUTION
    assert any(s["key"] == "review_concentration" for s in v.signals)


def test_concentration_does_not_punish_sales_proven_agent():
    """Regression: a sales-proven agent (like OKX's own Explorer #2023, 800+ sales) with
    concentrated reviews earns trust from SALES, not reviews - concentration must NOT bite."""
    ep = "https://svc.example.com/api"
    reviewers = (["0x1"] * 5 + ["0x2"] * 4 + ["0x3"] * 2 + ["0x4"])
    v = score_agent(_asp(salesCount=832), _svc(ep, "0.10"), _healthy(ep),
                    feedback={"reviewers": reviewers, "count": len(reviewers)},
                    owner_addrs=["0xowner"])
    assert v.verdict == SAFE
    assert not any(s["key"] == "review_concentration" for s in v.signals)


def test_diverse_reviews_do_not_penalize():
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=300), _svc(ep, "0.10"), _healthy(ep),
                    feedback={"reviewers": ["0x1", "0x2", "0x3", "0x4"], "count": 4},
                    owner_addrs=["0xowner"])
    assert v.verdict == SAFE


# ------------------------------------------------------------------ dead -> BLOCK
def test_dead_endpoint_is_block():
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=500), _svc(ep), _down(ep))
    assert v.verdict == BLOCK


def test_parked_or_broken_endpoint_not_safe():
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=500), _svc(ep), _parked(ep))
    assert v.verdict != SAFE


# ------------------------------------------------------------- non-ASP -> BLOCK
def test_non_asp_is_block():
    v = score_agent({}, [], {}, agent_id="1771")
    assert v.verdict == BLOCK
    assert v.evidence.get("isAsp") is False


def test_none_agent_info_is_block():
    v = score_agent(None, [], {}, agent_id="42")
    assert v.verdict == BLOCK


# --------------------------------------------------------- test-account handling
def test_test_account_zero_sales_is_block():
    v = score_agent(_asp(name="测试买家", salesCount=0), [], {})
    assert v.verdict == BLOCK


def test_marker_word_with_real_sales_not_nuked():
    # "RiskControl Analytics" is legit despite containing 'riskcontrol'.
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(name="RiskControl Analytics", salesCount=200), _svc(ep), _healthy(ep))
    assert v.verdict == SAFE


# ------------------------------------------------ type coercion / robustness (#6)
def test_missing_status_does_not_auto_block():
    ep = "https://svc.example.com/api"
    info = _asp(salesCount=200)
    del info["status"]
    v = score_agent(info, _svc(ep), _healthy(ep))
    assert v.verdict == SAFE  # absent status must be 'unknown', not 'inactive'


def test_string_typed_fields_are_handled():
    ep = "https://svc.example.com/api"
    info = _asp(salesCount="100", approvalStatus="4", onlineStatus="1", status="1")
    v = score_agent(info, _svc(ep), _healthy(ep))
    assert v.verdict == SAFE


def test_float_string_salescount_does_not_crash():
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount="150.0"), _svc(ep), _healthy(ep))
    assert v.verdict == SAFE


# ---------------------------------------------------------- confidence gate (#14)
def test_thin_evidence_cannot_be_safe():
    # No sales data, no rating, no approval, no endpoints -> low confidence -> cap.
    v = score_agent({"agentId": "5", "name": "Sparse", "salesCount": None},
                    [], {})
    assert v.verdict != SAFE


# ------------------------------------------ rolling uptime from history (slice 4)
def test_flapping_uptime_caps_below_safe():
    """A proven agent whose endpoint only serves 60% of the time over history is
    unreliable — the rolling-uptime signal caps it below SAFE even on a lucky probe."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=300), _svc(ep, "0.10"), _healthy(ep),
                    history={ep: {"uptime": 0.60, "p95_latency_ms": 200, "samples": 20}})
    assert v.verdict != SAFE, f"flapping endpoint reached {v.verdict} ({v.score})"


def test_solid_uptime_stays_safe():
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=300), _svc(ep, "0.10"), _healthy(ep),
                    history={ep: {"uptime": 0.99, "p95_latency_ms": 200, "samples": 20}})
    assert v.verdict == SAFE


# ------------------------------------ Wilson sample-size-aware reputation (slice 3)
def test_wilson_is_sample_size_aware():
    """The whole point: 2/2 perfect reviews must score FAR below 100/100 perfect
    ones, even though both are a 100% average."""
    thin = wilson_lower_bound(2, 2)
    thick = wilson_lower_bound(100, 100)
    assert 0.0 < thin < 0.45, thin          # pulled toward zero by uncertainty
    assert thick > 0.95, thick              # earned
    assert thick > thin


def test_wilson_zero_n_is_zero():
    assert wilson_lower_bound(0, 0) == 0.0
    assert wilson_lower_bound(5, 0) == 0.0


def test_wilson_mixed_reviews_below_clean():
    assert wilson_lower_bound(80, 100) < wilson_lower_bound(95, 100)


def test_review_counts_parses_star_distribution():
    assert _review_counts({"distribution": {"5": 90, "4": 5, "1": 5}}) == (95, 100)
    assert _review_counts({"positive": 8, "total": 10}) == (8, 10)
    assert _review_counts({"distribution": {"good": 7, "bad": 3}}) == (7, 10)
    # A2-only payload (reviewer addresses, no ratings) yields no counts.
    assert _review_counts({"reviewers": ["0x1"], "count": 1}) is None
    assert _review_counts({}) is None


def test_mixed_reviews_cap_an_otherwise_safe_agent():
    """The value the raw volume gate MISSES: an agent proven on sales but carrying
    a real proportion of negative reviews (60/100) is risky — capped below SAFE."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=300), _svc(ep, "0.10"), _healthy(ep),
                    feedback={"positive": 60, "total": 100})
    assert v.verdict != SAFE, f"mixed reviews reached {v.verdict} ({v.score})"


def test_thin_positive_reviews_do_not_penalise_a_proven_agent():
    """Few but genuine 5-star reviews must NOT drag a volume-proven agent down —
    small-sample uncertainty is not a negative signal (this was the Otto regression)."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=300), _svc(ep, "0.10"), _healthy(ep),
                    feedback={"positive": 2, "total": 2})
    assert v.verdict == SAFE


def test_deep_consistent_reviews_stay_safe():
    """95/100 positive reviews is earned trust — the Wilson term must NOT block it."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=300), _svc(ep, "0.10"), _healthy(ep),
                    feedback={"positive": 95, "total": 100})
    assert v.verdict == SAFE


# ------------------------------------------------------------------- integrity
def test_digest_is_stable_and_present():
    ep = "https://svc.example.com/api"
    a = score_agent(_asp(salesCount=169), _svc(ep), _healthy(ep))
    b = score_agent(_asp(salesCount=169), _svc(ep), _healthy(ep))
    assert a.digest and a.digest == b.digest


# ------------------------------------------------- A5: supply-side sybil (owner fleet)
# Ground truth these lock in (verified live 2026-07-15): wallet 0x3256c679…168d69
# controls 99 agents (Pulse/Edge/Depth/Cycle x ~19 tickers), 0x11f90417…810dfd another
# 75 cloning the same template. OKX's search API never exposes ownerAddress, so the
# marketplace itself cannot show a buyer that N "providers" are one wallet.

def _fleet(n, *, sales=0, stem="Pulse", owner="0xdead0000000000000000000000000000beef0001"):
    toks = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LINK", "AVAX", "DOT",
            "TRX", "LTC", "BCH", "ATOM", "NEAR", "FIL", "APT", "ARB", "OP", "MATIC"]
    members = [{"agent_id": str(900 + i), "name": f"{stem}{toks[i % len(toks)]}", "sold": 0}
               for i in range(n)]
    if sales and members:
        members[0]["sold"] = sales
    return {"owner": owner, "known_agents": n, "total_sales": sales,
            "zero_sale_agents": sum(1 for m in members if not m["sold"]), "members": members}


def _keys(v):
    return {s["key"] for s in v.signals}


def test_large_templated_zero_sale_fleet_is_flagged():
    """99 shells behind one wallet: not an independent provider."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=0), _svc(ep), _healthy(ep), fleet=_fleet(99))
    assert "owner_fleet" in _keys(v)
    assert v.verdict != SAFE
    assert "99" in " ".join(v.reasons)


def test_fleet_penalty_scales_with_size():
    """5 shells and 99 shells are different claims; the score must say so."""
    ep = "https://svc.example.com/api"
    small = score_agent(_asp(salesCount=0), _svc(ep), _healthy(ep), fleet=_fleet(6))
    big = score_agent(_asp(salesCount=0), _svc(ep), _healthy(ep), fleet=_fleet(99))
    assert big.score < small.score


def test_honest_multi_agent_operator_is_disclosed_not_penalised():
    """A real operator (SignalDesk's owner: 32 agents, real sales) keeps its reputation.
    Fleet size alone is NOT fraud — this is the false positive that would wreck KYA."""
    ep = "https://svc.example.com/api"
    f = _fleet(32, sales=69)
    v = score_agent(_asp(salesCount=42), _svc(ep), _healthy(ep), fleet=f)
    assert "owner_fleet" not in _keys(v)          # no penalty
    assert "owner_fleet_info" in _keys(v)         # but disclosed
    assert any(s["delta"] == 0 for s in v.signals if s["key"] == "owner_fleet_info")


def test_fleet_disclosure_is_visible_to_a_buyer():
    """A signal nobody reads is worthless: zero-delta info is normally filtered out."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=42), _svc(ep), _healthy(ep), fleet=_fleet(32, sales=69))
    assert any("Owner runs 32" in r for r in v.reasons)


def test_small_fleet_does_not_fire():
    """Below the threshold, running a couple of agents is just normal."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=0), _svc(ep), _healthy(ep), fleet=_fleet(3))
    assert "owner_fleet" not in _keys(v)


def test_agent_with_own_sales_escapes_fleet_penalty():
    """Self-healing: a shell that earns real settled volume stops being scored as one."""
    ep = "https://svc.example.com/api"
    f = _fleet(99)
    v = score_agent(_asp(salesCount=250), _svc(ep), _healthy(ep), fleet=f)
    assert "owner_fleet" not in _keys(v)


def test_no_fleet_data_changes_nothing():
    """Cold index / unknown wallet must be silent, never a guess."""
    ep = "https://svc.example.com/api"
    a = score_agent(_asp(salesCount=0), _svc(ep), _healthy(ep))
    b = score_agent(_asp(salesCount=0), _svc(ep), _healthy(ep), fleet=None)
    assert a.score == b.score
    assert "owner_fleet" not in _keys(a) and "owner_fleet" not in _keys(b)


# ---- cluster_risk: the fleet finding as a MACHINE-READABLE field, not just prose ----
# "1 wallet owns 99 agents" has to be something a calling agent can branch on, not a
# sentence it has to parse. evidence.cluster is that structured signal.

def test_cluster_field_flags_a_farm():
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=0), _svc(ep), _healthy(ep), fleet=_fleet(99))
    c = v.evidence.get("cluster")
    assert c is not None
    assert c["fleet_size"] == 99
    assert c["penalized"] is True
    assert c["risk"] == "high"
    assert c["owner"] == "0xdead0000000000000000000000000000beef0001"


def test_cluster_field_discloses_real_business_without_penalty():
    """A real 32-agent operator with sales: disclosed, but risk is NOT 'high'."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=42), _svc(ep), _healthy(ep), fleet=_fleet(32, sales=69))
    c = v.evidence.get("cluster")
    assert c is not None
    assert c["penalized"] is False
    assert c["risk"] == "disclosed"


def test_cluster_field_absent_without_fleet():
    """Unknown wallet -> no cluster claim at all (never invent one)."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=0), _svc(ep), _healthy(ep), fleet=None)
    assert v.evidence.get("cluster") is None


def test_cluster_field_absent_for_solo_operator():
    """A wallet KYA has only ever seen run ONE agent is not a cluster."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=0), _svc(ep), _healthy(ep), fleet=_fleet(1))
    assert v.evidence.get("cluster") is None


def test_distinct_names_never_trip_the_template_rule():
    """An operator with genuinely distinct names can't be convicted on naming alone."""
    from oracle.engine import _templated_count
    assert _templated_count(["Otto AI", "Newsliquid", "Barker Yield", "CoinAnk", "Argus"]) == 0
    assert _templated_count(["PulseBTC", "PulseETH", "PulseSOL", "EdgeBTC", "EdgeETH", "EdgeSOL"]) == 6


# ------------------------------------------------------- operators board (the view)
def test_operator_board_calls_a_farm_a_farm_and_spares_a_business():
    """The board must not just rank by size: 0x2e8e85c1 runs 32 agents WITH real
    customers and has to read as a business, not a farm."""
    from oracle.watchtower import _op_verdict
    farm = {"owner": "0xf", "agents": 99, "sales": 19,
            "names": [f"Pulse{t}" for t in ("BTC", "ETH", "SOL", "BNB", "XRP")] * 3}
    biz = {"owner": "0xb", "agents": 32, "sales": 69,
           "names": ["SignalDesk", "DefiMacro", "ChainPulse", "DepthCharge"]}
    thin = {"owner": "0xt", "agents": 4, "sales": 0, "names": ["A", "B", "C", "D"]}
    assert _op_verdict(farm) == ("BLOCK", "ONE OWNER")
    assert _op_verdict(biz) == ("SAFE", "BUSINESS")
    assert _op_verdict(thin) == ("CAUTION", "THIN")


def test_operator_rows_are_colour_coded_by_verdict():
    """Regression: the first cut passed the STAMP LABEL where the verdict was
    expected, so _eye fell through to its lime default and every row rendered
    identically — a board where a farm looks like a business is worse than no board."""
    from oracle.watchtower import _op_row, _C
    farm = _op_row({"owner": "0x" + "a" * 40, "agents": 99, "sales": 0,
                    "names": [f"Pulse{t}" for t in ("BTC", "ETH", "SOL")] * 2}, 1)
    biz = _op_row({"owner": "0x" + "b" * 40, "agents": 7, "sales": 30, "names": ["Otto"]}, 2)

    # The farm is nearly dark; the real business glows. ONE hue — a traffic light would
    # say "bad/good"; luminance says how much light the operator EARNED.
    assert _C["dark"] in farm and "ONE OWNER" in farm
    assert _C["lime"] in biz and "BUSINESS" in biz
    assert _C["dark"] not in biz


def test_the_board_never_uses_traffic_light_colours():
    """Amber/green/red status lights were the board's loudest vibe-code tell, and they were
    redundant — the eye's FORM already carries the verdict. Verdict must be encoded by hue-
    free luminance. If a second hue creeps back in, this fails."""
    from oracle.watchtower import _CSS, _C, _eye, _op_row

    surfaces = _CSS + "".join(_eye(v) for v in ("SAFE", "CAUTION", "BLOCK")) + _op_row(
        {"owner": "0x" + "c" * 40, "agents": 3, "sales": 1, "names": ["X"]}, 1)
    for banned in ("#F4B740", "#FF5247", "#D9F94C"):  # amber, red, the pre-brand lime
        assert banned not in surfaces, f"traffic-light colour {banned} is back on the board"

    # every verdict accent must be the SAME hue at different luminance
    assert len({_C["lime"], _C["dim"], _C["dark"]}) == 3


# ------------------------------------------------- volume basis: measured vs floor
# Ground truth (real agents, 2026-07-15): Otto #2118 = 220 sales across 40 services
# priced 0.001-0.15 (150x spread) -> floor $0.22 vs real takings nearer $11.
# Explorer #2023 = 941 sales, 19 services, 1.5e-05-7.5e-05 -> floor $0.0141.
# Median == min on BOTH (fee curves are skewed cheap), so "median fixes it" is false.

def _settle(vol, payers=6, amounts=None):
    """Build a settlement payload with the REAL shape: payers is {addr: total}, not a count.

    Two fixture bugs already caught by the engine here, both mine:
      1. six identical amounts -> correctly read as a replay wash, fell back to floor.
      2. distinct_payers=1 while the payer book held six addresses -> self-contradictory;
         the book, not the label, drives top-1 concentration.
    So: the book is DERIVED from `payers` and the amounts VARY. If a fixture has to lie to
    pass, the code is right and the test is wrong.
    """
    if amounts is None:
        share = vol / 6.0
        amounts = [share * m for m in (0.4, 0.7, 0.9, 1.1, 1.4, 1.5)]
    book: dict = {}
    for i, a in enumerate(amounts):
        addr = f"0x{(i % max(1, payers)):040x}"      # spread tx across exactly `payers` wallets
        book[addr] = book.get(addr, 0.0) + a
    return {"onchain_volume": vol, "distinct_payers": len(book),
            "payers": book, "amounts": amounts, "tx_count": len(amounts)}


def test_decoy_service_cannot_inflate_the_ceiling():
    """THE security property. Listing a service is free, so any statistic an attacker can
    RAISE by adding one is inflatable. Min is the unique fee statistic adding a service can
    only lower. Attack: wash-trade a 0.001 service, then list a 500-USDT decoy nobody buys."""
    from oracle.engine import _volume_basis
    honest, _, _, _ = _volume_basis(100, [0.001], None)
    with_decoy, _, _, _ = _volume_basis(100, [0.001, 500.0], None)
    assert with_decoy == honest == 0.1          # the decoy bought the attacker nothing
    # and the alternatives we rejected would have handed them the marketplace:
    import statistics
    assert 100 * statistics.median([0.001, 500.0]) == 25000.05


def test_measured_onchain_volume_beats_the_floor():
    """The real fix: stop estimating. Otto's floor is $0.22; measured says what moved."""
    from oracle.engine import _volume_basis
    vol, _, basis, txt = _volume_basis(220, [0.001, 0.15], _settle(11.03))
    assert basis == "measured" and vol == 11.03
    assert "distinct payers" in txt and "measured, not estimated" in txt


def test_washed_settlement_is_not_trusted_as_volume():
    """Measured only beats estimated when the money is real. One payer replaying an
    identical amount is not volume, it is a wash, and must NOT raise the ceiling."""
    from oracle.engine import _volume_basis
    v1, _, b1, _ = _volume_basis(100, [0.001], _settle(50.0, payers=1))
    assert b1 == "floor" and v1 == 0.1          # single payer -> ignored
    v2, _, b2, _ = _volume_basis(100, [0.001], _settle(50.0, payers=4, amounts=[12.5] * 8))
    assert b2 == "floor" and v2 == 0.1          # identical amounts replayed -> ignored


def test_floor_discloses_the_band_only_when_fees_actually_spread():
    """An honest multi-tier agent must not be silently libelled as unproven: say the
    number is a floor. But a uniform-fee agent has no ambiguity, so no noise."""
    from oracle.engine import _volume_basis
    _, _, _, wide = _volume_basis(220, [0.001, 0.15], None)
    _, _, _, flat = _volume_basis(390, [0.002, 0.002], None)
    assert "this is the floor" in wide and "0.001-0.15" in wide
    assert "floor" not in flat


def test_measured_ceiling_reaches_a_real_number():
    """End to end: the wedge only means something if measured volume moves the dollars."""
    ep = "https://svc.example.com/api"
    floor = score_agent(_asp(salesCount=220), _svc(ep, fee="0.001"), _healthy(ep))
    meas = score_agent(_asp(salesCount=220), _svc(ep, fee="0.001"), _healthy(ep),
                       settlement=_settle(11.03))
    assert meas.max_safe_usd > floor.max_safe_usd * 20
    assert meas.evidence["volumeBasis"] == "measured"
    assert floor.evidence["volumeBasis"] == "floor"


# --------------------------------------------- A5 hardening (found by hostile audit)
def test_one_wash_sale_per_shell_does_not_buy_immunity():
    """The adversarial pass broke the first cut for ~$0.10: it gated on `sales == 0`, so
    handing every shell ONE 0.001 sale bought total immunity for all 99. Judge the FLEET's
    economics and require the agent to EARN OUT in money, not sale counts."""
    ep = "https://svc.example.com/api"
    farm = {"owner": "0xf", "known_agents": 99, "total_sales": 19, "zero_sale_agents": 92,
            "members": [{"name": f"Pulse{t}", "sold": 0}
                        for t in ("BTC", "ETH", "SOL", "BNB", "XRP")] * 20}
    for s in (0, 1, 5, 50):
        v = score_agent(_asp(salesCount=s), _svc(ep, fee="0.001"), _healthy(ep), fleet=farm)
        assert "owner_fleet" in _keys(v), f"{s} token sales bought immunity"


def test_a_shell_that_actually_earns_out_escapes():
    """Self-healing must survive the hardening: real settled volume still clears you."""
    ep = "https://svc.example.com/api"
    farm = {"owner": "0xf", "known_agents": 99, "total_sales": 19, "zero_sale_agents": 92,
            "members": [{"name": f"Pulse{t}", "sold": 0}
                        for t in ("BTC", "ETH", "SOL", "BNB", "XRP")] * 20}
    v = score_agent(_asp(salesCount=600), _svc(ep, fee="0.001"), _healthy(ep), fleet=farm)
    assert "owner_fleet" not in _keys(v)


def test_unlaunched_startup_is_not_called_a_sybil_farm():
    """A real company can list several genuine agents before its first sale. Calling that a
    farm is defamation. 'No customers' alone convicts only at a size nobody launches
    honestly; a generated-name farm convicts at any size."""
    ep = "https://svc.example.com/api"
    newco = {"owner": "0xn", "known_agents": 6, "total_sales": 0, "zero_sale_agents": 6,
             "members": [{"name": n, "sold": 0} for n in
                         ("Ledgerly", "Quorum", "Tessellate", "Marrow", "Bindle", "Cormorant")]}
    v = score_agent(_asp(salesCount=0), _svc(ep), _healthy(ep), fleet=newco)
    assert "owner_fleet" not in _keys(v)        # not convicted
    assert "owner_fleet_info" in _keys(v)       # but the concentration is still disclosed

    big = {"owner": "0xb", "known_agents": 25, "total_sales": 0, "zero_sale_agents": 25,
           "members": [{"name": f"Distinct{i}", "sold": 0} for i in range(25)]}
    v2 = score_agent(_asp(salesCount=0), _svc(ep), _healthy(ep), fleet=big)
    assert "owner_fleet" in _keys(v2)           # 25 unsold distinct agents is not a startup


# ------------------------------------------------ the 63-hour bug: /verify must accept POST
def test_listed_free_service_returns_the_result_directly_not_402():
    """The #5290 contract, quoted from OKX's A2MCP guide rather than inferred:

        "① Free endpoint — returns the result directly on call; no billing, no x402."
        Self-check: `curl -i -X POST` -> "Free type ✅ expected: HTTP 200 + result"
        https://web3.okx.com/onchainos/dev-docs/okxai/howtomcp

    #5290 is registered fee "0", so /verify is FREE and MUST answer 200 with the verdict.
    It was rejected 2026-07-17 for exactly this: a 402 on a fee-0 service failed x402
    validation AND timed out the platform's test (it will not pay a free service, so it
    waited). The gate was added because approved fee-0 SlowMist #2155 was seen returning
    402/amount:"0" — evidence of what is TOLERATED, promoted to a rule without reading the
    one sentence that says the opposite. x402 lives on the PAID tier (/audit) only.
    """
    from fastapi.testclient import TestClient
    import app as A
    c = TestClient(A.app)

    for verb in ("get", "post"):
        r = getattr(c, verb)("/verify", params={"agentId": "2118"})
        assert r.status_code == 200, f"{verb} on the FREE service must be 200, got {r.status_code}"
        assert r.json()["verdict"] in ("SAFE", "CAUTION", "BLOCK")
        assert "payment-required" not in r.headers, "a fee-0 service must not issue a challenge"

    assert c.get("/watchtower").status_code == 200
    assert c.get("/operators").status_code == 200


def test_jsonrpc_id_is_never_mistaken_for_an_agent_id():
    """An MCP/JSON-RPC handshake was being answered with a real BLOCK verdict for "agent 1":
    `{"jsonrpc":"2.0","id":1,"method":"initialize"}` -> the `id` fallback read 1 as an agent
    id. A client that got a verdict instead of a protocol reply could not proceed, which is
    one half of "unable to receive a response from your Agent" (measured 2026-07-17)."""
    from fastapi.testclient import TestClient
    import app as A
    c = TestClient(A.app)

    r = c.post("/verify", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    body = r.json()
    assert body.get("agent_id") != "1", "JSON-RPC request id leaked in as an agent id"

    # a plain body may still use bare `id` as a convenience alias
    r2 = c.post("/verify", json={"id": "2118"})
    assert r2.status_code == 200 and r2.json()["agent_id"] == "2118"


def test_cap_disclosure_names_the_signal_holding_the_score_down():
    """A bare 69 cannot distinguish "clean but unproven" from "several things wrong".

    Full-marketplace sweep 2026-07-19: 213 of 578 agents landed on exactly 64 or 69 — the
    two sales caps — with EMPTY bins at 65/67/68 and 70-73. For most agents the score IS
    the sales cap wearing a number, while security rating, uptime, domain age and x402
    correctness are computed and then flattened. Publishing the binding signal restores
    that information without weakening the cap.
    """
    from oracle.engine import score_agent
    # A clean, well-behaved agent that simply has no sales yet.
    info = {"name": "Clean", "salesCount": 0, "status": 1, "onlineStatus": 1,
            "approvalStatus": 4, "securityRate": "4.8"}
    services = [{"serviceName": "s", "fee": 0.1,
                 "endpoint": "https://example.com/a"}]
    probes = {"https://example.com/a": {"reachable": True, "healthy": True,
                                        "status": 402, "latency_ms": 50}}
    v = score_agent(info, services, probes, agent_id="1")
    ev = v.evidence
    assert ev["cappedAt"] is not None, "a no-sales agent must be capped"
    assert ev["cappedBy"], "the binding signal must be named, not just its value"
    assert "sales" in ev["cappedBy"]
    assert ev["uncappedScore"] > v.score, "must show what it would have scored"
    # and the human-readable list must say so in words
    assert any("capped at" in r and "sales" in r for r in v.reasons)
