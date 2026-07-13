"""
I/O layer: pull an ASP's marketplace record via the `onchainos` CLI and probe
its endpoints for liveness. Kept separate from engine.py so scoring stays pure.
"""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

ONCHAINOS_BIN = os.environ.get("ONCHAINOS_BIN", "onchainos")
_PROBE_TIMEOUT = float(os.environ.get("PROBE_TIMEOUT", "4.0"))
_CACHE_TTL = float(os.environ.get("CACHE_TTL", "60"))

# Tiny in-process TTL cache so repeat verifies (and the 90s demo) don't re-shell
# onchainos every call. Keyed by agentId.
_cache: dict[str, tuple[float, tuple[dict, list[dict]]]] = {}


class AgentNotFound(Exception):
    pass


def _run_onchainos(args: list[str]) -> dict:
    try:
        proc = subprocess.run(
            [ONCHAINOS_BIN, *args], capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"onchainos binary not found ({ONCHAINOS_BIN})") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("onchainos timed out") from e
    if proc.returncode != 0:
        msg = (proc.stderr.strip() or proc.stdout.strip() or "(no output)")[:400]
        raise RuntimeError(f"onchainos rc={proc.returncode}: {msg}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"unparseable onchainos output: {proc.stdout[:200]}") from e


def fetch_agent(agent_id: str) -> tuple[dict, list[dict]]:
    """Return (agent_info, services) for an agentId. Raises AgentNotFound."""
    key = str(agent_id)
    hit = _cache.get(key)
    if hit and (time.time() - hit[0]) < _CACHE_TTL:
        return hit[1]

    payload = _run_onchainos(["agent", "service-list", "--agent-id", key])
    data = payload.get("data") or []
    if not isinstance(data, list) or not data:
        raise AgentNotFound(f"no agent #{agent_id} on OKX.AI")

    block = data[0]
    # agentInfo is null for User/buyer identities (non-ASPs); coerce to {} so the
    # engine can return a clean "not an ASP" verdict instead of crashing.
    result = (block.get("agentInfo") or {}), (block.get("list") or [])
    _cache[key] = (time.time(), result)
    return result


def _pick_exact(items: list[dict], name: str) -> str | None:
    """Return the agentId whose name EXACTLY (case-insensitively) matches, else None.

    Marketplace search is semantic and ranks loosely — it will happily return
    'Factor Credit Desk' for a query of 'Otto AI'. For a trust oracle a confident
    wrong answer is worse than none, so we never fall back to the top hit.
    """
    target = name.strip().lower()
    for it in items:
        if str(it.get("name") or "").strip().lower() == target:
            return str(it.get("agentId"))
    return None


def resolve_agent_id(name: str) -> str | None:
    """Resolve an ASP name to its agentId via exact-name match on marketplace search."""
    payload = _run_onchainos(["agent", "search", "--query", name])
    items = (payload.get("data") or {}).get("list") or []
    return _pick_exact(items, name)


def scan_malicious(services: list[dict]) -> list[str]:
    """Run OKX's phishing/blacklist scan on each distinct endpoint host.
    Returns the list of hosts flagged malicious (empty = clean). A live endpoint
    can be malicious — liveness alone never catches that."""
    seen, flagged = {}, []
    for s in services:
        ep = s.get("endpoint")
        if not ep:
            continue
        try:
            host = httpx.URL(ep).host
        except Exception:  # noqa: BLE001
            continue
        if host in seen:
            continue
        seen[host] = ep
        try:
            data = _run_onchainos(["security", "dapp-scan", "--domain", ep]).get("data") or {}
        except RuntimeError:
            continue  # scan unavailable -> don't fail the whole verdict
        if data.get("isMalicious"):
            flagged.append(host)
    return flagged


def fetch_feedback(agent_id: str) -> dict:
    """Per-review reviewer addresses + rating distribution — so reputation can be
    audited by WHO reviewed, not just an aggregate star average."""
    try:
        d = _run_onchainos(["agent", "feedback-list", "--agent-id", str(agent_id)]).get("data") or {}
    except RuntimeError:
        return {}
    lst = d.get("list") or []
    # Per-review ratings power the Wilson sample-size-aware reputation term. OKX's
    # exact field name isn't pinned, so read the first rating-ish key we find and
    # count 4-5 stars as positive; absent ratings just leave (positive,total) unset
    # and the engine falls back to securityRate. TODO(live): confirm the field name.
    def _rating(r: dict):
        for k in ("star", "stars", "rating", "score", "rate"):
            v = r.get(k)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None
        return None
    ratings = [x for x in (_rating(r) for r in lst) if x is not None]
    out = {
        "distribution": d.get("distribution") or {},
        "reviewers": [str(r.get("reviewerAddress") or "").lower() for r in lst if r.get("reviewerAddress")],
        "count": len(lst),
    }
    if ratings:
        out["total"] = len(ratings)
        out["positive"] = sum(1 for x in ratings if x >= 4)
    return out


# --------------------------------------------------------------------- SSRF guard
# KYA probes endpoints that a HOSTILE agent controls, from the same host that holds
# the signing key. Without this guard a malicious ASP could register
# `endpoint=http://169.254.169.254/latest/meta-data/…` (steal cloud IAM creds) or a
# public URL that 302s to an internal RPC — a classic SSRF, and worse in a *trust*
# product because the target also controls what "healthy" looks like. Primary control
# (per OWASP): resolve the host and reject if ANY resolved IP is non-public; belt &
# braces: an explicit metadata denylist, https/http-only, and NO redirect following.
_METADATA_HOSTS = {"169.254.169.254", "fd00:ec2::254", "metadata.google.internal",
                   "metadata.goog"}


class BlockedTarget(Exception):
    """The endpoint resolves to internal/reserved space or uses a bad scheme."""


def _ip_is_public(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified)


def guard_url(url: str) -> None:
    """Raise BlockedTarget if `url` could pivot to internal / cloud-metadata infra.

    Resolves the host and validates the PARSED IP (so decimal/hex/octal-encoded
    address tricks are caught too — we check what it resolves to, not the string).
    """
    try:
        u = httpx.URL(url)
    except Exception as e:  # noqa: BLE001
        raise BlockedTarget(f"unparseable URL: {url!r}") from e
    if u.scheme not in ("http", "https"):
        raise BlockedTarget(f"scheme {u.scheme!r} not allowed (http/https only)")
    host = (u.host or "").strip().rstrip(".").lower()
    if not host:
        raise BlockedTarget("no host in URL")
    if host in _METADATA_HOSTS:
        raise BlockedTarget(f"cloud-metadata host {host!r}")
    # A bare IP literal: validate it directly (no DNS).
    try:
        if not _ip_is_public(str(ipaddress.ip_address(host))):
            raise BlockedTarget(f"non-public IP literal {host!r}")
        return
    except ValueError:
        pass  # it's a hostname — resolve it
    try:
        infos = socket.getaddrinfo(host, u.port or (443 if u.scheme == "https" else 80),
                                   type=socket.SOCK_STREAM)
    except socket.gaierror:
        # Can't resolve — could be a transient DNS blip or a dead domain. This is
        # NOT an SSRF signal (there's no internal target to hit), so DON'T hard-block
        # it as malicious; let the real HTTP probe fail and be scored as unreachable.
        return
    addrs = {info[4][0] for info in infos}
    for ip_str in addrs:
        if not _ip_is_public(ip_str):
            raise BlockedTarget(f"{host!r} resolves to non-public IP {ip_str}")


def _registration_ids(reg: dict) -> set[str]:
    """Pull the agentId(s) an ERC-8004 .well-known/agent-registration.json claims.
    Tolerant of a few shapes: {registrations:[{agentId}]}, {agentId}, {agents:[...]}."""
    ids: set[str] = set()

    def _add(v):
        if v is not None:
            ids.add(str(v).strip().lstrip("#"))

    if not isinstance(reg, dict):
        return ids
    _add(reg.get("agentId"))
    for key in ("registrations", "agents"):
        for item in (reg.get(key) or []):
            if isinstance(item, dict):
                _add(item.get("agentId"))
    return {i for i in ids if i}


def _x402_paytos(body: dict) -> set[str]:
    """Pull the payTo address(es) from an x402 402 challenge. accepts[].payTo per
    the exact-EVM spec; the facilitator can only settle to payTo, so it IS the
    beneficiary. Lower-cased for comparison."""
    outs: set[str] = set()
    if not isinstance(body, dict):
        return outs
    for a in (body.get("accepts") or []):
        if isinstance(a, dict) and a.get("payTo"):
            outs.add(str(a["payTo"]).strip().lower())
    if body.get("payTo"):
        outs.add(str(body["payTo"]).strip().lower())
    return {o for o in outs if o}


def fetch_identity(agent_id: str, agent_info: dict | None, services: list[dict]) -> dict:
    """Anti-impersonation checks on the PRIMARY endpoint (best-effort, guarded):

      domain_binding — does {host}/.well-known/agent-registration.json name THIS
                       agent? Catches endpoint-BORROWING: agent B listing agent A's
                       live, well-reviewed endpoint to inherit its liveness score.
      payto          — does the x402 402 challenge route payment to the agent's own
                       registered wallet? Catches fund-DIVERSION.

    Returns each as 'match' | 'mismatch' | 'absent'. Absent = NEUTRAL: in 2026 few
    agents implement either, so only a positive CONTRADICTION is a trust signal."""
    result = {"domain_binding": "absent", "payto": "absent"}
    eps = [s.get("endpoint") for s in services if s.get("endpoint")]
    if not eps:
        return result
    ep = eps[0]
    try:
        u = httpx.URL(ep)
        wk = str(httpx.URL(scheme=u.scheme, host=u.host, port=u.port,
                           path="/.well-known/agent-registration.json"))
        guard_url(wk)
        r = httpx.get(wk, timeout=_PROBE_TIMEOUT, follow_redirects=False,
                      headers={"User-Agent": _UA})
        if r.status_code == 200 and _is_json(r):
            ids = _registration_ids(r.json())
            if ids:
                result["domain_binding"] = "match" if str(agent_id) in ids else "mismatch"
    except (httpx.HTTPError, ValueError, KeyError):
        pass

    wallet = str((agent_info or {}).get("agentWalletAddress") or "").strip().lower()
    if wallet:
        try:
            guard_url(ep)
            r = httpx.post(ep, timeout=_PROBE_TIMEOUT, follow_redirects=False,
                           headers={"User-Agent": _UA}, json={})
            if r.status_code == 402 and _is_json(r):
                pays = _x402_paytos(r.json())
                if pays:
                    result["payto"] = "match" if wallet in pays else "mismatch"
        except (httpx.HTTPError, ValueError, KeyError, BlockedTarget):
            pass
    return result


_UA = "Mozilla/5.0 (compatible; OracleTrustProbe/0.2; +https://okx.ai)"


def probe_endpoints(services: list[dict]) -> dict[str, dict]:
    """
    HTTP-probe each service endpoint concurrently and classify it:

      reachable : we got any HTTP response (host is up)
      healthy   : responded 2xx or 402 AND did not redirect off-host
                  (a 404 / 5xx / redirect to google.com is NOT a working service)
      status    : final HTTP status, or None
      down_kind : 'refused' (connection refused/DNS)  vs  'timeout' (unknown)

    The healthy/reachable split is what stops a parked domain scoring as live and
    stops a slow/WAF'd legit endpoint being hard-BLOCKed on a single timeout.
    """
    urls = sorted({s["endpoint"] for s in services if s.get("endpoint")})
    if not urls:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(urls))) as pool:
        results = pool.map(_probe_one, urls)
    return {url: res for url, res in zip(urls, results)}


def _reg(host: str) -> str:
    # Strip a leading www. so an apex->www (or www->apex) redirect isn't flagged
    # as off-host. Not a full public-suffix parse — good enough for liveness.
    h = host.lower()
    return h[4:] if h.startswith("www.") else h


def _same_host(a: str, b: str) -> bool:
    try:
        return _reg(httpx.URL(a).host) == _reg(httpx.URL(b).host)
    except Exception:  # noqa: BLE001
        return False


def _is_json(r: httpx.Response) -> bool:
    if "json" in r.headers.get("content-type", "").lower():
        return True
    try:
        json.loads(r.text)
        return True
    except Exception:  # noqa: BLE001
        return False


# category rank, best -> worst. healthy = {x402, api}.
_RANK = {"x402": 0, "api": 1, "parked": 2, "broken": 3, "offhost": 4, "down": 5}


def _classify(url: str, r: httpx.Response) -> str:
    """Classify one response the way an A2MCP caller would experience the endpoint."""
    code = r.status_code
    # We no longer FOLLOW redirects (SSRF), so inspect the Location ourselves: a
    # redirect pointing off-host is the parked/hijacked/bait signal we still want.
    if 300 <= code < 400:
        loc = r.headers.get("location", "")
        if loc:
            try:
                dest = str(httpx.URL(url).join(loc))
            except Exception:  # noqa: BLE001
                dest = loc
            if not _same_host(url, dest):
                return "offhost"              # redirect AWAY — parked / hijacked
        return "broken"                       # on-host / headerless redirect — not serving
    if not _same_host(url, str(r.url)):
        return "offhost"                      # defensive (redirects are off)
    if code == 402:
        return "x402"                         # proper payment challenge = working paid endpoint
    if 500 <= code < 600:
        return "broken"                       # server error
    if 200 <= code < 300 and _is_json(r):
        return "api"                          # serving JSON
    if code == 405 or (400 <= code < 500 and _is_json(r)):
        return "api"                          # endpoint exists; wrong method/params (e.g. POST-only)
    if 200 <= code < 300:
        return "parked"                       # 2xx HTML landing page — not an API
    return "broken"


def _probe_one(url: str) -> dict:
    # SSRF guard FIRST: never let a hostile endpoint point the prober at internal
    # or cloud-metadata infrastructure. A blocked target is a strong BLOCK signal.
    try:
        guard_url(url)
    except BlockedTarget as e:
        return {"reachable": False, "status": None, "healthy": False, "latency_ms": None,
                "category": "blocked", "down_kind": "blocked", "block_reason": str(e)}
    # A2MCP endpoints are POST-first; GET commonly yields 402/405. Try both and
    # keep the BEST evidence, so a POST-only service isn't mistaken for dead.
    best_cat, best_status, best_latency, down_kind = None, None, None, "refused"
    for method in ("POST", "GET"):
        t0 = time.perf_counter()
        try:
            r = httpx.request(
                method, url, timeout=_PROBE_TIMEOUT, follow_redirects=False,
                headers={"User-Agent": _UA}, json={} if method == "POST" else None,
            )
        except httpx.TimeoutException:
            down_kind = "timeout"
            continue
        except httpx.HTTPError:
            down_kind = "refused"
            continue
        elapsed = int((time.perf_counter() - t0) * 1000)
        cat = _classify(url, r)
        if best_cat is None or _RANK[cat] < _RANK[best_cat]:
            best_cat, best_status, best_latency = cat, r.status_code, elapsed

    if best_cat is None:
        return {"reachable": False, "status": None, "healthy": False, "latency_ms": None,
                "category": "down", "down_kind": down_kind}
    return {"reachable": True, "status": best_status, "healthy": best_cat in ("x402", "api"),
            "category": best_cat, "down_kind": None, "latency_ms": best_latency}
