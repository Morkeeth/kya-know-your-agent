# Wash gate - on-chain distinct-payer Sybil killer (currently OFF)

**Status: built, tested (`tests/test_settlement.py`), and DEFAULT-OFF.** No OKLink key
is present in env/secrets as of 2026-07-14, so it is correctly disabled - KYA never
claims settlement analysis it did not run (`no_fake_data`).

## Why it exists
OKX's marketplace API returns `buyerCount: null`, so a wash-trader can post N sub-cent
sales from 1–2 wallets and the count-based reputation gate can't see the concentration.
But x402 sales settle as **real on-chain stablecoin transfers** into the agent's wallet,
so the distinct *senders* are the distinct buyers. `settlement.py` reads them from
OKLink's X Layer `token-transaction-list` and hands the engine `{distinct_payers,
onchain_volume, per-payer totals}` for concentration / wash analysis.

## Enable - exactly two steps

**Step 1 - provide a key and flip the flag (Railway env):**
```
OKLINK_API_KEY = <key from https://web3.okx.com/onchain-os/dev-portal>   # or OKX_API_KEY
KYA_SETTLEMENT = 1
```
`enabled()` requires BOTH. Redeploy.

**Step 2 - verify the one unproven assumption on a REAL settled tx (do NOT skip):**
The distinct-payer count is only valid if an inbound transfer's `from` is the **buyer**,
not an OKX facilitator/settlement contract. If OKX routes buyer → facilitator → agent,
every `from` is the facilitator and `distinct_payers` collapses to 1 (false wash flag).
Check it against one real settlement before trusting the gate:
```
# pick a proven agent's wallet (e.g. Otto #2118), pull one inbound USDT transfer:
curl -s "https://www.oklink.com/api/v5/explorer/address/token-transaction-list?chainShortName=XLAYER&address=<AGENT_WALLET>&protocolType=token_20&tokenContractAddress=0x1e4a5963abfd975d8c9021ce480b42188849d41d&limit=5" \
  -H "OK-ACCESS-KEY: $OKLINK_API_KEY" | jq '.data[0].transactionLists[] | {from,to,amount}'
```
- `from` looks like many distinct buyer EOAs across txs → assumption holds → trust it, ship.
- `from` is one constant facilitator/contract address → gate is invalid → keep it OFF and
  switch the payer signal to a different source. Do not enable on a facilitator `from`.

Until Step 2 passes on real chain data, the gate stays off by design.
