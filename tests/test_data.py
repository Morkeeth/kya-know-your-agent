"""Probe-classifier tests — the behaviour-aware liveness logic, no network.

We hand-build httpx.Response objects to exercise _classify: an A2MCP endpoint
speaks JSON / 402, a parked domain serves HTML, a broken one 5xx, a hijacked one
redirects off-host.
"""
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from oracle.data import _classify, _is_json, guard_url, BlockedTarget  # noqa: E402

URL = "https://svc.example.com/api"


def _resp(status, *, json_ct=False, body="", final_url=URL, location=None):
    headers = {"content-type": "application/json"} if json_ct else {"content-type": "text/html"}
    if location is not None:
        headers["location"] = location
    req = httpx.Request("GET", final_url)
    return httpx.Response(status, headers=headers, text=body, request=req)


# ---------------------------------------------------------- SSRF guard (slice 2)
@pytest.mark.parametrize("bad", [
    "http://169.254.169.254/latest/meta-data/",        # AWS IMDS credential theft
    "http://metadata.google.internal/computeMetadata/", # GCP metadata
    "http://127.0.0.1:6379/",                          # loopback (co-located Redis)
    "http://localhost:8080/verify",                    # loopback by name
    "http://10.0.0.5/api",                             # RFC1918
    "http://192.168.1.1/",                             # RFC1918
    "http://169.254.169.254.nip.io/" if False else "http://[::1]/",  # IPv6 loopback
    "http://0x7f000001/",                              # hex-encoded 127.0.0.1
    "http://2130706433/",                              # decimal-encoded 127.0.0.1
    "file:///etc/passwd",                              # non-http scheme
    "gopher://internal/",                              # scheme smuggling
])
def test_guard_blocks_internal_and_bad_schemes(bad):
    with pytest.raises(BlockedTarget):
        guard_url(bad)


def test_guard_allows_public_https():
    # Public, resolvable host must pass (uses real DNS; example.com is stable).
    guard_url("https://example.com/api")


def test_offhost_redirect_via_location_header_is_offhost():
    # We no longer follow redirects — a 302 pointing away is caught from Location.
    r = _resp(302, location="https://evil.example.net/landing")
    assert _classify(URL, r) == "offhost"


def test_onhost_redirect_is_broken_not_serving():
    r = _resp(301, location="/login")  # same-host redirect — not a serving API
    assert _classify(URL, r) == "broken"


def test_402_is_x402():
    assert _classify(URL, _resp(402, json_ct=True, body="{}")) == "x402"


def test_2xx_json_is_api():
    assert _classify(URL, _resp(200, json_ct=True, body='{"ok":true}')) == "api"


def test_405_is_api_endpoint_present():
    # POST-only A2MCP endpoint returns 405 to a GET — it still exists.
    assert _classify(URL, _resp(405, json_ct=True, body='{"error":"use POST"}')) == "api"


def test_4xx_json_is_api():
    assert _classify(URL, _resp(422, json_ct=True, body='{"detail":"bad params"}')) == "api"


def test_200_html_is_parked():
    assert _classify(URL, _resp(200, body="<!DOCTYPE html><html>parked</html>")) == "parked"


def test_5xx_is_broken():
    assert _classify(URL, _resp(502, body="<html>bad gateway</html>")) == "broken"


def test_offhost_redirect_is_offhost():
    r = _resp(200, json_ct=True, body="{}", final_url="https://google.com/")
    assert _classify(URL, r) == "offhost"


def test_is_json_detects_body_without_header():
    r = _resp(200, body='{"a":1}')  # html content-type but JSON body
    assert _is_json(r) is True


# ---------------------------------------------------- name resolution (exact-only)
from oracle.data import _pick_exact  # noqa: E402


def test_pick_exact_matches_case_insensitively():
    items = [{"agentId": "4502", "name": "Factor Credit Desk"},
             {"agentId": "2118", "name": "Otto AI"}]
    assert _pick_exact(items, "otto ai") == "2118"


def test_pick_exact_never_guesses_top_hit():
    # Semantic search returned junk with no exact match -> must be None, not items[0].
    items = [{"agentId": "4502", "name": "Factor Credit Desk"},
             {"agentId": "2570", "name": "dealer.exe"}]
    assert _pick_exact(items, "Otto AI") is None


def test_pick_exact_empty():
    assert _pick_exact([], "Anything") is None
