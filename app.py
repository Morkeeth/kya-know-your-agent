"""
The Oracle — trust-verdict API for OKX.AI ASPs.

A free A2MCP endpoint: another agent calls GET /verify before transacting with a
counterparty ASP and gets back a signed SAFE/CAUTION/BLOCK verdict.

    uvicorn app:app --reload
"""
from __future__ import annotations

import os

import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from oracle import AgentNotFound
from oracle.data import resolve_agent_id
from oracle.verify import assess
from oracle.persona import pronounce, TAGLINE
from oracle.seal import render_stamp, render_passport
from oracle.signing import Signer

app = FastAPI(
    title="KYA — Know Your Agent",
    description="Vet any OKX.AI agent before you transact with it. Signed SAFE/CAUTION/BLOCK verdicts.",
    version="0.3.0",
)

_signer = Signer()

# Locks down the SVG document surface (badges embedded as <img> render fine).
_SVG_CSP = "default-src 'none'; style-src 'unsafe-inline'"


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
        "service": "KYA — Know Your Agent",
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


@app.get("/verify")
def verify(
    agentId: str | None = Query(default=None, description="OKX.AI agent id, e.g. 2118"),
    name: str | None = Query(default=None, description="ASP name to resolve, e.g. 'Otto AI'"),
) -> JSONResponse:
    v, env = _verdict_for(_resolve(agentId, name))
    body = v.to_dict()
    body["pronouncement"] = pronounce(v)   # KYA's voice (decoration; not signed)
    body["signature"] = env
    return JSONResponse(body)


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
