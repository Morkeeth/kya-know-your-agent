"""
I/O layer: pull an ASP's marketplace record via the `onchainos` CLI and probe
its endpoints for liveness. Kept separate from engine.py so scoring stays pure.
"""
from __future__ import annotations

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

import httpx

ONCHAINOS_BIN = os.environ.get("ONCHAINOS_BIN", "onchainos")
_PROBE_TIMEOUT = float(os.environ.get("PROBE_TIMEOUT", "4.0"))


class AgentNotFound(Exception):
    pass


def fetch_agent(agent_id: str) -> tuple[dict, list[dict]]:
    """Return (agent_info, services) for an agentId. Raises AgentNotFound."""
    try:
        proc = subprocess.run(
            [ONCHAINOS_BIN, "agent", "service-list", "--agent-id", str(agent_id)],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"onchainos binary not found ({ONCHAINOS_BIN})") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("onchainos timed out") from e

    if proc.returncode != 0:
        raise RuntimeError(f"onchainos error: {proc.stderr.strip()[:300]}")

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"unparseable onchainos output: {proc.stdout[:200]}") from e

    data = payload.get("data") or []
    if not data:
        raise AgentNotFound(f"no agent #{agent_id} on OKX.AI")

    block = data[0]
    # agentInfo is null for User/buyer identities (non-ASPs); coerce to {} so the
    # engine can return a clean "not an ASP" verdict instead of crashing.
    return (block.get("agentInfo") or {}), (block.get("list") or [])


def probe_endpoints(services: list[dict]) -> dict[str, dict]:
    """HTTP-probe each service endpoint concurrently. Any HTTP response = alive."""
    urls = sorted({s["endpoint"] for s in services if s.get("endpoint")})
    if not urls:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(urls))) as pool:
        results = pool.map(_probe_one, urls)
    return {url: res for url, res in zip(urls, results)}


def _probe_one(url: str) -> dict:
    # A GET that returns ANY status (200/402/404/405) means the host is up.
    # Only a connection error / timeout counts as "down".
    try:
        r = httpx.get(url, timeout=_PROBE_TIMEOUT, follow_redirects=True)
        return {"reachable": True, "status": r.status_code}
    except httpx.HTTPError:
        try:
            r = httpx.head(url, timeout=_PROBE_TIMEOUT, follow_redirects=True)
            return {"reachable": True, "status": r.status_code}
        except httpx.HTTPError:
            return {"reachable": False, "status": None}
