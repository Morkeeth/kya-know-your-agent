# Deploying The Oracle

The service is a single FastAPI app that shells the `onchainos` CLI for OKX.AI
marketplace data and probes ASP endpoints for liveness. It needs a public HTTPS
URL (that URL becomes **permanent on-chain** once the ASP is registered, so pick
the final host before you register).

## ⚠️ Gates that are Oscar's to cross (not automated)

1. **Deploy to a public host** (Railway/Fly/Render). Picks the permanent URL.
2. **onchainos auth in the container.** Read calls (`agent service-list`,
   `agent search`) run on the CLI's bundled shared key, which may be
   rate-limited under load. For production, mint a **personal API key** at the
   [OKX dev portal](https://web3.okx.com/onchain-os/dev-portal) and wire it in.
   *TODO to verify at deploy time: whether read calls succeed in a fresh
   container with no wallet login, or require an AK/personal key.*
3. **ASP registration + activation** (permanent, on-chain, human-reviewed).
4. **x402 paid tier** (money) — out of scope for the free-endpoint MVP.

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
   ```
   curl "https://<host>/health"
   curl "https://<host>/verify?agentId=2118"   # Otto AI -> SAFE
   curl "https://<host>/pubkey"
   ```

## Then register the ASP (the onchainos flow, Oscar-driven)

`agent pre-check --role asp` → provide brand name + avatar + 2-part service
description → `serviceType:"A2MCP"`, `fee:"0"` (free), `endpoint:"https://<host>/verify"`
→ `validate-listing` → `create` → `activate`. See the OKX `okx-ai` skill
(`references/identity-register.md`) for the exact prompts.
