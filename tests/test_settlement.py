"""On-chain settlement reader + wash-detection tests (slice 5).

The reader is mocked via an injected `get`, so no network + no key needed. The
engine gate is exercised with synthetic wash vs organic settlement facts."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle.settlement import fetch_settlements, _extract_txs  # noqa: E402
from oracle.engine import score_agent, _identical_ratio, SAFE, CAUTION, BLOCK  # noqa: E402


def _healthy(url): return {url: {"reachable": True, "status": 402, "healthy": True, "category": "x402"}}


def _asp(**over):
    base = dict(agentId="999", name="Test Provider", approvalStatus=4, onlineStatus=1,
                status=1, salesCount=120, securityRate="4.5", profileDescription="x")
    base.update(over)
    return base


def _svc(ep="https://svc.example.com/api", fee="0.001"):
    return [{"endpoint": ep, "fee": fee, "serviceType": "A2MCP", "serviceName": "Thing"}]


# ------------------------------------------------------------- reader (mocked)
def _page(txs):
    return {"data": [{"transactionLists": txs}]}


def test_reader_aggregates_inbound_distinct_payers():
    wallet = "0xagent"
    calls = {"n": 0}

    def fake_get(path, params):
        calls["n"] += 1
        # first token/page: 3 inbound from 2 payers + 1 outbound (ignored); then empty
        if calls["n"] == 1:
            return _page([
                {"from": "0xBUYER1", "to": "0xAGENT", "amount": "1.0"},
                {"from": "0xbuyer2", "to": "0xagent", "amount": "2.0"},
                {"from": "0xbuyer1", "to": "0xagent", "amount": "0.5"},
                {"from": "0xagent", "to": "0xother", "amount": "9.0"},   # outbound, ignored
            ])
        return _page([])

    s = fetch_settlements(wallet, get=fake_get)
    assert s["distinct_payers"] == 2
    assert s["onchain_volume"] == 3.5
    assert s["tx_count"] == 3


def test_extract_txs_shapes():
    assert _extract_txs({"data": [{"transactionLists": [{"x": 1}]}]}) == [{"x": 1}]
    assert _extract_txs({"data": {"transactionList": [{"y": 2}]}}) == [{"y": 2}]
    assert _extract_txs({"data": []}) == []


def test_identical_ratio():
    assert _identical_ratio([1.0, 1.0, 1.0, 1.0]) == 1.0
    assert _identical_ratio([1, 2, 3, 4]) == 0.25
    assert _identical_ratio([]) == 0.0


# --------------------------------------------------------- engine wash gate
def test_organic_settlements_are_safe():
    """Many distinct payers, varied amounts, no single whale -> earned -> SAFE."""
    ep = "https://svc.example.com/api"
    payers = {f"0x{i:02d}": 1.0 + i * 0.3 for i in range(12)}
    s = {"distinct_payers": 12, "onchain_volume": sum(payers.values()),
         "payers": payers, "amounts": list(payers.values()), "tx_count": 12}
    v = score_agent(_asp(), _svc(ep), _healthy(ep), settlement=s)
    assert v.verdict == SAFE


def test_two_wallet_subcent_wash_is_capped():
    """The headline attack: 100x 0.001 from 2 wallets. distinct_payers=2, identical
    amounts -> caught by the on-chain gate and capped below SAFE."""
    ep = "https://svc.example.com/api"
    amounts = [0.001] * 100
    payers = {"0xa": 0.05, "0xb": 0.05}
    s = {"distinct_payers": 2, "onchain_volume": 0.1,
         "payers": payers, "amounts": amounts, "tx_count": 100}
    v = score_agent(_asp(salesCount=100), _svc(ep, "0.001"), _healthy(ep), settlement=s)
    assert v.verdict != SAFE, f"2-wallet wash reached {v.verdict} ({v.score})"


def test_single_whale_concentration_is_capped():
    ep = "https://svc.example.com/api"
    payers = {"0xwhale": 95.0, "0xb": 1.0, "0xc": 1.0}
    s = {"distinct_payers": 3, "onchain_volume": 97.0,
         "payers": payers, "amounts": [95.0, 1.0, 1.0], "tx_count": 3}
    v = score_agent(_asp(), _svc(ep), _healthy(ep), settlement=s)
    assert v.verdict != SAFE


def test_claimed_sales_no_settlements_is_capped():
    """Claims 120 sales but zero on-chain money behind them -> unproven, capped."""
    ep = "https://svc.example.com/api"
    s = {"distinct_payers": 0, "onchain_volume": 0.0, "payers": {}, "amounts": [], "tx_count": 0}
    v = score_agent(_asp(salesCount=120), _svc(ep), _healthy(ep), settlement=s)
    assert v.verdict != SAFE


def test_settlement_absent_is_neutral():
    """Default-off (settlement=None) must not change any verdict."""
    ep = "https://svc.example.com/api"
    a = score_agent(_asp(salesCount=300), _svc(ep, "0.10"), _healthy(ep))
    b = score_agent(_asp(salesCount=300), _svc(ep, "0.10"), _healthy(ep), settlement=None)
    assert a.verdict == b.verdict == SAFE and a.score == b.score


def test_usdt0_the_actual_x402_settlement_token_is_read():
    """Regression: the x402 rail settles in USD₮0, which was missing from _TOKENS.

    Verified on a real settled payment (tx 0x79b3dab1…, 2026-07-19): 0.1 moved through
    contract 0x779ded0c…. With that contract absent the reader queried only USDC/USDT,
    found nothing, and returned tx_count=0 — which the engine reads as "claimed sales
    aren't backed by money" and as washed. A lookup miss shaped like a fraud finding.
    """
    from oracle import settlement
    assert "0x779ded0c9e1022225f8e0630b35a9b54be713736" in settlement._TOKENS.values()

    seen: list[str] = []

    def fake_get(path, params):
        seen.append(params["tokenContractAddress"])
        return {"data": [{"transactionLists": []}]}

    settlement.fetch_settlements("0x237eee4017b0e496a67d1c886150c0b19f459975", get=fake_get)
    assert "0x779ded0c9e1022225f8e0630b35a9b54be713736" in seen


def test_flat_rate_pricing_is_not_by_itself_a_wash_signature():
    """KNOWN DEFECT, pinned so the decision is explicit rather than forgotten.

    An honest flat-price ASP with many distinct payers currently trips _looks_washed
    purely because a fixed price yields identical amounts. This test documents the
    CURRENT behaviour; flip the assertion when the predicate is fixed.
    """
    from oracle.engine import _looks_washed
    honest_flat = {
        "distinct_payers": 20,
        "payers": {f"0x{i:040x}": 0.1 for i in range(20)},
        "amounts": [0.1] * 20, "onchain_volume": 2.0, "tx_count": 20,
    }
    varied = dict(honest_flat, amounts=[round(0.1 + 0.01 * i, 2) for i in range(20)])
    assert _looks_washed(varied) is False           # 20 distinct payers = clearly organic
    assert _looks_washed(honest_flat) is True       # <- only difference is flat pricing
