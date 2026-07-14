# Google form answers - KYA (OKX $100K, due Jul 17 23:59 UTC)

Every field pre-filled with REAL values from the live service and the marketplace sweep.
I do not have the exact form, so this is the standard hackathon field set; map each answer to
the matching field. Fields needing you are marked **[YOU]**. Copy-paste ready.

---

**Project name**
KYA - Know Your Agent

**One-line tagline**
The trust layer for the agent economy: a signed SAFE / CAUTION / BLOCK verdict on any OKX.AI agent, before you transact with it.

**What it does (2-3 lines)**
On OKX.AI, agents hire and pay each other. Everyone vets tokens and wallets; nobody vets the agents themselves. KYA is the missing primitive: your agent calls KYA before paying or hiring a counterparty and gets back a signed SAFE/CAUTION/BLOCK verdict, then refuses to transact on BLOCK. Verdicts come from settled on-chain reputation, live endpoint probing, malicious-host scanning, and reviewer-integrity analysis - not a star rating.

**Category / track**
Trust infrastructure / Finance Copilot / Software Utility. (Positioning: CertiK is OKX's *token* security partner; KYA is the *agent* one.)

**Live URL (deployed, working)**
https://kya-production-f846.up.railway.app
- Try it: https://kya-production-f846.up.railway.app/verify?agentId=2118  (Otto AI -> SAFE, signed)
- Watchtower board: https://kya-production-f846.up.railway.app/watchtower
- WOLF passport: https://kya-production-f846.up.railway.app/passport?agentId=3820
- Public key (verify verdicts offline): https://kya-production-f846.up.railway.app/pubkey

**Registered ASP / Agent ID**
KYA · Agent ID #5290 · service type A2MCP · fee 0 (free) · endpoint /verify · listing under review (submitted on-chain). Callable now via the Agent ID or the endpoint.

**How it uses OKX / Onchain OS**
Reads live OKX.AI marketplace records via onchainos (settled sales, endpoints, reviews, online status), probes each agent's x402/A2MCP endpoints, and runs a distinct-payer wash check against X Layer settlement (OKLink). Registered as an ASP on OKX.AI (#5290) on X Layer. It makes OKX's own agent marketplace safer to transact in.

**Proof it is real (not a toy)**
KYA has verified all 371 listed OKX.AI agents live and holds the signed verdicts on a persistent board: 15 SAFE / 334 CAUTION / 22 BLOCK. Only ~4% earned SAFE; 22 are flagged for a hard failure (dead endpoint, review-ring, or not a real provider). Every verdict is Ed25519-signed and time-bounded. 103 automated tests, two adversarial red-team passes.

**Tech stack**
Python + FastAPI, SQLite (persistent volume), Ed25519 signing, onchainos CLI, OKLink X Layer settlement reader, deployed on Railway. Pure gated scoring engine (no I/O) that is unit-tested and adversarially reviewed.

**Team**
**[YOU]** - name + contact (solo build unless you add collaborators).

**Demo video link**
**[YOU]** - paste the <=90s recording (see demo-shotlist.md).

**X post link (#OKXAI)**
**[YOU]** - paste after posting (draft in draft-x-post.md).

**GitHub / source**
**[YOU]** - the repo has no public remote yet. If the form requires a link, push to a private/public GitHub repo and paste it, or share access. Say the word and I will prep the push.

**Anything else / what's next**
Trust as a timeline, not a snapshot: KYA persists every verdict and re-verifies on change, so a patched dead endpoint or a silently poisoned tool description flips and shows on /changes. On-chain distinct-payer wash gate is built and tested, default-off pending an OKLink key (one-step enable documented).

---

## Submit-time reminders
- ASP #5290 listing approval is NOT required to submit; if still "under review" at the deadline, submit anyway (the live endpoint + Agent ID work regardless).
- Do not re-activate or change the listing.
