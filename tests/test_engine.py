"""
Verdict-engine tests — pure, no network. Each fixture is a hand-built marketplace
record + probe map, so these lock in the SCORING behavior (and the security
regressions the adversarial review surfaced).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle.engine import score_agent, SAFE, CAUTION, BLOCK  # noqa: E402


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


# ------------------------------------------------------------------- integrity
def test_digest_is_stable_and_present():
    ep = "https://svc.example.com/api"
    a = score_agent(_asp(salesCount=169), _svc(ep), _healthy(ep))
    b = score_agent(_asp(salesCount=169), _svc(ep), _healthy(ep))
    assert a.digest and a.digest == b.digest
