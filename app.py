"""
The Oracle - trust-verdict API for OKX.AI ASPs.

A free A2MCP endpoint: another agent calls GET /verify before transacting with a
counterparty ASP and gets back a signed SAFE/CAUTION/BLOCK verdict.

    uvicorn app:app --reload
"""
from __future__ import annotations

import os

import time

import json
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from oracle import AgentNotFound
from oracle import store
from oracle.data import resolve_agent_id
from oracle.verify import assess
from oracle.persona import pronounce, TAGLINE
from oracle.seal import render_stamp, render_passport
from oracle.signing import Signer
from oracle import x402

app = FastAPI(
    title="KYA - Know Your Agent",
    description="Vet any OKX.AI agent before you transact with it. Signed SAFE/CAUTION/BLOCK verdicts.",
    version="0.3.0",
)

_signer = Signer()

# --- PAID tier: mount /audit behind real x402 (OKX facilitator) if creds are present. ---
# Scoped to /audit ONLY; the free /verify under review is never touched. If creds are
# absent or the SDK is missing, the middleware is simply not added and the app runs free.
from oracle import audit_paid  # noqa: E402
_paid_mw, _paid_reason = audit_paid.build_paid_middleware()
if _paid_mw is not None:
    app.middleware("http")(_paid_mw)
import sys as _sys  # noqa: E402
print(f"[kya] paid tier: {_paid_reason}", file=_sys.stderr)

# Locks down the SVG document surface; img-src data: allows the embedded logo.
_SVG_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"


def _date(ts: int) -> str:
    return time.strftime("%d %b %Y", time.gmtime(ts)).upper()


def _verdict_for(agent_id: str):
    """Assess + sign an agent. Returns (verdict, signature_envelope)."""
    try:
        v = assess(agent_id)
    except AgentNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"upstream: {e}")
    return v, _signer.sign_digest(v.digest)


def _resolve(agentId, name) -> str:
    if not agentId and not name:
        raise HTTPException(status_code=400, detail="provide ?agentId= or ?name=")
    resolved = agentId
    if not resolved and name:
        resolved = resolve_agent_id(name)
        if not resolved:
            raise HTTPException(status_code=404, detail=f"no ASP exactly matching '{name}'")
    if not str(resolved).isdigit():
        raise HTTPException(status_code=400, detail="agentId must be numeric")
    return str(resolved)


@app.get("/")
def root() -> dict:
    return {
        "service": "KYA - Know Your Agent",
        "what": TAGLINE,
        "verify": "/verify?agentId=2118  (or ?name=Otto%20AI)",
        "passport": "/passport?agentId=2118  (shareable SVG)",
        "seal": "/seal?agentId=2118  (embeddable SVG badge)",
        "pubkey": "/pubkey",
        "verdicts": ["SAFE", "CAUTION", "BLOCK"],
    }


@app.get("/health")
def health() -> dict:
    return {"ok": True, "signing_key_source": _signer.source}


@app.get("/pubkey")
def pubkey() -> dict:
    """Publish the Ed25519 public key so anyone can verify a verdict offline."""
    return {"alg": "ed25519", "pubkey": _signer.public_key_hex}


@app.api_route("/verify", methods=["GET", "POST"])
async def verify(
    request: Request,
    agentId: str | None = Query(default=None, description="OKX.AI agent id, e.g. 2118"),
    name: str | None = Query(default=None, description="ASP name to resolve, e.g. 'Otto AI'"),
) -> JSONResponse:
    """The listed trust-verdict service, gated by x402.

    #5290's rejection ("unable to receive a response from your Agent") walked through three
    wrong theories before the real contract, each corrected by probing a LIVE APPROVED agent
    instead of reasoning:
      1. "OKX queue stall"  — no; the endpoint 405'd their POST test.
      2. "A2MCP is POST-only" — no; SlowMist #2155 is GET-shaped, 405s POST, and is approved.
         The real defect was answering NOTHING usable: 405 on POST, 400 on GET.
      3. "free service returns 200" — no; the marketplace hire path runs x402, and an
         unpaid call must return 402 + terms, not 200. SlowMist (fee 0, approved) proves it:
         its challenge is `amount:"0"` USDT on XLayer. 200-to-unpaid is "live and wrong".

    So: unpaid -> 402 challenge (handled above). Paid (X-PAYMENT present) -> the verdict.
    Amount is 0, so KYA stays genuinely free; nothing settles. The agent id comes from the
    query string, JSON body ({"agentId"|"agent_id"|"id"}), MCP tools/call
    ({"params":{"arguments":{...}}}), or form body.
    """
    # x402 GATE (the marketplace hire path). An unpaid request MUST get 402 + terms, not
    # 200 and not 400. Measured from the approved fee-0 comparable SlowMist #2155: its
    # challenge is amount "0" USDT on XLayer. KYA stays free (nothing settles) but must
    # speak x402 or the marketplace probe reports valid:false and blocks the hire.
    if not x402.is_paid(request.headers):
        resource = str(request.url).split("?")[0]
        return JSONResponse(
            x402.challenge(resource),
            status_code=402,
            headers={
                "payment-required": x402.challenge_header(resource),
                "access-control-expose-headers": "PAYMENT-REQUIRED,PAYMENT-RESPONSE",
                "access-control-allow-origin": "*",
            },
        )

    aid, nm = agentId, name
    if not (aid or nm):
        payload: dict = {}
        try:
            raw = await request.body()
            if raw:
                try:
                    payload = json.loads(raw)
                except ValueError:
                    form = await request.form()
                    payload = dict(form)
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            # MCP tools/call shape nests the real args; unwrap before looking.
            args = payload.get("params", {})
            args = args.get("arguments", args) if isinstance(args, dict) else {}
            src = {**(args if isinstance(args, dict) else {}), **payload}
            for k in ("agentId", "agent_id", "agentID", "id"):
                if src.get(k) is not None:
                    aid = str(src[k])
                    break
            for k in ("name", "aspName", "agentName"):
                if src.get(k) is not None:
                    nm = str(src[k])
                    break
        # Paid, but no agent named: the caller settled the (zero) challenge and asked about
        # nobody. Return a usable descriptor rather than 400, so a paid liveness probe passes.
        if not aid and not nm and not payload:
            return JSONResponse({
                "ok": True,
                "service": "KYA - Know Your Agent",
                "what": TAGLINE,
                "usage": {"body": {"agentId": "2118"}},
                "returns": ["verdict SAFE|CAUTION|BLOCK", "score", "max_safe_usd", "signature"],
                "verify_offline": "/pubkey",
            })
    v, env = _verdict_for(_resolve(aid, nm))
    body = v.to_dict()
    body["pronouncement"] = pronounce(v)   # KYA's voice (decoration; not signed)
    body["signature"] = env
    return JSONResponse(body)


@app.api_route("/audit", methods=["GET", "POST"])
async def audit(request: Request,
                agentId: str | None = Query(default=None),
                name: str | None = Query(default=None)) -> JSONResponse:
    """PAID full audit ($0.10 USDT via x402). The x402 middleware gates this route: an
    unpaid call never reaches here (it gets the facilitator's 402); a verified-paid call
    does. So by the time we run, payment is real and settled — we just serve the depth."""
    aid, nm = agentId, name
    if request.method == "POST" and not (aid or nm):
        try:
            payload = json.loads(await request.body() or b"{}")
            args = payload.get("params", {})
            args = args.get("arguments", args) if isinstance(args, dict) else {}
            src = {**(args if isinstance(args, dict) else {}), **payload}
            for k in ("agentId", "agent_id", "id"):
                if src.get(k) is not None:
                    aid = str(src[k]); break
        except Exception:
            pass
    v, env = _verdict_for(_resolve(aid, nm))
    return JSONResponse(audit_paid.full_audit(v.agent_id, v, env))


@app.get("/seal")
def seal(agentId: str | None = Query(default=None), name: str | None = Query(default=None)):
    """Embeddable SVG entry-stamp badge (links back to the live verdict)."""
    v, env = _verdict_for(_resolve(agentId, name))
    svg = render_stamp(v.verdict, v.agent_id, _date(env["signed_at"]))
    return Response(svg, media_type="image/svg+xml",
                    headers={"Content-Security-Policy": _SVG_CSP, "Cache-Control": "max-age=300"})


@app.get("/passport")
def passport(agentId: str | None = Query(default=None), name: str | None = Query(default=None)):
    """The shareable SVG agent passport."""
    v, env = _verdict_for(_resolve(agentId, name))
    svg = render_passport(
        v.verdict, v.name, v.agent_id, evidence=v.evidence, pronouncement=pronounce(v),
        issued=_date(env["signed_at"]), expires=_date(env["expires_at"]),
        digest=v.digest, pubkey=env["pubkey"],
    )
    return Response(svg, media_type="image/svg+xml",
                    headers={"Content-Security-Policy": _SVG_CSP, "Cache-Control": "max-age=300"})


@app.get("/history")
def history(agentId: str | None = Query(default=None), name: str | None = Query(default=None),
            limit: int = Query(default=20, ge=1, le=100)):
    """Every verdict KYA has issued for this agent - trust is a timeline, not a snapshot."""
    aid = _resolve(agentId, name)
    return {"agent_id": aid, "history": store.history(aid, limit=limit),
            "uptime": store.uptime(aid)}


@app.get("/changes")
def changes(limit: int = Query(default=20, ge=1, le=100)):
    """Recent verdict TRANSITIONS across all agents - who KYA re-verified up or down
    after they changed (patched a dead endpoint, lost their reviews, went offline)."""
    return {"changes": store.recent_changes(limit=limit)}


@app.get("/watchtower")
def watchtower():
    """The Watchtower - a live board of every agent KYA has judged + recent crossings."""
    from oracle.watchtower import render_watchtower
    html = render_watchtower(store.latest_per_agent(limit=400), store.recent_changes(limit=12))
    return Response(html, media_type="text/html",
                    headers={"Cache-Control": "max-age=30"})


@app.get("/operators")
def operators():
    """The board OKX's own marketplace cannot render: the same agents, grouped by the
    WALLET that controls them. `agent search` never returns ownerAddress, so a buyer
    sees N independent providers where there is really one face holding N passports."""
    from oracle.watchtower import render_operators
    html = render_operators(store.operators(limit=25))
    return Response(html, media_type="text/html",
                    headers={"Cache-Control": "max-age=30"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
