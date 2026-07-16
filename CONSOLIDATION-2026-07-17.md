# KYA Repo Consolidation — 2026-07-17

Consolidating the KYA / OKX Genesis project that had split across two git repos with
**unrelated histories** (parallel sessions) into ONE canonical repo with every feature and
a green test suite.

- **Branch:** `consolidate/kya-2026-07-17` (cut from `extra-mile/kya-2026-07-16`)
- **No force-push, no overwrite of public `main`.** Left for Oscar to review and publish.
- **No code was changed.** The on-chain payment path (x402 / facilitator / EIP-3009) is
  byte-for-byte untouched. `.env` stays gitignored; no secrets committed.

---

## 1. Canonical base — and the surprise

**Canonical: `okx-agent-oracle` (local `extra-mile/kya-2026-07-16`).** Chosen because it is
what is deployed to prod (Railway) and it holds the eligibility-critical x402 rejection fix.

The surprise that made this easy: **the local branch is already a strict superset of the
public repo.** The two "unrelated histories" independently built the *same* features
(operators board, A5 supply-side sybil, priced-trust v2, threat model) and — for every file
they share — converged to **byte-identical code**. Verified with `git diff HEAD origin/main`:

| Shared file | local vs public |
|---|---|
| `oracle/watchtower.py` (`/operators` board) | **identical** |
| `oracle/verify.py` | **identical** |
| `docs/THREAT-MODEL.md` (incl. A5) | **identical** |
| `oracle/engine.py` (A5 + priced-trust) | identical **except** local adds the `cluster` field |
| `app.py` | local adds the x402 gate + `/audit` route |

Everything the public repo has, the local branch already has. The public repo has **nothing**
the local branch lacks (the only public-only lines are 8 README prose lines saying "113
tests"; local's README is newer and says "140 tests"). So there was nothing to *port* — the
job reduced to: verify the superset, reconcile the sybil/cluster overlap, prove tests green,
and cut the clean branch.

Features confirmed present on the canonical branch:

- x402 rejection fix (`/verify` accepts GET+POST, speaks x402, the #5290 unblock) — `oracle/x402.py`, `app.py`
- `/audit` PAID tier (real USDT settle on X Layer via OKX facilitator, EIP-3009) — `oracle/audit_paid.py`
- machine-readable `cluster` field on `/verify` — `oracle/engine.py`
- `/operators` board — `oracle/watchtower.py` + `oracle/store.py:operators()`
- A5 supply-side sybil ("score the wallet, not the listing") — `oracle/engine.py`
- priced-trust v2 (`max_safe_usd`, measured settled volume) — `oracle/engine.py`
- threat model — `docs/THREAT-MODEL.md`
- `SUBMISSION.md`, `google-form-answers.md`, avatars (`oracle/assets/*.png`), MIT `LICENSE` — all present

## 2. Sybil / cluster reconciliation (the tricky part)

The brief flagged the public repo's **A5 supply-side sybil + `/operators` board** and the
local repo's new **`cluster` field** as "the same concept implemented twice in parallel" and
asked for one coherent implementation with no dead or duplicated code.

**Finding: they are already unified into ONE owner→agents path — not two competing
implementations.** There is a single data source and three *consumers* of it:

```
scripts/index_owners.py  +  verify.py   →  ONE SQLite table  agent_owners(owner, agent_id, name, sold)
    (agent get-agents is the only OKX API that returns ownerAddress; verify.py records each agent it sees)
                                   │
                 ┌─────────────────┼───────────────────────────────┐
   store.fleet_for(owner)                              store.operators(limit)
   (per-agent read)                                    (marketplace-wide aggregate read)
                 │                                                    │
   engine.score_agent(fleet=…)                          watchtower.render_operators()
     ├─ A5 signals  → human-readable, MOVES the score        the /operators board surface
     └─ cluster{}   → machine-readable, NEVER moves score
```

Why this is coherent and not duplicated:

- **One index, one schema.** Both the per-agent signal and the board read the same
  `agent_owners` table. `fleet_for()` is the per-owner slice; `operators()` is the
  `GROUP BY owner` aggregate. No second owner-grouping implementation exists.
- **The `cluster` field is a projection of A5, not a re-derivation.** In `engine.py` the
  `cluster_summary` object reuses the *exact variables A5 already computed* in the same block
  — `known`, `fleet_sales`, `per_agent`, `templated`, and crucially `fleet_penalized`
  (`cluster.risk == "high"` iff the A5 penalty fired). It is built only when `known >= 2`,
  is pure disclosure, sits outside the signed core, and **never moves the score** (the A5
  `Signal`s already did). So: A5 = the human sentence + the score movement; `cluster` = the
  same finding as a struct a calling agent can branch on (`if cluster.penalized: demand more
  volume`). One owner, one code path, two renderings for two audiences.
- **`/operators` is a different surface, not a duplicate.** A5/cluster answer "is *this*
  agent one of a farm?" (per-verify). `/operators` answers "what does the *whole*
  marketplace look like grouped by wallet?" (aggregate). Same table, different query, no
  overlap in logic.

**Action taken: none beyond verification.** The parallel work had already collapsed into this
single path on the local branch; there is no dead code, no duplicated owner-grouping, and one
clear owner→agents scoring path. Keeping it as-is *is* the reconciliation. Ripping the
`cluster` field back out (to match public) would be a regression — it is the machine-readable
half of the exact finding the board renders for humans.

## 3. Payment path — preserved exactly

No file under `oracle/` or `app.py` was modified. The x402 gate (`oracle/x402.py`), the paid
`/audit` middleware and facilitator settle (`oracle/audit_paid.py`, EIP-3009
`transferWithAuthorization`) are unchanged. The paid tier self-disables cleanly with no creds
in env — verified at import:

```
[kya] paid tier: no OKX creds in env — /audit not mounted (free tier unaffected)
```

## 4. Test results (real numbers)

Run with the repo venv (`.venv/bin/python -m pytest -q`):

| Suite | Result |
|---|---|
| **Public repo** (`github.com/Morkeeth/kya-know-your-agent` main, fresh clone) | **135 passed** |
| **Consolidation branch** `consolidate/kya-2026-07-17` (before = after; no code changed) | **140 passed** |

The delta is exactly **+5 tests**, all local-only and all passing:

- `test_cluster_field_flags_a_farm`
- `test_cluster_field_discloses_real_business_without_penalty`
- `test_cluster_field_absent_without_fleet`
- `test_cluster_field_absent_for_solo_operator`
- `test_verify_speaks_x402_unpaid_402_paid_200`  (the #5290 saga: unpaid→402, paid→200, both verbs)

Public has **zero** tests the consolidation branch lacks. One benign warning
(`StarletteDeprecationWarning` from the FastAPI TestClient) — not a failure.

## 5. Needs Oscar's decision / genuinely ambiguous

1. **Publishing.** The consolidation branch is a strict superset of public `main`, so
   publishing it as the new public `main` is safe (fast-forward-in-spirit; content only adds).
   Because histories are unrelated, this is a **content replace**, not a git merge — do it as
   a squash/replace commit onto public main, or reset public main to this tree. **Not done
   here by design** (no force-push, left for you).
2. **`google-form-answers.md:57`** already claims the *public* repo has "140 tests". Public
   currently has **135**. Publishing this branch makes that claim true — until you publish,
   the form answer is 5 ahead of the live public repo. No action needed if you publish before
   the form is reviewed; flagging so it isn't a surprise.
3. **Untested-by-CI payment settle.** The x402 *contract* (402 challenge / paid-200) is unit-
   tested. The *actual facilitator settle* in `audit_paid.full_audit` (real USDT / EIP-3009)
   is only exercisable live with OKX creds and is **not** covered by an offline test — expected
   for an on-chain path, but stated honestly: I did not run a live settlement, so I am not
   claiming the settle executes, only that its code is present and unchanged from prod.
