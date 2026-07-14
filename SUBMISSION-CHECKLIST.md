# KYA — OKX $100K submission checklist

Deadline **Jul 17**. Live: https://kya-production-f846.up.railway.app · ASP #5290 (listing under review).
Repo state as of 2026-07-14 (branch `main`).

## ✅ Done (machine-verifiable, real)
- [x] **Service live on Railway**, `/health` green, signing key from env (stable signatures).
- [x] **`scripts/demo.sh` runs end-to-end GREEN against the live URL** from real responses
      (`bash scripts/demo.sh` → exit 0). Two fenced sections: [LIVE] deployed spread +
      signed verdicts + in-loop caller refusing on BLOCK; [CONTROLLED] real flip/poison
      detectors on a labelled TEST fixture. Self-verifies (exits non-zero if live diverges).
- [x] **Live clean spread reproduces** on the deployed service: Otto/Explorer SAFE,
      Scope/WhalePulse CAUTION, Sentiment Oracle **BLOCK** (score 44, signed, real 502 endpoints).
- [x] **82 real OKX agents swept & seeded** into the live watchtower — spread 8 SAFE / 60
      CAUTION / 14 BLOCK. Genuinely discriminating, not a rubber stamp.
- [x] **Correctness fix**: false impersonation BLOCK on cross-registry ERC-8004 ids removed
      (Barker #2012 was falsely BLOCKed vs its Base id #52838 → now correctly SAFE).
      +3 regression tests. Committed `49d68b2`. **← needs deploy (see below).**
- [x] **Tests: 103 green.** Every threat-model row has coverage.
- [x] **Wash gate**: built + tested, correctly OFF (no OKLink key). Enable steps in `docs/WASH-GATE.md`.

## ⚠️ Decisions / deploy (need a human)
- [ ] **Deploy the Barker fix to live** (`railway up`) — HOLD until DB persistence is confirmed:
      no `KYA_DB_PATH`/volume var was visible, so a redeploy may **wipe the seeded 82-agent
      watchtower**. Confirm a Railway volume + `KYA_DB_PATH` on it first, then deploy, then
      re-run the 82-agent sweep to reseed. (Fix is committed and safe; only the timing is gated.)
- [ ] **Thin spot (optional)**: phishing/blacklist-host scan has the lightest test coverage
      (1 helper). Add a dead-host/blacklist regression if time allows — not a blocker.

## 👤 Oscar-only (cannot be automated)
- [ ] **Record the ~3-min demo** — narrate `bash scripts/demo.sh` live. Beat sheet: problem →
      live spread (BLOCK on Sentiment Oracle) → in-loop caller REFUSES → flip + poison detectors
      (say "controlled test agent, real detector") → watchtower board. Every on-screen number
      comes from the live call. Tonight per your plan.
- [ ] **X post (#OKXAI)** — short, video-first, killer hook, no bragging. Morning slot
      (Tue–Thu 8–10am Paris) → Jul 15/16 AM, not evening.
- [ ] **Google form** — fill from `SUBMISSION.md`; headline = signed live BLOCK primitive.
- [ ] **Watch ASP #5290 listing approval** — outside our control. If it slips past Jul 17,
      submit anyway with "listing review in progress" (already stated honestly in README).
      Do NOT re-activate or change the listing.

## Headline for the writeup
"A star rating is a claim; KYA checks the receipts." Signed, callable, always-fresh
SAFE/CAUTION/BLOCK on any agent — refuse to transact on BLOCK. Proven live on 82 real
OKX agents, gated so SAFE must be earned.
