# KYA on ERC-8004 — Ambitious Revive Plan (2026-08-25)

> **One line.** KYA is the trust layer that doesn't rate agents, it *prices* them — a signed,
> per-counterparty **dollar ceiling** (`max_safe_usd`). ERC-8004 gave 173k agents a portable
> identity and a Reputation Registry, but the spec deliberately left the hard part — turning raw,
> Sybil-ridden feedback into a number an agent can act on — to "competitive reputation aggregation
> services" that don't exist yet. KYA is that service, and it already computes the one output nobody
> else does: how many dollars to extend.

**Confidence: WORTH A SPRINT** (not STRONG REVIVE — no distribution path or named consumer yet;
not PARK — the standard's own gaps are KYA's exact differentiators, cited below). Promotion trigger
at the end.

---

## 1. Day-two user (not Oscar)

**Primary: the buyer-side, x402-paying agent operator.** An agent that hires and pays other agents
per-call and needs to answer, before it signs, "how many dollars is it safe to extend to *this*
counterparty right now?" This is not hypothetical for KYA — `scripts/demo_caller.py` is already
exactly this integration (fetch verdict → verify Ed25519 signature offline → refuse payment on
BLOCK / cap the amount at `max_safe_usd`). Today it points at OKX.AI; it is one read-plane swap away
from pointing at an ERC-8004 registry. The EF has named **trading agents** as the primary ERC-8004
use case, so the population that needs a spend ceiling is the population the standard is built for.
([RedStone/Credora](https://blog.redstone.finance/2026/02/12/erc-8004-gives-ai-agents-identity-redstone-and-credora-power-them-with-data-and-risk-intelligence/))

**Secondary: agentic-wallet policy engines.** Per-agent spend limits are already a wallet-policy
primitive; the missing *input* is a trustworthy per-counterparty ceiling. KYA supplies the number the
policy enforces. (OKX's own agentic wallet ships limit-order / spend controls — the same shape.)

---

## 2. The wedge — why a dollar ceiling beats a score, cited

Every other player on ERC-8004 returns a **score or a rating**; KYA returns a **decision in dollars**.

- The empirical study of the live ERC-8004 ecosystem (173,441 agents, Jan–May 2026) states plainly:
  **"No spending limits or economic risk controls exist,"** and manipulating an agent's score costs
  **$0.0027 on Base / $0.0042 on BSC / $0.055 on Ethereum** — far below the value at stake.
  ([arXiv 2606.26028](https://arxiv.org/html/2606.26028))
- The same study: **98.7–100% of feedback carries no payment proof** — nobody checks the interaction
  even happened — and **59–91% of reviewers are Sybil** via shared funding. Remove flagged feedback
  and **77.9–86.8% of agents have zero valid feedback left.** A raw score built on this is noise.
  ([arXiv 2606.26028](https://arxiv.org/html/2606.26028))
- The spec itself hands the slot to off-chain aggregators that **"subscribe to NewFeedback events,
  filter out likely Sybil feedback…, compute weighted scores"** — but leaves *what number to emit*
  open. ([Everstake](https://everstake.one/resources/blog/erc-8004-explained-building-a-unified-framework-for-data-verification))
- The nearest incumbent, **Credora by RedStone**, produces **credit ratings and default-probability
  scores for protocols and assets** — not a per-counterparty transaction ceiling for one agent paying
  another. Adjacent, not overlapping.
  ([RedStone](https://blog.redstone.finance/2025/11/06/redstone-brings-credora-to-market-following-acquisition-introducing-defi-risk-ratings-to-morpho-and-spark/))

**Wedge sentence:** *Everyone on ERC-8004 rates an agent; KYA prices it — a signed, earned
`max_safe_usd` ceiling backed by on-chain payment proof and operator-graph Sybil filtering, which is
precisely the "spending limits / economic risk controls" the ratified ecosystem is documented to lack.*

KYA's two existing moats map 1:1 onto the study's two named failure modes:
| Documented ERC-8004 gap (cited) | KYA mechanism that already exists |
|---|---|
| "No spending limits or economic risk controls exist" | `max_safe_usd = settled_volume × multiplier × confidence` (`oracle/engine.py:43`) |
| "98.7–100% of feedback lacks payment proof" | on-chain distinct-payer wash gate (`oracle/settlement.py`) |
| "59–91% of reviewers are Sybil" | operator-graph: agents → controlling wallet (`/operators`) |

---

## 3. What EXISTS today vs. what's claimed

**Exists and verified live (2026-08-25):**
- Service is up: `GET /verify?agentId=2118` → HTTP 200, real signed verdict with `max_safe_usd:0.183`,
  Ed25519 signature, capped-score reasoning. `/health` → `{"ok":true,"signing_key_source":"env"}`.
- Pure, portable trust core: `oracle/engine.py` (gated scoring + ceiling, no I/O), `signing.py`
  (Ed25519 + freshness), `store.py` (verdict timeline, re-verify-on-change), operator clustering.
- Paid tier wired end-to-end (x402 `/audit`, 0.10 USDT settled on X Layer — self-funded test, soldCount 0).
- 172 tests passing at HEAD (`consolidate/kya-2026-07-17`).

**Claimed but NOT true / stale — honest flags:**
- **The live Railway deploy is stale.** `/health` returns no `upstream_session` field; the Aug-16 HEAD
  commit adds that field unconditionally. So production is running a **pre-Aug-16 build** — the
  session-degradation fix and its two tests are not deployed. Redeploy is step 0.
- **KYA is 100% OKX.AI-specific on the read plane.** `oracle/data.py` reads the onchainos marketplace
  (X Layer settlements, `agentId` integers, OKX approval status). The engine ports to ERC-8004; the
  entire *read plane does not*. This is the real cost of the revive — see §4.
- **"ERC-8004 ratified Jan-2026" (task CONTEXT) is imprecise.** It was **deployed to mainnet Jan 29,
  2026** and is widely adopted, but the ERC is still **Draft/Review**, not Final, and the **Validation
  Registry is "still under active discussion with the TEE community"** with **no mainnet deployment**
  observed in the study. ([EIP-8004](https://eips.ethereum.org/EIPS/eip-8004) ·
  [arXiv 2606.26028](https://arxiv.org/html/2606.26028)) This dictates build order (validation last).

---

## 4. Build path to a registered ERC-8004 provider — ordered by leverage

**Step 0 — Redeploy HEAD to Railway.** The live service is behind the repo. Ship `consolidate/kya-2026-07-17`
first so the demoed behavior matches the code. (~30 min, no new code.)

**Step 1 — New read plane: ERC-8004 on Base.** Add `oracle/erc8004.py` beside `data.py`. Read the
Identity Registry (ERC-721 + URIStorage) → resolve each agent's `/.well-known/agent-card.json` →
fetch endpoints, payment address, and Reputation Registry `giveFeedback` records. Base first: cheapest
chain, most agents per the study. **The engine is untouched** — feed it the same dict shape. Domain
binding (`agent-registration.json`) reuses KYA's existing `.well-known` cross-check.
([QuickNode guide](https://www.quicknode.com/blog/erc-8004-a-developers-guide-to-trustless-ai-agent-identity) ·
[contracts](https://github.com/erc-8004/erc-8004-contracts)) — *highest leverage: unlocks the whole ecosystem.*

**Step 2 — Ship the signed off-chain ceiling API (the aggregator slot).** No registration required to
start: subscribe to `NewFeedback` events, run feedback through the operator-graph Sybil filter, drop
records with no payment proof, emit a signed `max_safe_usd` + verdict over HTTP — exactly the
"competitive reputation aggregation service" the spec designs for. This is a **provider by consumption,
not by permission**: any agent can call it today, no on-chain registration gate exists for aggregators.
([Everstake](https://everstake.one/resources/blog/erc-8004-explained-building-a-unified-framework-for-data-verification))

**Step 3 — Write ceilings back on-chain via `giveFeedback`.** Mechanical fit already confirmed: the
Reputation Registry stores `value` as **`int128` + `valueDecimals` (uint8 0–18)**, so `max_safe_usd`
goes on-chain as a *structured number*, not prose — KYA can publish its ceiling as a first-class,
composable feedback record other contracts can read. ([contracts](https://github.com/erc-8004/erc-8004-contracts))
This is the on-chain-composability hook and the strongest "provider" signal short of validation.

**Step 4 — Validator role (`validationResponse`), only when the interface stops churning.** The
Validation Registry has request/response (`validationRequest(validator, agentId, requestURI, requestHash)`
→ `validationResponse(requestHash, response, responseURI, responseHash, tag)`) but zero mainnet
deployment and open TEE debate. KYA registering as a validator that attests spend-ceilings is the
ambitious end state — but building on an unshipped, churning interface is the *last* step, not the first.

---

## 5. Honest risks

- **Zero proven demand.** The Validation Registry's emptiness is greenfield *and* zero validated
  demand at once. Nobody has paid for an ERC-8004 spend ceiling because the primitive doesn't exist
  yet — which is the opportunity and the risk in one sentence.
- **No distribution.** Being callable ≠ being called. KYA has no channel into the ERC-8004 agent
  population. The aggregator slot is open precisely because distribution is unsolved.
- **Standard still churning.** Draft/Review, not Final; Validation Registry under active TEE
  discussion. Build against Identity + Reputation (stable, deployed); treat Validation as optional.
- **The read-plane rewrite is real work,** not a config flag. `data.py` assumes OKX end to end.
- **An incumbent is adjacent.** Credora/RedStone owns "risk intelligence for agents" mindshare even
  though its output is a score on assets, not a per-counterparty dollar ceiling. KYA must state the
  distinction loudly or be mistaken for a worse Credora.

---

## Verdict — WORTH A SPRINT, with a promotion trigger

Sprint scope = Steps 0–2 (redeploy + Base read plane + signed off-chain ceiling API on real
ERC-8004 agents). **Promote to STRONG REVIVE** if, within the sprint, KYA runs signed ceilings
against real Base-registry agents **and** one external party (not Oscar) consumes the ceiling — a
wallet policy engine, a buyer agent, or an on-chain `giveFeedback` read. **Park** if neither lands:
that would prove the gap is real but the distribution isn't, and a correct-but-unused oracle is not a
revive.

*Every ERC-8004 and market claim above carries an inline citation. The one claim resting on primary
inspection of KYA itself — the stale live deploy — is verified against `/health` output on 2026-08-25.*
