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
- [ ] **Rotate `ORACLE_SIGNING_KEY`** (and the OKX API creds). The signing key is KYA's trust
      root and was exposed in plaintext during this session; anyone with it can forge SAFE
      verdicts. Cheap to rotate (`os.urandom(32).hex()`), no external consumer pins it pre-listing.
- [ ] **Set a light recurring re-sweep** (freshness): `seed_all.py` on a cron keeps verdicts
      current and populates `/changes` with real transitions over time. Optional, strengthens
      the "always-fresh timeline" story.

## 👤 Oscar-only (cannot be automated)
- [ ] **Record the ~3-min demo**: narrate `bash scripts/demo.sh` live. Beat sheet: problem,
      live spread (BLOCK on Sentiment Oracle), in-loop caller REFUSES, flip + poison detectors
      (say "controlled test agent, real detector"), the 371-agent watchtower board. Every
      on-screen number comes from the live call. Tonight per your plan.
- [ ] **X post (#OKXAI)**: short, video-first, killer hook, no bragging. Morning slot
      (Tue-Thu 8-10am Paris), Jul 15/16 AM, not evening.
- [ ] **Google form**: fill from `SUBMISSION.md`; headline = signed live BLOCK primitive + 371
      agents judged. Does NOT need the #5290 listing approved (decouple, see below).
- [ ] **ASP #5290 listing approval**: outside our control, trackable on request. If it slips
      past Jul 17, submit anyway with "listing review in progress" (stated honestly in README).
      Do NOT re-activate or change the listing.

## Headline for the writeup
"A star rating is a claim; KYA checks the receipts." Signed, callable, always-fresh
SAFE/CAUTION/BLOCK on any agent - refuse to transact on BLOCK. Proven live on 82 real
OKX agents, gated so SAFE must be earned.
