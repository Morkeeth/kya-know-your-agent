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

-- Supply-side sybil index: which wallet controls which agents.
-- The marketplace search API does NOT expose ownerAddress, so a buyer browsing
-- OKX.AI cannot see that N "independent providers" are one wallet. Only
-- `agent get-agents` reveals it. We record it on every assess, so the index
-- self-populates from the sweep we already run (zero extra API calls).
CREATE TABLE IF NOT EXISTS agent_owners (
    agent_id TEXT PRIMARY KEY,
    owner    TEXT NOT NULL,
    name     TEXT,
    sold     INTEGER,
    seen_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_owners_owner ON agent_owners(owner);
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
        # Tool NAMES + DESCRIPTIONS are part of the fingerprint: a silent edit to a
        # tool description after approval (content rug-pull / tool poisoning) changes
        # the hash and triggers re-verification, which is where the scanner catches it.
        "manifest": sorted(f"{s.get('serviceName')}::{s.get('serviceDescription')}" for s in services),
        "profile": (agent_info or {}).get("profileDescription"),
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
    # A transition fires on any VERDICT move, whether the cause is a config change
    # (new services / sales) or a pure liveness flip (a patched dead endpoint —
    # the exact 're-verify' case, which state_hash deliberately excludes).
    verdict_moved = prev is not None and prev["verdict"] != verdict.verdict
    transition = None
    with _conn(path) as con:
        con.execute(
            "INSERT INTO verdicts(agent_id,state_hash,verdict,score,confidence,digest,issued_at,payload)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (verdict.agent_id, sh, verdict.verdict, verdict.score, verdict.confidence,
             verdict.digest, issued_at, json.dumps(verdict.to_dict())),
        )
        if verdict_moved:
            cause = "config changed" if changed else "liveness/endpoint changed"
            reason = f"{cause}; verdict {prev['verdict']} -> {verdict.verdict}"
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


UPTIME_WINDOW_DAYS = 7


def uptime(agent_id: str, path: str | None = None, min_samples: int = 5,
           window_days: int = UPTIME_WINDOW_DAYS) -> dict | None:
    """Rolling availability + P95 latency per endpoint, or None if too few samples.
    Returns {endpoint: {"uptime": 0..1, "p95_latency_ms": int|None, "samples": n}}.

    Windowed to the last `window_days` — the docstring always said "rolling", but the
    query had no bound, so this was a LIFETIME average and no sample ever aged out. That
    makes the metric unable to represent recovery: an endpoint that was down and is now
    up stays penalised roughly forever (measured: 151 consecutive healthy probes needed
    to clear 95% off a 1/9 history). A real window is also the honest alternative to
    deleting rows when a probe bug is found — bad samples age out on their own instead
    of a trust oracle editing its own history.

    Fails safe: too few samples in-window returns None, and the engine only penalises
    when history is present (engine.py `if history:`), so a sparse window never invents
    a penalty.
    """
    cutoff = int(time.time()) - window_days * 86400
    with _conn(path) as con:
        rows = con.execute(
            "SELECT endpoint, healthy, latency_ms FROM probe_samples "
            "WHERE agent_id=? AND ts>=?",
            (str(agent_id), cutoff),
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


def latest_per_agent(limit: int = 50, path: str | None = None) -> list[dict]:
    """The most recent verdict for each distinct agent — the Watchtower board.
    Uses SQLite's bare-column-with-MAX rule to pick the newest row per agent."""
    with _conn(path) as con:
        rows = con.execute(
            "SELECT agent_id, verdict, score, confidence, MAX(issued_at) AS issued_at, payload"
            " FROM verdicts GROUP BY agent_id ORDER BY issued_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["name"] = (json.loads(d.pop("payload") or "{}") or {}).get("name") or ""
        except (ValueError, TypeError):
            d["name"] = ""
        out.append(d)
    return out


def recent_changes(limit: int = 20, path: str | None = None) -> list[dict]:
    with _conn(path) as con:
        rows = con.execute(
            "SELECT agent_id,name,from_verdict,to_verdict,from_score,to_score,reason,at"
            " FROM transitions ORDER BY at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def record_owner(agent_id: str, owner: str, name: str | None = None,
                 sold: int | None = None, seen_at: int | None = None,
                 path: str | None = None) -> None:
    """Index agent -> owning wallet. Called on every assess, so the owner map fills
    in from the sweep we already run. Cheap, idempotent, no extra API calls."""
    owner = (owner or "").strip().lower()
    if not owner or not agent_id:
        return
    with _conn(path) as con:
        con.execute(
            "INSERT INTO agent_owners(agent_id,owner,name,sold,seen_at) VALUES(?,?,?,?,?)"
            " ON CONFLICT(agent_id) DO UPDATE SET owner=excluded.owner, name=excluded.name,"
            " sold=excluded.sold, seen_at=excluded.seen_at",
            (str(agent_id), owner, name, sold, int(seen_at if seen_at is not None else time.time())),
        )


def fleet_for(owner: str, path: str | None = None) -> dict | None:
    """What else does this wallet control, according to what KYA has actually seen?

    Deliberately reports KNOWN agents, never a claim about the whole marketplace:
    the index only contains agents we have verified, so an un-swept store
    undercounts. Undercounting is safe (the signal simply doesn't fire); inventing
    a total we haven't observed would be the exact staleness bug this codebase
    keeps getting bitten by. Returns None when the wallet is unknown.
    """
    owner = (owner or "").strip().lower()
    if not owner:
        return None
    with _conn(path) as con:
        rows = con.execute(
            "SELECT agent_id,name,sold FROM agent_owners WHERE owner=? ORDER BY CAST(agent_id AS INTEGER)",
            (owner,),
        ).fetchall()
    if not rows:
        return None
    members = [dict(r) for r in rows]
    return {
        "owner": owner,
        "known_agents": len(members),
        "zero_sale_agents": sum(1 for m in members if not (m.get("sold") or 0)),
        "total_sales": sum((m.get("sold") or 0) for m in members),
        "members": members,
    }


def operators(limit: int = 25, path: str | None = None) -> dict:
    """The marketplace ranked by WHO CONTROLS IT, not by agent.

    This is the view OKX's own marketplace cannot render: `agent search` never
    returns ownerAddress, so the UI can only ever show you N listings. Group those
    same listings by owner and the shape of the place changes completely.
    """
    with _conn(path) as con:
        rows = con.execute(
            "SELECT owner, COUNT(*) agents, SUM(COALESCE(sold,0)) sales,"
            " SUM(CASE WHEN COALESCE(sold,0)=0 THEN 1 ELSE 0 END) zero_sale"
            " FROM agent_owners GROUP BY owner"
            " ORDER BY agents DESC, sales DESC LIMIT ?",
            (limit,),
        ).fetchall()
        total_agents = con.execute("SELECT COUNT(*) c FROM agent_owners").fetchone()["c"]
        total_owners = con.execute("SELECT COUNT(DISTINCT owner) c FROM agent_owners").fetchone()["c"]
        out = []
        for r in rows:
            names = [x["name"] or "" for x in con.execute(
                "SELECT name FROM agent_owners WHERE owner=? LIMIT 200", (r["owner"],)).fetchall()]
            out.append({"owner": r["owner"], "agents": r["agents"], "sales": r["sales"],
                        "zero_sale": r["zero_sale"], "names": names})
    return {"operators": out, "total_agents": total_agents, "total_owners": total_owners}
