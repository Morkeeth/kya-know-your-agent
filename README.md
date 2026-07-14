# KYA - Know Your Agent 👁️

### Don't rate agents. Price them.

**The trust layer for the agent economy.** On OKX.AI, agents hire and pay each other blind. Everyone vets tokens and wallets; **nobody vets the agents themselves.** Before your agent pays or hires a counterparty, call KYA and get back a signed `SAFE` / `CAUTION` / `BLOCK` verdict **and a dollar ceiling** on that counterparty - and refuse to transact when it says BLOCK.

Everyone else returns a score. KYA returns **`max_safe_usd`**: the largest single transaction you should extend to this agent, *earned* from its proven settled volume and included in the signed payload. The WOLF gets `$0`; a proven agent gets a real, earned number. Trust, priced in dollars.

**Live:** https://kya-production-f846.up.railway.app · **ASP:** OKX.AI Agent #5290 · **Verdicts are Ed25519-signed.**

```bash
curl "https://kya-production-f846.up.railway.app/verify?agentId=2118"   # Otto AI -> SAFE, signed
```

---

## The problem (why this is necessary)

Connecting an AI agent or MCP server is running someone else's code with a wallet and your tools. Today you either trust it blind, or you do what a security team does - a slow, manual review that is obsolete the moment the counterparty ships an update. There is no `npm audit` for agents. KYA is that missing primitive: a callable, signed, continuously re-checked verdict on any agent, built from the attack classes that actually happen in this market.

A star rating is a claim. KYA checks the receipts.

## What KYA checks - the threat model

KYA covers both halves of the problem: an agent's **reputation and endpoint**, and the **content it exposes**. Each maps to a documented agent/MCP attack class.

| Attack class | KYA's check |
|---|---|
| **Rug pull** (approved clean, turns malicious later) | Persisted verdicts + **re-verification on change**; a flip is recorded on `/changes` |
| **Tool poisoning** (hidden instructions in a tool description) | Content scanner: injected instructions, secret-exfil, zero-width/bidi unicode → BLOCK |
| **Fake / wash-traded reputation** | Sample-size-aware **Wilson** reputation + on-chain **distinct-payer** wash gate (X Layer settlements) |
| **Impersonation / endpoint-borrowing** | `.well-known` domain-binding + x402 `payTo` cross-check |
| **Dead / hijacked / parked endpoint** | Behaviour-aware liveness probe (POST+GET; x402/api = serving, off-host redirect = hijacked) |
| **Malicious / drainer endpoint** | OKX phishing/blacklist host scan |
| **Reviewer rings / self-review** | Reviewer-wallet integrity audit |
| **KYA attacking itself** (SSRF) | The prober refuses internal/loopback/cloud-metadata targets |

## SAFE must be earned

Every *listed* ASP already passed OKX review, is online, and has a live endpoint - that is table stakes, not trust. So the engine is **gated, not additive**: it starts neutral, adds signal deltas, then clamps to the **lowest cap** any signal imposed. One hard failure overrides a pile of good signals - you cannot buy back a dead endpoint or a poisoned tool with a nice rating.

Bands: **SAFE** ≥ 70 · **CAUTION** 45–69 · **BLOCK** < 45. Every verdict carries a **confidence** (thin evidence itself caps at CAUTION).

### It discriminates on real agents (no rubber-stamping)

| Agent | ID | Verdict | Why |
|---|---|---|---|
| Otto AI | #2118 | **SAFE** | 216 settled sales, all endpoints serving, x402 valid |
| Onchain Data Explorer | #2023 | **SAFE** | 800+ sales, live, clean |
| Scope | #3733 | **CAUTION** | Barely proven, one sale |
| WhalePulse | #3369 | **CAUTION** | Live but unproven, nobody has used it |
| Sentiment Oracle | #3820 | **BLOCK** | Listed & online, but endpoints broken and zero settled sales |

**At marketplace scale, not hand-picked:** KYA has verified **all 371 listed OKX.AI
agents** live and holds the signed verdicts on a persistent board
([/watchtower](https://kya-production-f846.up.railway.app/watchtower)). The spread:
**15 SAFE · 334 CAUTION · 22 BLOCK.** Only 4% of listed agents have *earned* SAFE
via real settled reputation, and 22 are flagged for a hard failure (broken endpoint,
review-ring, or not a real provider). Listed is table stakes; trusted is earned.

## Trust is cryptographic, and a timeline

- **Signed:** each verdict signs `sha256(canonical verdict) + issued_at + ttl` with a key KYA controls; the public key is at `/pubkey`. A consumer pins it once and verifies every verdict **offline** - a rogue oracle can't ship its own key and self-sign SAFE.
- **A timeline, not a snapshot:** a verdict is only trustworthy inside its TTL. KYA persists every verdict, re-verifies when an agent changes, and records the transition - so a patched dead endpoint or a silently poisoned tool description **flips** and shows up on `/changes`. A point-in-time review can't do that.

## See it

```bash
python scripts/demo_caller.py 2118 2023 3820   # KYA gating real payments: pay / pay / REFUSE
python scripts/demo_flip.py                    # patched dead endpoint -> BLOCK->SAFE re-verify
python scripts/demo_poison.py                  # silent tool-poisoning -> SAFE->BLOCK rug-pull
open  https://kya-production-f846.up.railway.app/watchtower               # live verdict board + crossings
open  https://kya-production-f846.up.railway.app/passport?agentId=3820    # the WOLF passport
```

`demo_caller.py` is the reference **integration**: a buyer agent that fetches KYA's verdict, verifies the signature against a pinned key, and refuses the payment on BLOCK. That is how you use KYA.

## Architecture

Python, split so the trust logic stays pure and unit-testable:

```
oracle/
  engine.py      Pure gated scoring. No I/O. dicts in -> signed Verdict out. The trust logic.
  data.py        I/O: onchainos marketplace record + SSRF-guarded endpoint probing.
  content.py     Tool-poisoning / prompt-injection scanner over exposed text.
  settlement.py  On-chain distinct-payer wash gate (OKLink X Layer). Default-off until keyed.
  signing.py     Ed25519 sign/verify of the verdict digest + freshness window.
  store.py       SQLite: verdict history, re-verify-on-change transitions, uptime.
  watchtower.py  The live verdict board (KYA passport identity).
app.py           FastAPI: /verify /pubkey /health /passport /seal /history /changes /watchtower
scripts/         demo_caller, demo_flip, demo_poison, smoke, demo.sh
tests/           103 tests incl. wash-trade, dead-endpoint, SSRF, and tool-poisoning regressions.
```

`engine.py` has no network or subprocess dependency - the part that decides "should money move" is small, pure, and adversarially tested (two red-team passes; every fix locked with a regression).

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python cli.py 2118           # Otto AI -> SAFE   (needs the `onchainos` CLI on PATH)
uvicorn app:app --port 8000  # then: curl localhost:8000/verify?agentId=2118
pytest -q                    # 103 tests
```

Env knobs (`.env.example`): `ORACLE_SIGNING_KEY` (stable signatures across redeploys), `KYA_DB_PATH` (persist history on a volume), `PROBE_TIMEOUT`, `CACHE_TTL`, `KYA_SETTLEMENT` + `OKLINK_API_KEY` (enable the on-chain wash gate).

## Status

Live and deployed on Railway; ASP #5290 registered on OKX.AI (listing review in progress). The on-chain distinct-payer wash gate is built and tested but **default-off** pending an OKLink key + a one-tx check that the settlement `from` is the buyer, not a facilitator.

## Why it matters beyond the hackathon

"Should this transaction happen, with this counterparty, right now?" is the question a hardware wallet answers for humans - one layer up, for agents. The agent economy needs that check to be a callable, signed, always-fresh service. That is KYA.
