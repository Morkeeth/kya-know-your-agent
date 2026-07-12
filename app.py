"""
The Oracle — trust-verdict API for OKX.AI ASPs.

A free A2MCP endpoint: another agent calls GET /verify before transacting with a
counterparty ASP and gets back a signed SAFE/CAUTION/BLOCK verdict.

    uvicorn app:app --reload
"""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from oracle import fetch_agent, probe_endpoints, score_agent, AgentNotFound
from oracle.data import resolve_agent_id
from oracle.signing import Signer

app = FastAPI(
    title="The Oracle — OKX.AI Trust Verdicts",
    description="Vet any OKX.AI ASP before you transact with it. Signed SAFE/CAUTION/BLOCK verdicts.",
    version="0.2.0",
)

_signer = Signer()


@app.get("/")
def root() -> dict:
    return {
        "service": "The Oracle",
        "what": "Signed trust verdicts for OKX.AI ASPs — vet a counterparty agent before you transact.",
        "verify": "/verify?agentId=2118  (or ?name=Otto%20AI)",
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
    if not agentId and not name:
        raise HTTPException(status_code=400, detail="provide ?agentId= or ?name=")

    resolved = agentId
    if not resolved and name:
        resolved = resolve_agent_id(name)
        if not resolved:
            raise HTTPException(status_code=404, detail=f"no ASP matching name '{name}'")

    if not str(resolved).isdigit():
        raise HTTPException(status_code=400, detail="agentId must be numeric")

    try:
        info, services = fetch_agent(resolved)
    except AgentNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"upstream: {e}")

    verdict = score_agent(info, services, probe_endpoints(services), agent_id=resolved)
    body = verdict.to_dict()
    body["signature"] = _signer.sign_digest(verdict.digest)
    return JSONResponse(body)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
