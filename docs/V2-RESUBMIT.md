# KYA V2 — re-submit kit

You built v1 in an hour. V2 turns it from "a signed verdict" into **a trust system with memory, hardened against the attacks a security judge will actually try.** Same ASP (#5290), same endpoint — the depth ships by **redeploying the same code to the same Railway URL.** The on-chain listing already points at `/verify`; no re-registration required.

---

## What changed (the pitch upgrade)

| V1 | V2 |
|---|---|
| One-shot signed verdict | **Trust is a timeline** — every verdict persisted; a patched agent is **re-verified** and its BLOCK→SAFE flip recorded on `/changes` |
| Prober fetched any URL | **SSRF-hardened** — refuses endpoints aimed at internal/cloud-metadata infra (a trust product can't have that hole) |
| Star-average reputation | **Wilson lower-bound** — sample-size-aware; catches mixed-review agents volume alone waves through, without punishing honest new agents |
| Scored the agent | **Anti-impersonation** — checks the endpoint's `.well-known` domain-binding + x402 `payTo`, catching endpoint-borrowing and fund-diversion |
| Single liveness probe | **Rolling uptime/latency** — a flapping endpoint (<95%) can't hold SAFE on one lucky probe |

All verified: **81 tests green**, live discrimination stable (Otto/Explorer SAFE, #3820 BLOCK).

---

## 1. Deploy (same Railway project, same URL)

1. Push the branch (`night-run-2026-07-13`) / merge to the deployed branch.
2. Railway redeploys the `Dockerfile` automatically.
3. **New env var for history to survive redeploys:** mount a Railway **volume** and set `KYA_DB_PATH=/data/kya.db`. Without a volume, `kya.db` is ephemeral (history resets each deploy — fine for the demo, not for production).
4. Smoke it:
   ```
   curl "https://kya-production-f846.up.railway.app/verify?agentId=2118"   # SAFE, signed
   curl "https://kya-production-f846.up.railway.app/verify?agentId=2118"   # again -> "revalidated": true
   curl "https://kya-production-f846.up.railway.app/history?agentId=2118"  # the timeline
   curl "https://kya-production-f846.up.railway.app/changes"               # recent transitions
   ```

## 2. (Optional) refresh the listing to advertise the depth

The description can be updated to sell the new capabilities, then re-activate:
```
onchainos agent update --agent-id 5290 --description \
"KYA (Know Your Agent) verifies any OKX.AI agent before you transact. Signed SAFE/CAUTION/BLOCK trust verdicts from settled reputation (sample-size-aware), live SSRF-hardened endpoint checks, anti-impersonation (domain-binding + x402 payTo), reviewer-integrity, and re-verification-on-change — trust as a timeline, not a snapshot."
onchainos agent activate --agent-id 5290
```
⚠️ `activate` resubmits to the ≤24h review — do it with buffer before Jul 17. If the current review already passes, you may not need to touch the listing at all.

## 3. Demo (≤90s) — now shows DEPTH, hero = the re-verify flip

Record backward from the flip:

| # | Shot | Say |
|---|------|-----|
| 1 — cold open | KYA wordmark | "Agents on OKX.AI hire and pay each other blind. Everyone vets tokens — nobody vets the agents." |
| 2 — SAFE | `/verify?agentId=2118` → SAFE, signed | "Otto — 188 settled sales, all endpoints serving, x402 valid. Signed SAFE." |
| 3 — WOLF | `/passport?agentId=3820` → red slashed eye | "Sentiment Oracle — listed and online, but 0 settled sales and broken responses. WOLF. Turned away." |
| 4 — **HERO: trust decays** | `/verify?agentId=3820` twice, then `/changes` | "Call it again — `revalidated: true`. KYA remembers. When an agent patches a dead endpoint, KYA re-verifies and records the flip — BLOCK → SAFE, on `/changes`. Trust is a timeline." |
| 5 — security | the SSRF refusal (a fixture agent pointing at `169.254.169.254`) → BLOCK "internal infrastructure" | "A hostile agent points its endpoint at cloud metadata. KYA refuses to even probe it — and blocks it. A trust oracle can't have an SSRF hole." |
| 6 — close | the eye | "KYA. Know Your Agent." |

*(Drop shot 5 or 6 if over 90s. The `bash scripts/demo.sh` CLI fallback still works for beats 2-3.)*

## 4. X post (#OKXAI) — V2

> KYA — Know Your Agent. 👁️ v2.
>
> On OKX.AI, agents hire and pay each other blind. Everyone vets tokens; nobody vets the *agents*.
>
> KYA is the trust layer: a signed SAFE / CAUTION / BLOCK verdict on any counterparty. v2 goes deeper —
> • trust is a **timeline**: it re-verifies a patched agent and records the flip
> • **SSRF-hardened** probing (a trust oracle can't be the hole)
> • sample-size-aware reputation + **anti-impersonation** (domain-binding + x402 payTo)
>
> Built on @OKX Onchain OS / X Layer. #OKXAI
> kya.fyi
>
> [attach ≤90s demo]

## 5. Google form fields

| Field | Value |
|---|---|
| Project name | KYA — Know Your Agent |
| What it does | A trust oracle for the agent economy with memory. Signed SAFE/CAUTION/BLOCK verdicts from sample-size-aware settled reputation, SSRF-hardened live endpoint checks, anti-impersonation (domain-binding + x402 payTo), reviewer-integrity, and re-verification-on-change. Trust as a timeline, not a snapshot. |
| ASP name / Agent ID | KYA / #5290 |
| Endpoint | https://kya-production-f846.up.railway.app/verify · `/history` · `/changes` · `/passport` |
| Service type | A2MCP (free), Ed25519-signed verdicts |
| X post link | ‹paste after posting› |
| Category | Finance Copilot / Software Utility (trust infrastructure) |

---

## Still open (two gates)

1. **Slice 5 — the Sybil killer (on-chain distinct-payer/wash detection).** Built-ready pending: an **OKLink `OK-ACCESS-KEY`** (OKX dev portal) + a one-tx check that inbound settlement `from` is the *buyer* not a facilitator contract (else distinct-payer counting collapses). Endpoint + parsing confirmed by the spike (`token-transaction-list`). Wire it on once the key + that check land.
2. **The human re-submit actions** — redeploy, record the ≤90s, post X, submit the form, (optional) `agent update`+`activate`.
