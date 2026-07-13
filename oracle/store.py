"""
Persistence layer — KYA's memory. A verdict is only trustworthy inside its signed
TTL, so trust DECAYS and must be RE-VERIFIED. This store gives KYA three things a
single-shot oracle can't have:

  1. History      — every verdict it ever issued, keyed by a hash of the agent's
                    mutable state, so we can tell "same agent, re-checked" from
                    "the agent changed".
  2. Re-run-on-patch — when an agent's state hash changes (it patched a dead
                    endpoint, gained sales, got new reviews), the next assess()
                    records a TRANSITION (e.g. BLOCK -> SAFE) instead of silently
                    overwriting. A patched agent gets a fresh verdict, not a stale one.
  3. Liveness history — per-endpoint probe samples, so the engine can score rolling
                    uptime / latency instead of a single lucky probe.

SQLite (stdlib) is enough. The path is configurable; on an ephemeral host (Railway)
point KYA_DB_PATH at a mounted volume to survive redeploys.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager

DB_PATH = os.environ.get("KYA_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "kya.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS verdicts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id   TEXT    NOT NULL,
    state_hash TEXT    NOT NULL,
    verdict    TEXT    NOT NULL,
    score      INTEGER NOT NULL,
    confidence INTEGER NOT NULL,
    digest     TEXT,
    issued_at  INTEGER NOT NULL,
    payload    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_verdicts_agent ON verdicts(agent_id, issued_at DESC);

CREATE TABLE IF NOT EXISTS transitions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id     TEXT    NOT NULL,
    name         TEXT,
    from_verdict TEXT    NOT NULL,
    to_verdict   TEXT    NOT NULL,
    from_score   INTEGER,
    to_score     INTEGER,
    reason       TEXT,
    at           INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_transitions_at ON transitions(at DESC);

CREATE TABLE IF NOT EXISTS probe_samples (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id   TEXT    NOT NULL,
    endpoint   TEXT    NOT NULL,
    ts         INTEGER NOT NULL,
    category   TEXT,
    status     INTEGER,
    healthy    INTEGER NOT NULL,
    latency_ms INTEGER
);
CREATE INDEX IF NOT EXISTS ix_probe_agent ON probe_samples(agent_id, endpoint, ts DESC);
"""


@contextmanager
def _conn(path: str | None = None):
    con = sqlite3.connect(path or DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(_SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


def state_hash(agent_info: dict | None, services: list[dict], feedback: dict | None) -> str:
    """A stable fingerprint of the agent's MUTABLE, trust-relevant state. Two calls
    return the same hash iff nothing that could change the verdict has changed — so a
    differing hash is exactly the "the agent patched something, re-verify" trigger.
    Deliberately excludes volatile probe results (those live in probe_samples)."""
    core = {
        "endpoints": sorted(s.get("endpoint") for s in services if s.get("endpoint")),
        "fees": sorted(str(s.get("fee")) for s in services),
        "services": len(services),
        "salesCount": (agent_info or {}).get("salesCount"),
        "securityRate": (agent_info or {}).get("securityRate"),
        "approvalStatus": (agent_info or {}).get("approvalStatus"),
        "onlineStatus": (agent_info or {}).get("onlineStatus"),
        "status": (agent_info or {}).get("status"),
        "reviewers": sorted((feedback or {}).get("reviewers") or []),
        "reviewCount": (feedback or {}).get("count"),
    }
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def last_verdict(agent_id: str, path: str | None = None) -> dict | None:
    """The most recent stored verdict for an agent, or None."""
    with _conn(path) as con:
        row = con.execute(
            "SELECT * FROM verdicts WHERE agent_id=? ORDER BY issued_at DESC, id DESC LIMIT 1",
            (str(agent_id),),
        ).fetchone()
    return dict(row) if row else None


def record(verdict, sh: str, issued_at: int | None = None, path: str | None = None) -> dict:
    """Persist a verdict and, if the state hash changed since the last one, record a
    transition. Returns {"changed": bool, "previous": <verdict str|None>,
    "transition": <dict|None>} so the caller can surface "re-verified / it moved"."""
    issued_at = int(issued_at if issued_at is not None else time.time())
    prev = last_verdict(verdict.agent_id, path)
    changed = prev is not None and prev["state_hash"] != sh
    transition = None
    with _conn(path) as con:
        con.execute(
            "INSERT INTO verdicts(agent_id,state_hash,verdict,score,confidence,digest,issued_at,payload)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (verdict.agent_id, sh, verdict.verdict, verdict.score, verdict.confidence,
             verdict.digest, issued_at, json.dumps(verdict.to_dict())),
        )
        if changed and prev["verdict"] != verdict.verdict:
            reason = f"state changed; verdict {prev['verdict']} -> {verdict.verdict}"
            con.execute(
                "INSERT INTO transitions(agent_id,name,from_verdict,to_verdict,from_score,to_score,reason,at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (verdict.agent_id, verdict.name, prev["verdict"], verdict.verdict,
                 prev["score"], verdict.score, reason, issued_at),
            )
            transition = {"from": prev["verdict"], "to": verdict.verdict,
                          "from_score": prev["score"], "to_score": verdict.score, "at": issued_at}
    return {"changed": changed, "previous": prev["verdict"] if prev else None,
            "previous_state_hash": prev["state_hash"] if prev else None, "transition": transition}


def record_probes(agent_id: str, probes: dict[str, dict], ts: int | None = None,
                  path: str | None = None) -> None:
    ts = int(ts if ts is not None else time.time())
    with _conn(path) as con:
        con.executemany(
            "INSERT INTO probe_samples(agent_id,endpoint,ts,category,status,healthy,latency_ms)"
            " VALUES(?,?,?,?,?,?,?)",
            [(str(agent_id), ep, ts, p.get("category"), p.get("status"),
              1 if p.get("healthy") else 0, p.get("latency_ms")) for ep, p in probes.items()],
        )


def uptime(agent_id: str, path: str | None = None, min_samples: int = 5) -> dict | None:
    """Rolling availability + P95 latency per endpoint, or None if too few samples.
    Returns {endpoint: {"uptime": 0..1, "p95_latency_ms": int|None, "samples": n}}."""
    with _conn(path) as con:
        rows = con.execute(
            "SELECT endpoint, healthy, latency_ms FROM probe_samples WHERE agent_id=?",
            (str(agent_id),),
        ).fetchall()
    by_ep: dict[str, list] = {}
    for r in rows:
        by_ep.setdefault(r["endpoint"], []).append((r["healthy"], r["latency_ms"]))
    out = {}
    for ep, samples in by_ep.items():
        if len(samples) < min_samples:
            continue
        up = sum(h for h, _ in samples) / len(samples)
        lats = sorted(l for _, l in samples if l is not None)
        p95 = lats[min(len(lats) - 1, int(0.95 * len(lats)))] if lats else None
        out[ep] = {"uptime": round(up, 3), "p95_latency_ms": p95, "samples": len(samples)}
    return out or None


def history(agent_id: str, limit: int = 20, path: str | None = None) -> list[dict]:
    with _conn(path) as con:
        rows = con.execute(
            "SELECT verdict,score,confidence,state_hash,issued_at FROM verdicts"
            " WHERE agent_id=? ORDER BY issued_at DESC, id DESC LIMIT ?",
            (str(agent_id), limit),
        ).fetchall()
    return [dict(r) for r in rows]


def recent_changes(limit: int = 20, path: str | None = None) -> list[dict]:
    with _conn(path) as con:
        rows = con.execute(
            "SELECT agent_id,name,from_verdict,to_verdict,from_score,to_score,reason,at"
            " FROM transitions ORDER BY at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
