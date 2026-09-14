"""Upstream dead must never mean 'buyer pays, gets nothing' (2026-09-14, OKX unlisting).

Three invariants, all reproduced against production before this file existed:
  1. "agent wallet refresh token error" is recognised as an auth failure.
  2. /verify (free, listed) serves the last stored verdict marked stale, HTTP 200,
     instead of a 502, when the upstream read fails.
  3. /audit (paid) answers 503 before any 402 is minted while upstream is dead.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("KYA_DB_PATH", str(tmp_path / "kya.db"))
    for k in ("OKX_API_KEY", "OKX_SECRET_KEY", "OKX_PASSPHRASE", "KYA_AUDIT_PAYTO"):
        monkeypatch.delenv(k, raising=False)
    for m in [m for m in list(sys.modules) if m == "app" or m.startswith("oracle")]:
        del sys.modules[m]
    from oracle import store
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "kya.db"))
    import app as A
    from fastapi.testclient import TestClient
    return TestClient(A.app), A


def _seed_verdict(agent_id="2118"):
    from oracle import store
    from oracle.engine import score_agent
    ep = "https://svc.example.com/api"
    asp = dict(agentId=agent_id, name="Otto AI", approvalStatus=4, onlineStatus=1, status=1,
               salesCount=169, securityRate="4.75", profileDescription="does a thing")
    svc = [{"endpoint": ep, "fee": "0", "serviceType": "A2MCP", "serviceName": "Thing"}]
    v = score_agent(asp, svc, {ep: {"reachable": True, "status": 200, "healthy": True,
                                    "category": "json"}})
    store.record(v, "hash-1", issued_at=1_700_000_000)
    return v


def _kill_upstream(monkeypatch):
    from oracle import data
    def dead(args):
        raise RuntimeError('onchainos rc=1: {"ok":false,"error":"code=20003 msg=agent wallet '
                           'refresh token error"}')
    monkeypatch.setattr(data, "_run_onchainos", dead)
    data._probe_at[0] = 0.0
    data._cache.clear(); data._last_good.clear()


def test_refresh_token_error_is_an_auth_failure():
    from oracle.data import _looks_like_auth_failure
    assert _looks_like_auth_failure("code=20003 msg=agent wallet refresh token error")
    assert _looks_like_auth_failure("API Key trial expired. Please upgrade")


def test_verify_serves_last_stored_verdict_marked_stale(client, monkeypatch):
    c, A = client
    v = _seed_verdict()
    _kill_upstream(monkeypatch)
    r = c.get("/verify?agentId=2118")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stale"] is True
    assert body["verdict"] == v.verdict
    assert body["signature"] is None
    assert body["stale_issued_at"] == 1_700_000_000
    assert "refresh token" in body["upstream_error"]


def test_verify_still_502_when_nothing_stored(client, monkeypatch):
    c, A = client
    _kill_upstream(monkeypatch)
    r = c.get("/verify?agentId=424242")
    assert r.status_code == 502


def test_audit_refuses_before_402_while_upstream_dead(client, monkeypatch):
    c, A = client
    _kill_upstream(monkeypatch)
    r = c.get("/audit?agentId=2118")
    assert r.status_code == 503, r.text
    assert "payment-required" not in {k.lower() for k in r.headers}
    assert r.json()["error"] == "upstream_unavailable"
    assert r.headers.get("retry-after") == "600"


def test_health_goes_red_on_its_own(client, monkeypatch):
    c, A = client
    _kill_upstream(monkeypatch)
    r = c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["upstream_session"] == "expired"
    assert "refresh token" in body["upstream_last_error"]
