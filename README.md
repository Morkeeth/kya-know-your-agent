# The Oracle

**A trust oracle for the agent economy.** Before your agent pays a counterparty, ask The Oracle whether that counterparty is worth trusting — and get back a signed `SAFE` / `CAUTION` / `BLOCK` verdict.

> Working name. Final name TBD.

---

## The problem

OKX.AI is a marketplace where autonomous agents hire other agents. An Agent Service Provider (ASP) lists a service, and any other agent can call and pay it — often over x402, often unattended. But the agent doing the hiring is transacting **blind**. It sees a name, a star rating, maybe a fee. It has no way to know:

- Is this ASP's endpoint actually alive, or listed-but-dead?
- Has anyone *ever* completed a paid transaction with it, or is it a 5-star listing with zero sales?
- Is this even a provider, or a buyer/test identity that can't deliver anything?

Star ratings don't answer these. A rating is a claim; The Oracle checks the receipts.

## What it does

The Oracle is itself an ASP. Another agent calls it with a target `agentId` and gets back a verdict on whether transacting with that agent is safe. It reasons over the target's **live OKX marketplace record**, **probes its endpoints in real time**, and runs **anomaly detection** across the two — then returns a gated, signed verdict.

The white space: the token/wallet-safety corner of OKX.AI is already contested. **Nobody vets the agents/ASPs themselves.** That's what this fills — and in doing so it makes OKX's own marketplace safer to transact in.

## How the verdict works

### SAFE must be earned

Every *listed* ASP has already passed OKX review, is marked online, and has a live endpoint. That is table stakes — not a reason to trust it with money. So the engine is **gated, not additive**:

| Condition | Effect |
|---|---|
| Dead endpoint / inactive / test account / not an ASP | Score **capped low → BLOCK** |
| Live but **0 completed sales** (unproven) | Score **capped at 64 → CAUTION** |
| Real, earned track record + clean signals | Can reach **SAFE (≥70)** |

Verdict bands: **SAFE** ≥ 70 · **CAUTION** 45–69 · **BLOCK** < 45.

Scoring starts at a neutral 50, applies additive signal deltas, then clamps to the **lowest cap** any signal imposed. A single hard failure overrides a pile of good signals — you cannot buy back a dead endpoint with a nice star rating.

### Three signal families

1. **Reputation (the earned signal that gates SAFE)** — settled **volume**, not a raw sales *count*. `salesCount × median fee` is the proxy: a raw count is the cheapest thing to fake (wash-buy a 0.001-USDT service 10× for ~$0.01), so SAFE requires either real settled volume *or* a sales count high enough to be costly to wash. Cheap, low-count sales cap at CAUTION.
2. **Liveness (behaviour-aware, not just "responds")** — every endpoint is probed with **both POST and GET** and classified by how it behaves: a `402` payment challenge or a JSON API response = *serving*; a 2xx **HTML** landing page = *parked*; `5xx` = *broken*; an off-host redirect = *hijacked/parked*; connection-refused = *down*. This is what stops a parked domain scoring as "live" and stops a POST-only A2MCP endpoint being mistaken for dead. Timeouts are treated as *unverified* (softer) rather than proven-dead.
3. **Anomaly detection** — the cross-checks a raw rating won't surface: high rating with zero sales ("reputation not earned through real usage"), **listed-online-but-endpoint-actually-down**, test/placeholder account names (only when also unproven), empty profile, and off-market fees.

Each verdict carries a **confidence** score (0–100) reflecting how much evidence was available — and thin evidence itself caps the verdict at CAUTION. Verdicts are **Ed25519-signed and time-bounded**: the service signs `sha256(canonical verdict) + issued_at + ttl` with a key it controls and publishes the public key at `/pubkey`, so any consumer can verify a verdict offline and reject an expired one — no shared secret.

### Verified against live agents

The engine discriminates correctly across real OKX.AI agents — it does not rubber-stamp:

| Agent | ID | Sales | Verdict | Score | Why |
|---|---|---|---|---|---|
| Onchain Data Explorer | #2023 | 656 | **SAFE** | 100 | Strong earned track record, live, clean |
| Otto AI | #2118 | 169 | **SAFE** | 100 | Proven track record + live endpoint |
| Scope | #3733 | 1 | **CAUTION** | 69 | Barely proven — one sale caps it |
| WhalePulse | #3369 | 0 | **CAUTION** | 64 | Live but unproven — nobody has used it |
| Sentiment Oracle | #3820 | 0 | **BLOCK** | 44 | Its endpoints actually return 502 — listed-online but down |
| (non-ASP identity) | #2971 | — | **BLOCK** | 20 | No registered ASP services |
| (non-ASP identity) | #1771 | — | **BLOCK** | 20 | Not a provider you can transact with |

That Sentiment Oracle row is the point: a raw star-rating would never tell you the endpoint is dead. The behaviour-aware probe caught it.

Reproduce it:

```bash
python scripts/smoke.py 2118 2023 3733 3369 3820 2971 1771
```

## Architecture

Python, deliberately split so the trust logic is unit-testable in isolation:

```
oracle/
  engine.py   Pure gated scoring. No I/O. Input: marketplace record + probe
              results. Output: a Verdict dataclass + content digest. The trust logic.
  data.py     I/O layer. Shells `onchainos agent service-list` for the target's
              marketplace record + name resolution, then behaviour-probes its
              endpoints (httpx, thread pool) for liveness.
  signing.py  Ed25519 keypair mgmt; signs the verdict digest + freshness window,
              publishes the public key, verifies envelopes (incl. expiry).
app.py        FastAPI server: GET /verify, /pubkey, /health. The A2MCP endpoint.
cli.py        Local harness: fetch -> probe -> score -> print JSON. No server needed.
scripts/
  smoke.py    Runs the engine across real agents; proves discrimination.
  demo.sh     The 90-second demo narrative (SAFE / CAUTION / BLOCK on live agents).
tests/        31+ tests incl. the wash-trade and dead-endpoint security regressions.
```

`engine.py` has **no network or subprocess dependency** — you hand it dicts, it hands you a `Verdict`. That keeps the part that decides "should money move" small, pure, and testable. `data.py` owns everything that can fail on the network. `app.py` wraps them behind `GET /verify` and attaches the signature.

**Deploy target:** Railway (public HTTPS) — see [DEPLOY.md](DEPLOY.md). That URL becomes permanent on-chain when the ASP registers, so it ships behind a stable host from day one. Free A2MCP endpoint first; paid x402 tier later.

## API sketch

```
GET /verify?agentId=2118
```

Returns the `Verdict` shape produced by `engine.py`:

```json
{
  "agent_id": "2118",
  "name": "Otto AI",
  "verdict": "SAFE",
  "score": 100,
  "confidence": 100,
  "reasons": [
    "✅ 169 completed sales — strong, earned track record.",
    "✅ All 1 service endpoint(s) responding.",
    "✅ Passed OKX listing review."
  ],
  "signals": [
    { "key": "sales", "delta": 26, "reason": "169 completed sales — strong, earned track record.", "severity": "good", "cap": null },
    { "key": "liveness", "delta": 18, "reason": "All 1 service endpoint(s) responding.", "severity": "good", "cap": null }
  ],
  "evidence": {
    "isAsp": true,
    "sales": 169,
    "securityRate": 5.0,
    "approvalStatus": 4,
    "onlineStatus": 1,
    "serviceCount": 1,
    "endpoints": { "https://…": "live (x402 paywall)" },
    "cappedAt": null
  },
  "digest": "3f9c…",
  "signature": {
    "alg": "ed25519",
    "pubkey": "e54e0984…",
    "signature": "…",
    "signed_at": 1783899860,
    "ttl": 300,
    "expires_at": 1783900160
  }
}
```

`reasons` is the human-readable "why" (criticals first). `signals` is the full scored breakdown. `evidence` is the raw record the verdict was built from. `digest` is the sha256 of the canonical verdict; `signature` is the Ed25519 envelope over it — verify with the key at `GET /pubkey`, and reject if `now > expires_at`. Resolve by name with `GET /verify?name=Otto%20AI` (exact match only — it never guesses).

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Requires the `onchainos` CLI on PATH (or set ONCHAINOS_BIN).
python cli.py 2118          # Otto AI      -> SAFE
python cli.py 3733          # Scope        -> CAUTION (1 sale)
python cli.py 2971          # non-ASP      -> BLOCK

# Run the server, then hit it:
uvicorn app:app --port 8000
#   curl "localhost:8000/verify?agentId=2118"

pytest -q                   # 31+ tests
bash scripts/demo.sh        # the 90-second demo
```

Environment knobs in [`.env.example`](.env.example): `ONCHAINOS_BIN`, `PROBE_TIMEOUT`, `CACHE_TTL`, `ORACLE_SIGNING_KEY`, `ORACLE_VERDICT_TTL`.

## Roadmap

1. **Ship the free endpoint** — register `GET /verify` as a free A2MCP tier on OKX.AI. Get listed fast. *(server + signing + tests done; deploy + registration are the next gates — see DEPLOY.md.)*
2. **Broaden the signals** — dispute history, delivery latency, fee-drift over time, per-service scoring (score the exact service the caller will use), cross-agent reference checks.
3. **Paid x402 tier** — a metered, higher-assurance verification tier once the free endpoint has traction.

## Why it matters beyond the hackathon

Counterparty and signing safety is the same problem a hardware wallet solves for humans, one layer up: *should this transaction happen, with this counterparty, right now?* The agent economy needs that check to be a callable service — which is directly relevant to **Ledger**.
