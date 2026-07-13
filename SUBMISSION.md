# KYA — OKX.AI Genesis Hackathon submission kit

**Deadline: Jul 17 2026, 23:59 UTC.** Valid submission = ASP **built + approved & listed** on OKX.AI + an **X post (#OKXAI)** + the **Google form**. The approve+list review is ≤24h, so **register early**.

Critical path (the long poles are yours — I've made them zero-friction):
**deploy → register → activate (review ≤24h) → demo → X post → form.**

---

## 1. Framing (the pitch, one breath)

> Agents on OKX.AI hire and pay each other blind. Everyone's building services that vet *tokens* and *wallets* — **nobody vets the agents themselves.** KYA is the missing trust primitive: call it before you transact and get a signed SAFE/CAUTION/BLOCK verdict on the counterparty agent. It makes OKX's own marketplace safer to transact in.

- **Track:** Trust-infra / **Finance Copilot** / Software Utility. Lead with "the reputation/trust layer the marketplace is missing" (OKX keeps naming this lane — CertiK is their *token* security partner; KYA is the *agent* one).
- **Why it's real, not a toy:** it checks the receipts — settled volume (not wash-tradeable counts), live endpoint behaviour, **malicious-endpoint scanning**, and **reviewer-integrity** (self-review / sybil-ring detection). Every verdict is Ed25519-signed + time-bounded.

## 2. Deploy (Railway — ~10 min)

1. Push this repo to GitHub (private is fine).
2. Railway → New Project → Deploy from repo. It auto-detects the `Dockerfile`.
3. Env vars:
   - `ORACLE_SIGNING_KEY` = `python -c "import os;print(os.urandom(32).hex())"` (so verdict signatures survive redeploys)
   - *(optional, recommended)* `OKX_API_KEY` / `OKX_SECRET_KEY` / `OKX_PASSPHRASE` — a personal key from the [OKX dev portal](https://web3.okx.com/onchain-os/dev-portal) for un-throttled reads. The bundled shared key works for the demo; add the personal key if you hit rate limits.
   - `PORT` is provided by Railway.
4. Grab the public URL, smoke it:
   ```
   curl "https://<host>/health"
   curl "https://<host>/verify?agentId=2118"   # Otto AI -> SAFE
   open "https://<host>/passport?agentId=2118"  # the passport SVG
   ```
   → **This URL becomes the ASP endpoint and is permanent on-chain. Pick the final host before registering.**

## 3. Register + list the ASP (your local, logged-in `onchainos`)

Run the `okx-ai` ASP flow (role `asp`). Details to paste:

- **Agent name (brand, 3–25 chars):** `KYA`
- **Agent description (≤500 chars):**
  > KYA (Know Your Agent) verifies any OKX.AI agent before you transact with it — returning a signed SAFE / CAUTION / BLOCK trust verdict from settled reputation, live endpoint checks, malicious-endpoint scanning, and reviewer-integrity analysis.
- **Avatar (required):** save the KYA eye/wordmark logo as a PNG and upload it (`agent upload --file <path>`).
- **Service:**
  - `serviceName` (5–30 chars): `Agent Trust Verdict`
  - `serviceType`: `A2MCP`
  - `fee`: `0`  (free — fastest to list; monetize later)
  - `endpoint`: `https://<host>/verify`
  - `serviceDescription` (2 parts, on separate lines, no links/tech-names/disclaimers):
    ```
    Returns a signed SAFE / CAUTION / BLOCK trust verdict on any OKX.AI agent, from settled reputation, live endpoint checks, malicious-endpoint scanning and reviewer-integrity analysis. For any agent about to hire or pay a counterparty ASP.
    1. the target agent's ID
    ```
- Pass `validate-listing` → `create` → **`activate`** (this submits to review, ≤24h). It's usable via its Agent ID even before approval.

## 4. Demo (≤90s — the passport is the hero)

Narrative (record screen):
1. "Before an agent pays a counterparty, it calls KYA." Show `curl https://<host>/verify?agentId=2118` → **SAFE**, signed.
2. Open `/passport?agentId=3820` → the **WOLF** passport (red slashed eye): "listed and 'online' — but KYA probed the endpoint and it's dead. Blocked."
3. One line on the receipts: "not a star rating — settled volume, a live malicious-endpoint scan, and it audits *who* left the reviews."
4. Close on the eye: "KYA. Know Your Agent."

`bash scripts/demo.sh` gives the CLI version of the same three-beat story for a fallback.

## 5. X post draft (#OKXAI) — *do not post until you approve*

> Meet KYA — Know Your Agent. 👁️
>
> On OKX.AI, agents hire and pay each other blind. Everyone vets tokens; nobody vets the *agents*.
>
> KYA is the trust layer: call it before you transact → a signed SAFE / CAUTION / BLOCK verdict on the counterparty. It checks the receipts — real settled volume, live endpoint + malicious-host scanning, and it audits *who* reviewed whom.
>
> Built on @OKX Onchain OS / X Layer. #OKXAI
> kya.fyi
>
> [attach the ≤90s demo]

## 6. Google form answers (draft)

- **Project name:** KYA — Know Your Agent
- **What it does (1–2 lines):** A trust oracle for the agent economy. Call it before transacting with any OKX.AI agent and get a signed SAFE/CAUTION/BLOCK verdict from settled reputation, live endpoint + malicious-host scanning, and reviewer-integrity analysis — the agent-vetting primitive the marketplace is missing.
- **ASP name / Agent ID:** KYA / `#<id from activate>`
- **Service type:** A2MCP (free endpoint), Ed25519-signed verdicts
- **X post link:** `<paste after posting>`
- **Category:** Finance Copilot / Software Utility (trust infrastructure)

---

## Status checklist
- [x] ASP built (gated verdict engine, signed + time-bounded)
- [x] Substance: liveness, malicious-endpoint scan (A1), reviewer-integrity (A2), volume-weighted reputation
- [x] Brand + passport/seal (KYA lime-on-black, eye verdict)
- [x] Demo script, deploy staging (Dockerfile/DEPLOY.md)
- [ ] **Deploy to Railway** ← you (long pole)
- [ ] **Register + activate** ← you (submits to ≤24h review)
- [ ] Record demo · [ ] X post · [ ] Google form
