# KYA - OKX $100K submission checklist

Deadline **Jul 17**. Live: https://kya-production-f846.up.railway.app · ASP #5290 (listing under review).
Repo state as of 2026-07-14 (branch `main`).

## ✅ Done (machine-verifiable, real, DEPLOYED)
- [x] **Service live on Railway**, `/health` green, signing key from env (stable signatures).
- [x] **`scripts/demo.sh` runs end-to-end GREEN against the live URL** from real responses
      (`bash scripts/demo.sh` -> exit 0). Two fenced sections: [LIVE] deployed spread +
      signed verdicts + in-loop caller refusing on BLOCK; [CONTROLLED] real flip/poison
      detectors on a labelled TEST fixture. Self-verifies (exits non-zero if live diverges).
- [x] **Live clean spread reproduces** on the deployed service: Otto/Explorer SAFE,
      Scope/WhalePulse CAUTION, Sentiment Oracle **BLOCK** (score 44, signed, real 502 endpoints).
- [x] **Correctness fix DEPLOYED**: false impersonation BLOCK on cross-registry ERC-8004 ids
      removed (Barker #2012 was falsely BLOCKed vs its Base id #52838, now correctly SAFE 100
      on production). +3 regression tests. Commit `49d68b2`, live.
- [x] **Persistence**: Railway volume `/data` + `KYA_DB_PATH` set, so the watchtower survives
      redeploys and restarts. Board cap raised 50 -> 400 (`app.py`).
- [x] **Whole marketplace judged live**: all **371 listed OKX agents** swept via
      `scripts/seed_all.py` into the persistent store, 0 errors. Spread **15 SAFE / 334 CAUTION
      / 22 BLOCK** (only 4% earn SAFE). Re-runnable; verdicts sit warm for other callers.
- [x] **Tests: 103 green.** Every threat-model row has coverage (incl. phishing/drainer BLOCK).
- [x] **Wash gate**: built + tested, correctly OFF (no OKLink key). Enable steps in `docs/WASH-GATE.md`.
- [x] **Submission kit refreshed**: README + V2-RESUBMIT carry the 371-agent proof and 103 tests.

## ⚠️ Decisions (need a human)
- [x] **`ORACLE_SIGNING_KEY` ROTATED** (done). Old leaked key (`fabe730d…`) neutralized; live
      pubkey now `2fbb9b67…`; 363 agents re-swept so stored verdicts re-sign under the new key.
      OKX API creds also rotated by Oscar. (Note: enumeration variance means a few stored
      verdicts may still hold old-key sigs; live `/verify` always re-signs fresh, no exposure.)
- [ ] **Set a light recurring re-sweep** (freshness): `seed_all.py` on a cron keeps verdicts
      current and populates `/changes` with real transitions over time. Optional, strengthens
      the "always-fresh timeline" story.

## 👤 Oscar-only (cannot be automated)
> **🚨 CORRECTED Jul 15 — read this before the rows below.** The official rules (Step 2) state:
> *"Your ASP must pass OKX AI's internal review and go live to remain eligible. If the ASP listing
> is not approved or cannot go live, your hackathon submission will be deemed invalid."*
> The prior "decouple / submit anyway" strategy in this file was **WRONG** and is dead.
> **Approval + a live listing is a HARD eligibility gate.** Verified live Jul 15 07:23 UTC:
> #5290 = `Listing under review`, status `not listed` (in review since Jul 13 10:47 UTC, ~45h,
> past the claimed ≤24h). Deadline is Jul 17 **23:59 UTC**. Demo cap is **90 seconds**, not 3 min.

- [ ] **Record the demo — HARD CAP 90 SECONDS** (rules: "Demo content should be no longer than 90
      seconds"). This file previously said ~3 min: **wrong, would breach the rules.** Narrate
      `bash scripts/demo.sh` live. Beat sheet must be re-cut to fit 90s: problem, live spread
      (BLOCK on Sentiment Oracle), in-loop caller REFUSES, the 371-agent watchtower board.
      Flip + poison detectors are the first cut if over time. Every on-screen number from the live call.
- [ ] **X post (#OKXAI)** — must introduce the ASP, explain the use case, and carry the demo.
      Short, video-first, killer hook, no bragging. Morning slot (Tue-Thu 8-10am Paris), not evening.
      **Post BEFORE the form** — the form requires a link to this post.
- [ ] **Google form** (Jul 17 **23:59 UTC**): fill from `SUBMISSION.md`; must include ASP details
      + the X post link. Headline = signed live BLOCK primitive + 371 agents judged.
- [ ] 🚨 **ASP #5290 listing approval = THE ELIGIBILITY GATE, not a nice-to-have.** Outside our
      control. Do NOT re-activate or change the listing (it is already submitted; `activate` on an
      under-review listing is a no-op). The only lever is **nudging OKX review**. AI pre-screen
      remark is already positive ("AI quality review suggested pass"). If it is still `not listed`
      at the deadline, submit anyway (costs nothing) but understand the entry is invalid as written.

## Headline for the writeup
"A star rating is a claim; KYA checks the receipts." Signed, callable, always-fresh
SAFE/CAUTION/BLOCK on any agent - refuse to transact on BLOCK. Proven live on 82 real
OKX agents, gated so SAFE must be earned.
