# Deploying KYA

The service is a single FastAPI app that shells the `onchainos` CLI for OKX.AI
marketplace data and probes ASP endpoints for liveness. It needs a public HTTPS
URL (that URL becomes **permanent on-chain** once the ASP is registered, so pick
the final host before you register).

## Prerequisites

1. **A public host** (Railway/Fly/Render). This picks the permanent URL.
2. **onchainos auth in the container.** Read calls (`agent service-list`,
   `agent search`) run on the CLI's bundled shared key, which may be
   rate-limited under load. For production, mint a **personal API key** at the
   [OKX dev portal](https://web3.okx.com/onchain-os/dev-portal) and wire it in.
   *TODO to verify at deploy time: whether read calls succeed in a fresh
   container with no wallet login, or require an AK/personal key.*
3. **ASP registration + activation** — permanent, on-chain, human-reviewed.
4. **Paid tier (optional).** `/audit` settles real USDT through OKX's own x402
   facilitator and self-disables when its creds are absent, so the free tier
   deploys fine without it. To enable it, set `KYA_AUDIT_PAYTO` plus the
   facilitator creds (see `.env.example`).

## Railway (recommended — matches what live competitors use)

1. Push this repo to GitHub.
2. New Railway project → Deploy from repo. It auto-detects the `Dockerfile`.
3. Set env vars (see `.env.example`):
   - `ORACLE_SIGNING_KEY` = `python -c "import os;print(os.urandom(32).hex())"`
     (so verdict signatures survive redeploys)
   - `ORACLE_VERDICT_TTL`, `PROBE_TIMEOUT`, `CACHE_TTL` as desired
   - `PORT` is provided by Railway automatically
4. Deploy → grab the public `https://…up.railway.app` URL.
5. Smoke it:
   ```bash
   curl "https://<host>/health"
   curl "https://<host>/pubkey"

   # /verify speaks x402: an UNPAID call must answer 402 + terms, not 200.
   # That is the marketplace hire path — a 200 here means the listing probe
   # reports valid:false. Expect HTTP 402:
   curl -i "https://<host>/verify?agentId=2118"

   # A caller presents X-PAYMENT. At the free tier's amount "0" nothing settles;
   # this is the zero-value payload a real x402 client sends. Expect Otto AI -> SAFE:
   XPAY=$(printf '%s' '{"x402Version":2,"scheme":"exact","network":"eip155:196","payload":{"amount":"0"}}' | base64 | tr -d '\n')
   curl -H "X-PAYMENT: $XPAY" "https://<host>/verify?agentId=2118"
   ```

## Then register the ASP (the onchainos flow)

`agent pre-check --role asp` → provide brand name + avatar + 2-part service
description → `serviceType:"A2MCP"`, `fee:"0"` (free), `endpoint:"https://<host>/verify"`
→ `validate-listing` → `create` → `activate`. See the OKX `okx-ai` skill
(`references/identity-register.md`) for the exact prompts.

**Avatar spec (learned the hard way, Jul 17 2026):** exactly **440×440 px**, **square
corners** (rounded/squircle avatars are rejected), high-res and sharp, and it must visually
match the agent's stated positioning. A listing rejected on the avatar is a listing that is
not live — and an ASP that is not live is not eligible.
