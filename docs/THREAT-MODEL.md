# KYA threat model and coverage

An honest map of the agentic-security landscape, what KYA verifies, and what no
pre-transaction oracle can. Grounded in the 2025-2026 literature (OWASP, MITRE ATLAS,
NIST, CSA) and documented attacks, not vibes.

## The distinction that governs everything

Every agent threat is either **pre-transaction verifiable** (checkable about a counterparty
*before* you pay it) or **runtime** (only manifests during execution). Across OWASP LLM Top 10
(2025), OWASP Agentic T1-T15 / ASI01-10 (2026), MITRE ATLAS, and CSA MAESTRO, the pre-tx-
verifiable surface reduces to five things: **identity/impersonation resistance, provenance/
supply-chain, declared authority surface, traceability/non-repudiation, and secure-protocol
posture.** Everything else - prompt-injection execution, memory/context poisoning, goal hijack,
cascading hallucination, RCE, resource overload - is runtime and cannot be externally pre-vetted.

**So "does KYA cover everything?" has one honest answer: no oracle can, and one claiming to is
lying.** KYA's job is to (1) own the pre-transaction gate completely, (2) re-derive signals
adversarially instead of trusting published scores, and (3) turn *runtime* failures into
*future* pre-tx signals via re-verify-on-change. It is a gate plus a live, decaying trust
signal - not a guarantee of future behavior, which is provably impossible (see Limits below).

## What KYA verifies today (and the real attack each maps to)

| KYA check | Threat class | Real attack it addresses | Strength |
|---|---|---|---|
| Tool-poisoning content scanner (injected instructions, secret-exfil, **zero-width/bidi/unicode**) | OWASP LLM01, ASI02, T2 | MCP tool poisoning (Invariant Labs, Apr 2025); "line jumping" (Trail of Bits); Unicode-tag injection | **High.** The zero-width/bidi scan is near-deterministic - hidden chars in a description have no legit reason. Injection detection is medium (documented 42-87% bypasses); a hit is strong-negative, a pass is weak-positive |
| Settled on-chain volume + distinct-payer wash gate + Wilson sample-size scoring | ASI-reputation, T13 | Sybil/wash-traded reputation; sock-puppet cross-attestation | **High signal, partially live.** Settled volume + Wilson are on; the on-chain distinct-payer wash gate is built but OFF pending an OKLink key + facilitator check (see WASH-GATE.md). Never passes a registry score through - re-derives it |
| Reviewer-wallet integrity (self-review / ring) | ASI-reputation | Reviewer collusion rings, self-dealing | **Medium.** Catches self-review and single-address rings; full FRAUDAR-style bipartite graph analysis is a gap |
| `.well-known` domain-binding + x402 `payTo` cross-check | T9 identity spoofing, ASI03 | Agent-card poisoning / shadowing (Trustwave, Keysight); endpoint borrowing | **Medium, deliberately conservative.** Same-registry impostors are caught; cross-registry ERC-8004 ids are treated as not-comparable (neutral) to avoid false accusations - a correctness fix, not full coverage |
| Behaviour-aware liveness probe (POST+GET; x402/api = serving, off-host redirect = hijacked) | dead/hijacked endpoint | Parked/hijacked endpoints; the ERC-8004 finding that only 3-15% of registrations are live | **Medium.** A necessary gate; malicious hosts are also "live", so this only rules out the dead, not the bad |
| OKX phishing/blacklist host scan | LLM03-adjacent, malicious endpoint | Drainer/phishing endpoints | **Strong on a hit, weak on a miss** - fresh fraud infra isn't listed yet |
| Persisted verdicts + **re-verify-on-change** (`/changes`, `/history`) | rug pull | MCPoison (CVE-2025-54136): approval bound to name not content, silent swap | **High *because* stateful.** The single biggest thing KYA adds over a one-shot scanner. Enhancement: full-surface hash-pinning + diff-before-tx |
| SSRF-guarded prober (refuses internal/loopback/metadata) | oracle self-defense | Drainer endpoint probing the oracle's own infra; DNS-rebinding | **Essential oracle-side control.** Correct as a control; weak as a claim about the remote host |
| Ed25519-signed, TTL-bounded verdicts; pinned-key offline verification | T8 non-repudiation | Rogue oracle self-signing SAFE | **Strong.** The trust root; verifiable offline against `/pubkey` |

## Honest gaps (prioritized, cheap-first)

Real, mostly cheap improvements the literature says matter and KYA does not do yet:

1. **Domain age (RDAP) + Certificate-Transparency first-seen** - one of the strongest cheap signals (~78% of phishing domains are <30 days old). Not in KYA. **Top fast-follow.**
2. **Full reviewer-graph collusion detection** (FRAUDAR-style bipartite, camouflage-resistant) - KYA does self-review/single-ring only.
3. **Time-decay on stored reputation** - defense against the good-then-bad "sleeper flip" (Reputation Lag Attack). KYA has TTL on verdicts but no decay on accumulated reputation weight.
4. **Web Bot Auth request signatures (RFC 9421)** - the strongest *live* proof of key+domain control per request. Not checked.
5. **Enable the wash gate for real** - needs an OKLink key + the buyer-vs-facilitator `from` verification (WASH-GATE.md). Off until verified against real settlement data (no fake signals).
6. **Full-surface hash-pinning** for rug-pull defense - extend re-verify-on-change to fingerprint the entire tool/description surface and diff before each transaction.

Structurally thin for *everyone* (documented, not just KYA): capability least-privilege (inside-runtime), supply-chain attestation (publish-and-trust; only TEE remote attestation closes it, near-zero adoption), dispute/refund history (rail-dependent, ~0 agent disputes exist yet).

## What no pre-transaction oracle can do (structural limits, stated plainly)

These are impossibilities, not KYA bugs. Any oracle sold as a future-behavior guarantee is selling something provably impossible.

1. **TOCTOU** - the verdict binds to a state that may differ at payment time. Mitigation: short TTL, re-validate immediately before action, pin DNS/IP across check-to-pay, streamed payments.
2. **Intent is undecidable** (Rice's theorem); models even behave *better* when they sense they're being tested (Anthropic agentic-misalignment). Mitigation: constrain action space, require stake, monitor at runtime.
3. **The endpoint you verify is not the model that runs** (45.8% of API endpoints failed fingerprint verification). Only per-response TEE attestation binds them, and it's barely deployed.
4. **One-shot / final-round defection** ("reputation milking") is dominant when the payoff exceeds accumulated-reputation NPV. Mitigation: stake sized to exceed the specific deal's defection payoff; stream payments.
5. **Runtime prompt injection via live tool outputs** (the "lethal trifecta") lands during the transaction on content no pre-check ever saw. Mitigation: least-privilege, HITL for high-risk, loss-bounding payment structure.

The right posture, aligned with the consensus (arXiv 2511.03434): **default zero-trust for high-impact actions; a pre-tx oracle blocks the deterministically-bad and prices the rest, but real protection for the residual lives in runtime** - escrow/staking sized to the deal, metered payments, spend caps, re-validation before settlement.

## External validation of KYA's headline

KYA's live sweep found only **~4% of 374 listed OKX agents earn SAFE**. Independent academic work
reached the same conclusion: "Can Trustless Agents Be Trusted?" (arXiv 2606.26028) audited deployed
ERC-8004 agents and found only **3% / 4% / 15%** (Ethereum/BSC/Base) have a valid live endpoint, and
**73-90% of reviewers are Sybil**. The rot KYA measures live on OKX is the rot the literature measures
across chains. Most listed agents do not survive real scrutiny - which is exactly why a callable,
signed, re-derived verdict is the missing primitive.

## Sources
OWASP LLM Top 10 2025 (genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025) · OWASP Agentic Threats & Mitigations (genai.owasp.org/resource/agentic-ai-threats-and-mitigations) · MITRE ATLAS (atlas.mitre.org) · MCP tool poisoning (invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks) · Line jumping (blog.trailofbits.com, 2025-04-21) · MCPoison CVE-2025-54136 (research.checkpoint.com) · Five Attacks on x402 (arXiv 2605.11781) · Can Trustless Agents Be Trusted? (arXiv 2606.26028) · Inter-agent trust taxonomy (arXiv 2511.03434) · TOCTOU in LLM agents (arXiv 2508.17155) · postmark-mcp supply-chain incident (semgrep.dev) · x402 free-riding (arXiv 2605.30998)
