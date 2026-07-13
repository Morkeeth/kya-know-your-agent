"""Persistence / re-run-on-patch tests — the memory that makes trust a timeline.

Uses a temp DB per test (no shared state, no network)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle import store  # noqa: E402


class _V:  # minimal stand-in for a Verdict (only the fields store.record reads)
    def __init__(self, agent_id, verdict, score, name="Test", confidence=100, digest="d"):
        self.agent_id, self.verdict, self.score = agent_id, verdict, score
        self.name, self.confidence, self.digest = name, confidence, digest

    def to_dict(self):
        return {"agent_id": self.agent_id, "verdict": self.verdict, "score": self.score}


def _db(tmp_path):
    return str(tmp_path / "kya.db")


# ------------------------------------------------------------------- state hash
def test_state_hash_stable_and_change_sensitive():
    info = {"salesCount": 10, "securityRate": "4.0", "approvalStatus": 4}
    svc = [{"endpoint": "https://a.com/x", "fee": "0.10"}]
    fb = {"reviewers": ["0x1"], "count": 1}
    h1 = store.state_hash(info, svc, fb)
    assert h1 == store.state_hash(dict(info), list(svc), dict(fb))          # stable
    assert h1 != store.state_hash({**info, "salesCount": 11}, svc, fb)      # sales moved
    assert h1 != store.state_hash(info, [{"endpoint": "https://a.com/y", "fee": "0.10"}], fb)  # endpoint
    assert h1 != store.state_hash(info, svc, {"reviewers": ["0x1", "0x2"], "count": 2})        # reviews


# --------------------------------------------------------- persistence roundtrip
def test_record_and_last_verdict_survive_reconnect(tmp_path):
    db = _db(tmp_path)
    store.record(_V("2118", "SAFE", 100), "hashA", issued_at=1000, path=db)
    # a fresh connection == a process restart; the row must still be there.
    last = store.last_verdict("2118", path=db)
    assert last["verdict"] == "SAFE" and last["state_hash"] == "hashA"


# ------------------------------------------------------ re-run-on-patch transition
def test_state_change_records_transition(tmp_path):
    db = _db(tmp_path)
    # first look: a dead-endpoint agent -> BLOCK
    r1 = store.record(_V("3820", "BLOCK", 44, name="Sentiment"), "hash_dead", issued_at=1000, path=db)
    assert r1["changed"] is False and r1["transition"] is None
    # agent PATCHES its endpoint -> new state hash, now SAFE
    r2 = store.record(_V("3820", "SAFE", 82, name="Sentiment"), "hash_live", issued_at=2000, path=db)
    assert r2["changed"] is True
    assert r2["transition"]["from"] == "BLOCK" and r2["transition"]["to"] == "SAFE"
    changes = store.recent_changes(path=db)
    assert changes and changes[0]["from_verdict"] == "BLOCK" and changes[0]["to_verdict"] == "SAFE"


def test_same_state_is_not_a_change(tmp_path):
    db = _db(tmp_path)
    store.record(_V("2118", "SAFE", 100), "hashA", issued_at=1000, path=db)
    r = store.record(_V("2118", "SAFE", 100), "hashA", issued_at=2000, path=db)
    assert r["changed"] is False and r["transition"] is None
    assert len(store.history("2118", path=db)) == 2   # still logged (a timeline)


# -------------------------------------------------------------- uptime / latency
def test_uptime_needs_min_samples_then_computes(tmp_path):
    db = _db(tmp_path)
    ep = "https://a.com/x"
    # 4 samples < min -> None
    for i in range(4):
        store.record_probes("2118", {ep: {"category": "api", "status": 200, "healthy": True,
                                           "latency_ms": 100}}, ts=i, path=db)
    assert store.uptime("2118", path=db) is None
    # add a 5th, one of them unhealthy -> uptime = 4/5, p95 present
    store.record_probes("2118", {ep: {"category": "down", "status": None, "healthy": False,
                                       "latency_ms": None}}, ts=5, path=db)
    up = store.uptime("2118", path=db)
    assert up and up[ep]["samples"] == 5 and up[ep]["uptime"] == 0.8
