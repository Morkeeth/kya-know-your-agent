"""Persistence / re-run-on-patch tests — the memory that makes trust a timeline.

Uses a temp DB per test (no shared state, no network)."""
import sys
import time
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


def test_pure_liveness_flip_records_transition(tmp_path):
    """A patched dead endpoint moves the verdict with the SAME marketplace state
    hash — the transition must still fire (this is the demo-hero case)."""
    db = _db(tmp_path)
    store.record(_V("42", "BLOCK", 20), "same_hash", issued_at=1000, path=db)
    r = store.record(_V("42", "SAFE", 80), "same_hash", issued_at=2000, path=db)
    assert r["changed"] is False               # config didn't change...
    assert r["transition"]["from"] == "BLOCK" and r["transition"]["to"] == "SAFE"  # ...but verdict did


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
    now = int(time.time())
    # 4 samples < min -> None
    for i in range(4):
        store.record_probes("2118", {ep: {"category": "api", "status": 200, "healthy": True,
                                           "latency_ms": 100}}, ts=now - 100 + i, path=db)
    assert store.uptime("2118", path=db) is None
    # add a 5th, one of them unhealthy -> uptime = 4/5, p95 present
    store.record_probes("2118", {ep: {"category": "down", "status": None, "healthy": False,
                                       "latency_ms": None}}, ts=now - 95, path=db)
    up = store.uptime("2118", path=db)
    assert up and up[ep]["samples"] == 5 and up[ep]["uptime"] == 0.8


def test_uptime_is_windowed_so_stale_failures_age_out(tmp_path):
    """The window is what lets a recovered endpoint stop being punished.

    Regression for the KYA self-scoring incident: a blocked event loop made the server
    time out on its OWN probes, recording false unhealthy rows. With an unbounded query
    those rows were permanent (1/9 needed 151 consecutive healthy probes to clear 95%).
    Windowed, they age out — no row deletion, no oracle editing its own history.
    """
    db = _db(tmp_path)
    ep = "https://a.com/x"
    now = int(time.time())
    old = now - 30 * 86400          # 30d ago: outside the 7d window
    # 9 stale failures + 1 stale success — the corrupted history
    for i in range(9):
        store.record_probes("2118", {ep: {"category": "down", "status": None,
                                          "healthy": False, "latency_ms": None}},
                            ts=old + i, path=db)
    # Outside the window entirely -> no signal at all, rather than a stale penalty.
    assert store.uptime("2118", path=db) is None
    # Fresh healthy probes inside the window are judged on their own merit.
    for i in range(5):
        store.record_probes("2118", {ep: {"category": "api", "status": 200,
                                          "healthy": True, "latency_ms": 120}},
                            ts=now - 60 + i, path=db)
    up = store.uptime("2118", path=db)
    assert up and up[ep]["samples"] == 5 and up[ep]["uptime"] == 1.0
    # And the unbounded query would have said 5/14 = 0.357 — the bug this pins.


# ------------------------------------------------------------- owner index (A5)
def test_owner_index_round_trip(tmp_path):
    p = str(tmp_path / "t.db")
    store.record_owner("1", "0xAAA", name="PulseBTC", sold=0, path=p)
    store.record_owner("2", "0xaaa", name="PulseETH", sold=3, path=p)
    store.record_owner("3", "0xBBB", name="Otto", sold=99, path=p)
    f = store.fleet_for("0xaaa", path=p)
    assert f["known_agents"] == 2          # case-insensitive: 0xAAA and 0xaaa are one wallet
    assert f["total_sales"] == 3
    assert f["zero_sale_agents"] == 1
    assert {m["name"] for m in f["members"]} == {"PulseBTC", "PulseETH"}


def test_unknown_owner_is_none_not_a_guess(tmp_path):
    """An un-swept store must undercount silently, never invent a total."""
    p = str(tmp_path / "t.db")
    assert store.fleet_for("0xnever-seen", path=p) is None
    assert store.fleet_for("", path=p) is None


def test_record_owner_is_idempotent(tmp_path):
    """Re-sweeping must update in place, not inflate the fleet count."""
    p = str(tmp_path / "t.db")
    for _ in range(5):
        store.record_owner("1", "0xAAA", name="PulseBTC", sold=0, path=p)
    store.record_owner("1", "0xAAA", name="PulseBTC", sold=7, path=p)
    f = store.fleet_for("0xAAA", path=p)
    assert f["known_agents"] == 1
    assert f["total_sales"] == 7


def test_operators_ranks_by_control(tmp_path):
    p = str(tmp_path / "t.db")
    for i in range(9):
        store.record_owner(str(i), "0xFARM", name=f"Pulse{i}", sold=0, path=p)
    store.record_owner("90", "0xREAL", name="Otto", sold=200, path=p)
    d = store.operators(limit=5, path=p)
    assert d["total_agents"] == 10 and d["total_owners"] == 2
    assert d["operators"][0]["owner"] == "0xfarm"      # most agents first
    assert d["operators"][0]["agents"] == 9
    assert d["operators"][0]["zero_sale"] == 9
