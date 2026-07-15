# Google form answers - KYA (OKX $100K, due Jul 17 23:59 UTC)

Every field pre-filled with REAL values from the live service and the marketplace sweep.
I do not have the exact form, so this is the standard hackathon field set; map each answer to
the matching field. Fields needing you are marked **[YOU]**. Copy-paste ready.

---

**Project name**
KYA - Know Your Agent

**One-line tagline**
Don't rate agents. Price them. KYA returns a signed trust verdict on any OKX.AI agent plus the dollar ceiling you should risk on it, before you transact.

**What it does (2-3 lines)**
On OKX.AI, agents hire and pay each other. Everyone vets tokens and wallets; nobody vets the agents themselves. KYA is the missing primitive: your agent calls KYA before paying or hiring a counterparty and gets back a signed SAFE/CAUTION/BLOCK verdict, then refuses to transact on BLOCK. Verdicts come from settled on-chain reputation, live endpoint probing, malicious-host scanning, and reviewer-integrity analysis - not a star rating.
A star rating is an opinion; a ceiling is a decision. KYA converts trust into **`max_safe_usd`** - the dollar amount this agent has actually earned the right to be trusted with, derived from settled volume rather than review counts, so it cannot be inflated by wash trading or a review ring.

**Category / track**
**Software Utility** (the ASP is registered on OKX.AI under `SOFTWARE_SERVICES`) / trust infrastructure. (Positioning: CertiK is OKX's *token* security partner; KYA is the *agent* one.)

**Live URL (deployed, working)**
https://kya-production-f846.up.railway.app
- Try it: https://kya-production-f846.up.railway.app/verify?agentId=2118  (Otto AI -> SAFE, score 100, **max_safe_usd 0.66**, signed)
- Watchtower board: https://kya-production-f846.up.railway.app/watchtower
- WOLF passport: https://kya-production-f846.up.railway.app/passport?agentId=3820
- Public key (verify verdicts offline): https://kya-production-f846.up.railway.app/pubkey

**Registered ASP / Agent ID**
KYA · Agent ID #5290 · service type A2MCP · fee 0 (free) · endpoint /verify · listing under review (submitted on-chain). Callable now via the Agent ID or the endpoint.

**How it uses OKX / Onchain OS**
Reads live OKX.AI marketplace records via onchainos (settled sales, endpoints, reviews, online status), probes each agent's x402/A2MCP endpoints, and runs a distinct-payer wash check against X Layer settlement (OKLink). Registered as an ASP on OKX.AI (#5290) on X Layer. It makes OKX's own agent marketplace safer to transact in.

**Proof it is real (not a toy)**
KYA has verified **every listed agent on the OKX.AI marketplace** live - 400 at time of writing - and holds the signed verdicts on a persistent board: **13 CLEARED / 360 WARY / 27 WOLF**. Only ~3% earn a clear verdict; 27 are flagged for a hard failure (dead endpoint, review-ring, or not a real provider). Not five hand-picked examples: the whole marketplace, re-runnable, with verdicts sitting warm for any caller. Every verdict is Ed25519-signed and time-bounded. **113 automated tests**, two adversarial red-team passes.

**Tech stack**
Python + FastAPI, SQLite (persistent volume), Ed25519 signing, onchainos CLI, OKLink X Layer settlement reader, deployed on Railway. Pure gated scoring engine (no I/O) that is unit-tested and adversarially reviewed.

**Team**
**[YOU]** - name + contact (solo build unless you add collaborators).

**Demo video link**
**[YOU]** - paste the <=90s recording (see demo-shotlist.md).

**X post link (#OKXAI)**
**[YOU]** - paste after posting (draft in draft-x-post.md).

**GitHub / source**
https://github.com/Morkeeth/kya-know-your-agent  (public - verified HTTP 200 on Jul 15; code + 113 tests + README + deploy docs)

**Anything else / what's next**
Trust as a timeline, not a snapshot: KYA persists every verdict and re-verifies on change, so a patched dead endpoint or a silently poisoned tool description flips and shows on /changes. On-chain distinct-payer wash gate is built and tested, default-off pending an OKLink key (one-step enable documented).

---

## Submit-time reminders
- **Deadline: Jul 17, 23:59 UTC.**
- **Order matters: post on X FIRST**, then fill this form — the form requires a link to the X post.
- 🚨 **CORRECTED Jul 15: ASP #5290 approval IS required.** The old line here ("approval is NOT
  required to submit") was wrong. Official rules Step 2: *"Your ASP must pass OKX AI's internal
  review and go live to remain eligible. If the ASP listing is not approved or cannot go live, your
  hackathon submission will be deemed invalid."* Verified Jul 15 07:23 UTC: `Listing under review`,
  status `not listed`. Submitting the form is necessary but NOT sufficient — the listing must go live.
- Do not re-activate or change the listing (already under review; re-activating is a no-op).
- Demo content cap: **90 seconds**.
- ⚠️ **THE NUMBERS IN THIS FILE ROT.** The marketplace grows: the sweep was 371 agents on Jul 14 and
  **400 on Jul 15** (spread moved 15/334/22 → 13/360/27). Test count moved 103 → 113 in a day.
  **Re-verify immediately before pasting into the form** (`/watchtower` for the spread,
  `.venv/bin/python -m pytest -q` for tests), and keep the phrasing "every listed agent (N at time of
  writing)" so a stale N reads as a timestamp, not a false claim. Numbers verified Jul 15 07:4x UTC.
