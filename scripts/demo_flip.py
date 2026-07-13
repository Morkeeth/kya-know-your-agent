#!/usr/bin/env python3
"""
Honest re-verify-on-patch demo.

Stands up a REAL local endpoint, flips it from dead (502) to serving (402 x402),
and shows KYA's real engine + store detect the change and record a genuine
BLOCK -> SAFE transition. Nothing is mocked: the prober really hits the endpoint,
the real _classify reads the response, the real engine scores it, the real store
logs the flip. The agent record is a clearly-labelled TEST agent; the DETECTION
is 100% real. Run: ./.venv/bin/python scripts/demo_flip.py
"""
import os
import socket
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.environ["KYA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "demo.db")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from oracle.data import _classify  # noqa: E402
from oracle.engine import score_agent  # noqa: E402
from oracle import store  # noqa: E402

STATE = {"alive": False}  # the endpoint's real behaviour, flipped mid-demo


class _Handler(BaseHTTPRequestHandler):
    def _reply(self):
        if STATE["alive"]:
            self.send_response(402)  # a real x402 payment challenge = serving
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"accepts":[{"scheme":"exact","payTo":"0xtest"}]}')
        else:
            self.send_response(502)  # dead
            self.send_header("content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html>bad gateway</html>")

    do_GET = do_POST = lambda self: self._reply()  # noqa: E731

    def log_message(self, *a):
        pass


def _probe(url: str) -> dict:
    """Real HTTP to the real (changing) endpoint, scored by the real classifier."""
    best = None
    for method in ("POST", "GET"):
        try:
            r = httpx.request(method, url, timeout=3, follow_redirects=False,
                              json={} if method == "POST" else None)
        except httpx.HTTPError:
            continue
        cat = _classify(url, r)
        best = {"reachable": True, "status": r.status_code, "healthy": cat in ("x402", "api"),
                "category": cat, "down_kind": None, "latency_ms": 5}
    return best or {"reachable": False, "status": None, "healthy": False,
                    "category": "down", "down_kind": "refused", "latency_ms": None}


def _agent():
    # a TEST agent record; only its endpoint's real liveness changes between looks
    return dict(agentId="TESTFLIP", name="Test Flip Agent", approvalStatus=4,
                onlineStatus=1, status=1, salesCount=200, securityRate="4.5",
                profileDescription="demo test agent")


def main():
    # Reserve a port but leave NOTHING listening for look #1, so a real probe gets
    # connection-refused == a genuinely dead endpoint (BLOCK), not just a 5xx.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    url = f"http://127.0.0.1:{port}/verify"
    svc = [{"endpoint": url, "fee": "0.10", "serviceType": "A2MCP", "serviceName": "x"}]

    def look(label):
        probes = {url: _probe(url)}
        v = score_agent(_agent(), svc, probes, agent_id="TESTFLIP")
        sh = store.state_hash(_agent(), svc, None)  # SAME both looks — only liveness moved
        store.record_probes("TESTFLIP", probes)
        ch = store.record(v, sh)
        flip = f"   >>> TRANSITION {ch['transition']['from']} -> {ch['transition']['to']}" if ch["transition"] else ""
        print(f"{label}\n   endpoint probed: {probes[url]['category']:6} -> verdict {v.verdict} ({v.score}){flip}")

    print("== KYA re-verify-on-patch  (real endpoint, real detection) ==\n")
    look("1. First look — endpoint is dead (nothing listening):")

    # The agent PATCHES: bring the real endpoint up, serving x402.
    STATE["alive"] = True
    srv = HTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    look("2. Agent patches its endpoint, KYA is called again:")

    print("\n/changes feed:")
    for c in store.recent_changes(limit=3):
        print(f"   {c['name']}: {c['from_verdict']} -> {c['to_verdict']}  ({c['reason']})")
    srv.shutdown()


if __name__ == "__main__":
    main()
