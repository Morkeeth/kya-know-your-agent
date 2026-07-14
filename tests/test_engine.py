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


def test_review_ring_caps_at_caution():
    """Many reviews from only 1-2 addresses = a ring -> capped at CAUTION."""
    ep = "https://svc.example.com/api"
    v = score_agent(_asp(salesCount=300), _svc(ep, "0.10"), _healthy(ep),
                    feedback={"reviewers": ["0x1", "0x1", "0x1", "0x2"], "count": 4},
                    owner_addrs=["0xowner"])
    assert v.verdict == CAUTION


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
