# KYA V2 Research Spec

Synthesized from four adversarially-verified research dimensions (ranking, sybil, sandbox, attestation, data). Every recommendation below is tied to a citation that survived verification. Claims that verification flagged `OVERSTATED`/`UNSUPPORTED` have been demoted or corrected inline and are called out explicitly.

**Current engine map (what these changes touch):**
- `oracle/engine.py` — `score_agent()`, the gated-additive scorer; reputation VOLUME gate (~L160), review-ring audit "A2" (~L217), `_confidence()` (~L287), thresholds `SAFE>=70 / CAUTION 45..69 / BLOCK<45`.
- `oracle/data.py` — `fetch_agent()`, `fetch_feedback()`, `probe_endpoints()` / `_probe_one()` (the HTTP prober, `follow_redirects=True` at L204), `_classify()`, `scan_malicious()`.
- `oracle/seal.py` / `oracle/signing.py` / `keys/` — the signer. The prober currently runs in-process with these. That is the load-bearing security problem.
- No persistence layer exists today. Several V2 items require adding one (SQLite is enough).

---

## 1. TL;DR — the 3 highest-leverage upgrades

1. **SSRF-harden the prober before the deadline.** `_probe_one` fetches an attacker-controlled URL with `follow_redirects=True` and zero IP validation, in the same process as the signing keys. This is both a credential-exfil hole (302 → `169.254.169.254`) *and* a poisoned data source (the agent controls what "healthy" looks like). Cheapest, highest-value, invisible-to-demo fix.
2. **Stop trusting `salesCount`; reconstruct distinct payers on-chain.** x402 settles as a real on-chain token transfer, so every genuine sale is a verifiable inflow to the agent's wallet. Reading OKLink X Layer inflows gives the distinct-buyer count that `buyerCount=null` makes "impossible" today — the single structural fix for wash-trade Sybil resistance.
3. **Replace hand-tuned reputation deltas with a principled estimator: Wilson lower-bound now, EigenTrust-weighted review graph in V2.** Wilson structurally enforces "SAFE must be EARNED" in ~15 lines with no new data; EigenTrust makes a swarm of fresh colluding wallets contribute ≈0 weight, closing the review-ring gap for real instead of heuristically.

---

## 2. Ship-now candidates (effort S, low-risk, land before Jul 17)

All of these are pure functions or single-file guards with no new data source. The SSRF items are **invisible to the demo** (no verdict changes on honest agents); the identity + Wilson items are **demo-visible** (they change scores and add new reasons/flags judges can see).

### S1 — SSRF: turn off redirect following `[INVISIBLE TO DEMO]`
`oracle/data.py:204` — set `follow_redirects=False`. A 3xx becomes its own probe category; do **not** auto-follow. If you must follow one hop, re-run the IP guard (S2) on the `Location` header first.
- Defends: redirect-to-metadata SSRF (302 → `http://169.254.169.254/latest/meta-data/` → IAM creds) and internal-RPC pivots reachable from the signer host.
- Verification note: the fix is sound; the research's "OWASP's single most-repeated control" framing was flagged **OVERSTATED** (OWASP ranks allowlisting > IP-validation > redirect-disabling). Ship it as defense-in-depth, not as the primary control — S2 is primary.
- Cite: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html

### S2 — SSRF: resolve + validate + pin the IP `[INVISIBLE TO DEMO]`
Add a pre-request guard in `_probe_one` (and the host-extraction paths): parse URL, enforce scheme ∈ `{http,https}`, `socket.getaddrinfo()` the host, reject if **any** resolved IP is private/loopback/link-local/reserved/multicast (`127/8, 10/8, 172.16/12, 192.168/16, 169.254/16, ::1, fc00::/7, fe80::/10`), then connect **to the validated IP** (see V2-A for the DNS-rebind pin — the S-version can at minimum resolve-and-check). Emit `internal_target` / `blocked_target` as a distinct probe class, never "healthy".
- Defends: direct SSRF to loopback (co-located RPC/signer), private X Layer infra, `169.254.169.254` IMDSv1 credential theft; also blocks decimal/hex-encoded address bypasses because you validate the parsed IP, not the string.
- Verification: **CONFIRMED**. Code fact confirmed — no `ipaddress`/resolve anywhere in `data.py`; raw string handed to httpx.
- Cite: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html · https://stytch.com/blog/securing-identity-apis-against-ssrf/

### S3 — SSRF: scheme + metadata denylist belt-and-braces `[INVISIBLE TO DEMO]`
In the same guard, reject any scheme not in `{http,https}`, optionally constrain ports to `{80,443, known x402 ports}`, and hardcode a reject for `169.254.169.254` / `fd00:ec2::254` even if the range check somehow misses it.
- Defends: scheme-smuggling (`file://`, `:6379` timing oracles) and a second layer against encoding tricks.
- Cite: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html

### S4 — Wilson lower-bound reputation term `[DEMO-VISIBLE]`
Replace the raw `securityRate` / review-fraction term in `score_agent` with the Wilson 95% lower bound on the positive-feedback fraction:
```
WilsonLB(pos, n, z=1.96) =
  (p + z²/2n − z·√((p(1−p) + z²/4n)/n)) / (1 + z²/n),  where p = pos/n
```
A thinly-reviewed agent is pulled toward zero and **cannot reach the SAFE band on reviews alone** — this is "SAFE must be EARNED" as a formula, not a hand-tuned delta. ~15-line pure function, no new data.
- Defends: thin-review self-promotion (2 perfect reviews outranking 100/1), and few-but-perfect wash campaigns.
- Verification: **CONFIRMED** (Evan Miller canonical; arXiv 1809.07694 corroborates the family).
- Cite: https://www.evanmiller.org/how-not-to-sort-by-average-rating.html · https://arxiv.org/pdf/1809.07694

### S5 — Benford + identical-amount wash test `[DEMO-VISIBLE]`
Add an anomaly sub-check over the existing settled-fee / sales series: first-significant-digit chi-square vs Benford, plus a coefficient-of-variation-near-zero detector for repeated identical amounts. Failing either forces `SAFE → CAUTION`. Pure function over data KYA already pulls; directly targets the `100× $0.001` hole because machine-generated identical sub-cent fees are exactly the non-organic signature.
- Verification: **CONFIRMED** (NBER w30783 / Cong-Li-Tang-Yang, *Management Science* 2023 — Benford + round-number clustering is the canonical fabricated-volume test). Caveat: the paper tests centralized-exchange reported volume; applying it to on-chain fee distributions is a reasonable transfer, not something the paper validates on-chain. Use as a `SAFE→CAUTION` gate, not a standalone BLOCK.
- Cite: https://www.nber.org/system/files/working_papers/w30783/w30783.pdf

### S6 — `.well-known/agent-registration.json` domain-binding gate `[DEMO-VISIBLE]`
After the endpoint probe, `GET {scheme}://{endpoint-host}/.well-known/agent-registration.json` and confirm a `registrations` entry matches the on-chain `(agentRegistry, agentId, chainId)` of the agent under review. Missing/mismatched → cap at CAUTION and **zero the endpoint-derived score**; matching → unlock full liveness credit. One GET, reuses the (now-hardened) prober.
- Defends: **endpoint-borrowing / impersonation** — agent B listing someone else's live, well-reviewed x402 endpoint as its own and inheriting its liveness + x402-correctness score for free. KYA is blind to this today.
- Verification: **CONFIRMED** against the EIP (mechanism is verbatim). Note: the spec frames this proof as OPTIONAL (`MAY`), so treat a missing file as "unverified → capped", not "malicious → blocked". The QuickNode citation does **not** support the specifics; rely on the EIP.
- Cite: https://eips.ethereum.org/EIPS/eip-8004

### S7 — x402 `payTo` identity cross-check `[DEMO-VISIBLE]`
Parse the 402 challenge `accepts[]`, validate `scheme=exact` + `network` + `asset` + `payTo` shape (not just `status==402`), and compare `payTo` against the agent's on-chain registered wallet(s). Match → full x402 credit + `payTo_verified` flag; mismatch → BLOCK-eligible red flag. No signing, just parse-and-compare; pairs with S6.
- Defends: **fund-diversion / endpoint re-hosting** — a legitimately-listed agent whose live endpoint routes payment to an attacker wallet; and malformed/spoofed 402s that pass a naive status check.
- Verification: **CONFIRMED** (x402 exact-EVM spec: facilitator cannot modify amount or destination; funds can only go to `payTo`). Field-name nuance: v1 `maxAmountRequired` → v2 `amount`; handle both.
- Cite: https://github.com/coinbase/x402/blob/main/specs/schemes/exact/scheme_exact_evm.md

### S8 — ERC-8004 `supportedTrust` / `x402Support` consistency check `[DEMO-VISIBLE]`
Parse `supportedTrust` (⊆ `{reputation, crypto-economic, tee-attestation}`) and `x402Support` from the registration/AgentCard. Add a `trust_claim_consistency` check: claims `x402Support:true` but probe returns non-402 → penalty; claims `tee-attestation` but no attestation retrievable → penalty. Turns a static registry field into an integrity signal at near-zero cost.
- Verification: **CONFIRMED** against the EIP (exact field names + the "if absent/empty, discovery-only, not trust" clause). The Allium citation does not support the specifics; anchor on the live EIP (it is a moving draft — read the spec, not overviews).
- Cite: https://eips.ethereum.org/EIPS/eip-8004

---

## 3. V2 build queue (ordered by leverage-per-effort)

### V2-A — DNS-rebind pin at connect time (finish the SSRF fix)
- **What:** small `httpx.HTTPTransport` subclass (or getaddrinfo + connect-by-IP with original `Host`/SNI preserved) so `_probe_one` connects to the single validated IP and never re-resolves. Use a fixed external resolver.
- **Module:** `oracle/data.py` (prober transport).
- **Attack:** DNS rebinding / TOCTOU — attacker returns a public IP on the validation lookup and a metadata/internal IP on the connect lookup. Naive resolve-then-fetch is the documented bypass.
- **Effort:** M. **Verification:** CONFIRMED (Craft CMS GHSA-gp2f-7wcm-5fhx; MCP Atlassian GHSA-489g-7rxv-6c8q).
- Cite: https://github.com/craftcms/cms/security/advisories/GHSA-gp2f-7wcm-5fhx · https://behradtaher.dev/DNS-Rebinding-Attacks-Against-SSRF-Protections/

### V2-B — On-chain settlement reader (the buyerCount=null killer)
- **What:** new `data.py` `fetch_settlements(wallet)` hitting the OKLink X Layer address transaction-list API, filtered to the USDC/USDT contract. Feed `engine.py` a dict `{onchain_volume, distinct_payers, claimed_vs_actual_ratio}`. Replace the `sales × eff_fee` heuristic: SAFE requires `onchain_volume` within tolerance of claimed **and** `distinct_payers >= N`; a `salesCount` unbacked by inflows caps at CAUTION/BLOCK.
- **Module:** `oracle/data.py` (new fetch) + `oracle/engine.py` (reputation gate ~L160).
- **Attack:** fabricated/inflated `salesCount` with no matching money; the distinct-buyer Sybil gap — on-chain payer addresses **are** the missing buyerCount.
- **Effort:** M. **Verification:** **OVERSTATED** on one point — x402 exact-EVM settles via EIP-3009 `transferWithAuthorization` for **USDC**, but **USDT does not support EIP-3009** and settles via the Permit2 scheme. Both are still on-chain token transfers (the data logic holds), but handle both settlement schemes; don't assume EIP-3009 for USDT. OKLink capability confirmed; exact endpoint URL not shown in docs — confirm on integration.
- Cite: https://github.com/coinbase/x402/blob/main/specs/schemes/exact/scheme_exact_evm.md · https://web3.okx.com/xlayer/onchaindata/docs/en/

### V2-C — Concentration index over payers/reviewers (HHI + top-1 share)
- **What:** compute a concentration metric (Herfindahl-Hirschman Index + top-1 counterparty share) over the reviewer-wallet multiset **now** (free, data already fetched), extended to distinct settlement senders once V2-B lands. Rule: SAFE requires top-1 share < ~40% **and** ≥ N distinct independent wallets; else cap at CAUTION.
- **Module:** `oracle/engine.py` (new signal feeding the VOLUME gate).
- **Attack:** sub-cent-wash-at-scale — 100× $0.001 from 2–3 controlled wallets shows HHI ≈ 1.0 even with healthy `salesCount` and null `buyerCount`.
- **Effort:** M. **Verification:** CONFIRMED for the diagnosis (wash = volume concentrated among self-owned wallets, per Chainalysis/NFTDisk). Caveat: HHI/top-1 as the *specific* metric is the research's synthesis on top of a supported principle — the citations back the diagnosis, not the exact gating threshold. Tune thresholds against real data.
- Cite: https://www.chainalysis.com/blog/2022-crypto-crime-report-preview-nft-wash-trading-money-laundering/ · https://arxiv.org/pdf/2302.05863

### V2-D — Persistence + rolling uptime/latency + re-verification (kills single-shot)
- **What:** new store layer (SQLite is enough) keyed by `agentId+endpoint`, storing probe samples `(ts, category, status, latency_ms)`. New engine signals `uptime_history` (rolling availability caps SAFE below ~95%) and `latency` (P95 penalty). A scheduled re-probe re-runs `score_agent` and **diffs the prior verdict** — a state change (`down→healthy` or `healthy→down`) is a first-class output, so a patched agent gets a fresh verdict instead of a stale BLOCK.
- **Module:** new `oracle/store.py` + `oracle/data.py` (sampling) + `oracle/engine.py` (two signals) + a cron.
- **Attack:** flapping endpoints passing on a lucky single probe; stale verdicts after an agent patches or breaks; latency-degraded "technically up" services.
- **Effort:** L. **Verification:** standard SLA-monitoring practice (uptime %/P95); no controversial claim.
- Cite: https://www.dotcom-monitor.com/features/uptime-and-sla-reports/

### V2-E — Time-decay / forgetting factor on stale signals
- **What:** once persistence (V2-D) exists, weight each feedback item and cached liveness/x402/security result by `λ^age` (λ ≈ 0.96/day, tunable) inside the Wilson/Beta aggregation. Add a `reputation_freshness` sub-signal.
- **Module:** `oracle/engine.py` aggregation + `oracle/store.py` timestamps.
- **Attack:** stale reputation carrying a now-degraded agent; slow whitewashing where old good history papers over recent failures.
- **Effort:** M (depends on V2-D). **Verification:** CONFIRMED as a standard trust-model principle.
- Cite: https://arxiv.org/pdf/1405.3199

### V2-F — Refund / dispute / arbitration signal (distinct from low stars)
- **What:** extend `fetch_feedback` (or add `fetch_disputes` via onchainos task/decision APIs) to surface refund/revoked/rejected/arbitration-lost counts. New `dispute_history` signal: any confirmed refund or lost arbitration hard-caps at CAUTION-or-lower and appears as a critical headline reason, independent of `securityRate`. Maps to ERC-8004's `FeedbackRevoked`/`ResponseAppended`.
- **Module:** `oracle/data.py` + `oracle/engine.py`.
- **Attack:** clean-looking star average hiding a trail of refunds/chargebacks; reputation laundering by diluting bad outcomes with trivial positives.
- **Effort:** M. **Verification:** ERC-8004 reputation model confirmed against the EIP.
- Cite: https://eips.ethereum.org/EIPS/eip-8004

### V2-G — Beta-reputation core with skeptical prior + dispute-weighted negatives
- **What:** represent reputation as `Beta(α, β)`, `α = positives + prior`, `β = negatives + prior`; expected score `α/(α+β)` shrinks to the prior when evidence is thin, and the interval width drives the `_confidence` gate directly. Feed negative evidence asymmetrically — a resolved-against-provider dispute/refund increments β with weight `w ≫ 1`. This is the statistical home for the confidence layer that Wilson (S4) approximates; V2-G supersedes S4 as the reputation core once disputes (V2-F) are available.
- **Module:** `oracle/engine.py` reputation core + `_confidence`.
- **Attack:** over-trusting thin evidence; positive-review farming that ignores disputes.
- **Effort:** M. **Verification:** CONFIRMED (Jøsang & Ismail, *The Beta Reputation System*, 2002). Caveat: the asymmetric dispute weighting and sub-0.5 prior are **extensions** of the paper, not results in it — the paper uses a symmetric uniform prior. Label them as our design built on BRS.
- Cite: https://people.cs.vt.edu/~irchen/5984/pdf/Josang-BECC02.pdf

### V2-H — EigenTrust over the reviewer graph (the real Sybil answer)
- **What:** build a trust graph over reviewer wallets; each reviewer's weight = their own transitively-earned global trust (principal eigenvector of the normalized local-trust matrix), anchored to a pre-trusted set (OKX-listing-reviewed agents / known-good operator wallets). Each feedback item is weighted by the reviewer's global trust before entering the Wilson/Beta term. Cheap 1-hop approximation now (weight by reviewer's own settled-volume/age); full normalized eigenvector later.
- **Module:** `oracle/engine.py` review-ring module → graph engine.
- **Attack:** orchestrated collusion / review rings / Sybil swarms of fresh wallets — a clique that only trusts itself gets ≈0 global weight regardless of count (paper shows resilience up to ~70% malicious collectives). This is the structural fix the current pairwise-overlap detection misses.
- **Effort:** L. **Verification:** CONFIRMED (Kamvar et al., Stanford).
- Cite: https://nlp.stanford.edu/pubs/eigentrust.pdf · https://en.wikipedia.org/wiki/EigenTrust

### V2-I — Wallet age + funding-provenance signal
- **What:** from OKLink, pull the agent's receiving/owner wallet first-tx timestamp (age) and first-funder. New `wallet_provenance` signal: age < threshold, or funder == owner / known-bad / a reviewer address → cap at CAUTION. Cross-reference the funder against the leaked/blocked wallet list already tracked (e.g. the `0x3d7d` leaked wallet).
- **Module:** `oracle/data.py` + `oracle/engine.py`.
- **Attack:** fresh disposable agents spun up to escape a prior bad reputation (whitewashing); agents funded by a mixer or by the wallet that also pays their own reviews.
- **Effort:** M. **Verification:** CONFIRMED (first-tx timestamp is immutable/on-chain; standard forensic heuristic).
- Cite: https://cryptotracelabs.com/blog/on-chain-wallet-age-analysis-using-first-transaction-timing-for-attribution/

### V2-J — Explicit cost-to-forge as a signed verdict output
- **What:** a scoring wrapper where each gate declares its marginal forge-cost contribution (distinct-wallet gas/funding + bonded stake at risk + settled-volume floor); sum to `forgeCostUsd`, expose it in the signed verdict JSON, add hard rule "SAFE requires `forgeCostUsd >= threshold`". Reframes the vague "~$0.10 + effort" into a measured, judge-legible adversary-economics number.
- **Module:** `oracle/engine.py` confidence/verdict layer + `oracle/seal.py` payload.
- **Attack:** the core weakness — a SAFE verdict buyable for cents. Makes each gate's economic contribution auditable.
- **Effort:** M. **Verification:** premise CONFIRMED (Sybil resistance is a cost spectrum) but citations are **low-authority glossary pages**, and the "relative to reward" framing is standard security reasoning, not stated on the cited pages. Ship the mechanism; don't over-cite it.
- Cite: https://chainscorelabs.com/en/glossary/smart-contracts/dao-governance-contracts/sybil-resistance

### V2-K — Grounded-feedback requirement (require settlement/validation behind a review)
- **What:** upgrade the review module from "detect ring → discount" to "require grounding": feedback counts toward reputation only if the reviewer wallet has an on-chain settlement to the agent (from V2-B) or a Validation Registry entry. Ungrounded feedback caps at CAUTION-weight. This is the eBay ballot-stuffing defense and also compensates for null `buyerCount`.
- **Module:** `oracle/data.py` feedback ingestion + `oracle/engine.py` review term.
- **Attack:** coordinated reviewer rings and ungrounded feedback inflating an agent to SAFE with no paid interaction behind it.
- **Effort:** M. **Verification:** CONFIRMED — the empirical ERC-8004 study (arXiv 2606.26028) found 73–90% of reviewers showed coordinated Sybil behavior and feedback "rarely grounded in verifiable interactions"; eBay ballot-stuffing literature confirms transaction-fee coupling as the economic gate.
- Cite: https://arxiv.org/abs/2606.26028 · https://www.researchgate.net/publication/228344433_Avoiding_ballot_stuffing_in_eBay-like_reputation_systems

### V2-L — Payer-graph funding-cluster collapse
- **What:** for each distinct payer (V2-B), fetch its first-funder; collapse payers sharing a funder into one cluster (star-divergence airdrop-Sybil pattern). Feed engine `distinct_funding_clusters`; the sub-cent SAFE path additionally requires `clusters >= K`. Reuses V2-B/V2-I OKLink calls.
- **Module:** `oracle/data.py` settlement reader + `oracle/engine.py`.
- **Attack:** wash farms that spread volume across many fresh addresses to beat distinct-count/concentration checks — every fake buyer traces to one funder.
- **Effort:** L. **Verification:** standard airdrop-Sybil clustering (Forta/Trusta).
- Cite: https://arxiv.org/html/2505.09313v1

---

## 4. Ranking methodology (proposal)

**Current state:** additive signals with a lowest-cap override, hand-tuned deltas, `SAFE>=70 / CAUTION 45..69 / BLOCK<45`, gated by an availability-based `_confidence`. The philosophy ("SAFE must be EARNED") is right; the *implementation* is intuition-tuned and therefore unfalsifiable.

**Proposed layered model** (each layer is independently shippable; earlier layers are strict subsets of later ones):

**Layer 0 — Wilson lower bound (ship now, S4).** Reputation term = `WilsonLB(pos, n, z=1.96)`:
```
p = pos / n
WilsonLB = (p + z²/2n − z·√((p(1−p) + z²/4n)/n)) / (1 + z²/n)
```
Why it beats hand-tuned deltas: the uncertainty term `z·√(…)/…` mechanically dominates at small `n`, so a 2-review agent is pulled toward 0 and *cannot* be tuned into SAFE by picking a friendly delta. "SAFE must be EARNED" becomes a property of the estimator, not a constant an engineer chose.

**Layer 1 — Beta reputation core (V2-G).** Replace the point estimate with `Beta(α,β)`, expected score `α/(α+β)`, skeptical prior, dispute-weighted β. The **interval width** *is* the confidence signal — it replaces the ad-hoc availability-count `_confidence()` with a statistically meaningful one, and gives disputes/refunds real teeth instead of averaging them away.

**Layer 2 — EigenTrust reviewer weighting (V2-H).** Before feedback enters the Beta counts, multiply each item by the reviewer's transitively-earned global trust, anchored to a pre-trusted set. This is what actually closes the review-ring / null-buyerCount gap: colluding fresh wallets contribute ≈0 no matter how many reviews they post. Heuristic pairwise-overlap detection cannot make that guarantee; the eigenvector does, provably, up to ~70% malicious.

**Grounding gate (V2-K), across all layers:** only settlement-grounded or validation-grounded feedback is counted at full weight — so the whole reputation stack sits on paid, on-chain-verifiable interactions rather than free-text reviews.

**Meta-layer — calibration (see §5).** Bands (`70/45`) should be *learned* from realized outcomes (isotonic/Platt), not asserted. Until KYA logs verdict→outcome pairs, the thresholds are guesses; the model above is only honest once the calibration harness exists.

Net: the engine moves from "additive deltas + lowest cap, thresholds picked by hand" to "grounded, Sybil-weighted Bayesian reputation with a decision boundary calibrated against reality" — every piece falsifiable and citable.

---

## 5. Open research questions

1. **Calibration / ground truth (the meta-gap).** The oracle emits SAFE/CAUTION/BLOCK with implicit confidence, but nothing measures whether SAFE agents empirically don't defraud. Needs: persistent `(agent, verdict, confidence, outcome)` logging, then Brier score + reliability diagram + isotonic recalibration of the bands. **Blocker:** where do ground-truth outcome labels come from on X Layer? (disputes lost, endpoints gone malicious, funds diverted). Without a label source the harness is unbuildable. Priority *later*, but everything in §4 is provisional until it exists. Cite: https://arxiv.org/pdf/2008.03033
2. **OKLink X Layer endpoint specifics.** V2-B/-I/-L all assume an address transaction-list + token-transfer endpoint. The docs landing page confirms the *capability* but did not surface the exact endpoint URL/auth/rate-limits — needs an integration spike before committing effort. Also confirm the USDC (EIP-3009) vs USDT (Permit2) settlement-scheme split on X Layer specifically.
3. **ERC-8004 registry reachability from X Layer.** Cross-marketplace reputation and the Validation Registry (stake/evidence-backed, self-review-proof) are strictly stronger than OKX's siloed feedback — but only if the registries are deployed and readable on X Layer. Verify deployment before building readers. ERC-8004 is a moving draft; pin to the live spec. Cite: https://eips.ethereum.org/EIPS/eip-8004
4. **TEE remote attestation for anti-bait-and-switch.** The only mechanism that cryptographically proves the live endpoint still runs the reviewed code (pin TDX MRTD/RTMR or Nitro PCR at review, compare on re-scan; drift → BLOCK). Maps onto ERC-8004's `tee-attestation` trust model and fixes single-shot. Research-grade: few marketplace agents ship in a TEE, quote verification (vendor cert chains) is non-trivial. Cite: https://arxiv.org/pdf/2303.15540
5. **Slashable-bond SAFE tier.** The only mechanism that puts a hard *price* on a false SAFE (TCR/identity-staking). Requires an on-chain bond contract + challenge flow — design now, build post-hackathon. Open question: who posts the bond (agent vs ASP) and who arbitrates a challenge? Cite: https://university.mitosis.org/token-curated-registries-tcr/
6. **Egress-proxy + sandboxed prober (deploy-side SSRF depth).** App-layer guards (S1–S3, V2-A) are necessary-but-insufficient; the durable fix is a Smokescreen-style egress-allowlist proxy with metadata/RFC1918 blocked at the VPC route table, and moving probing into an ephemeral secret-free worker (gVisor/Firecracker) with no route to `keys/`/`signing.py`. Deferred to *later* because it's deploy/infra work, but it's the structural guarantee that a prober bug can never reach the signer. Cite: https://github.com/stripe/smokescreen
7. **DID/VC authority layer (schema placeholder).** ERC-8004 + x402 answer "is this a real, live, paid agent?" but not "is it authorized on someone's behalf?" (x401 / AP2 mandates). Reserve an `authority_vc` slot in the verdict schema; no-op until VCs appear in OKX data. Cite: https://www.proof.com/blog/introducing-x401
