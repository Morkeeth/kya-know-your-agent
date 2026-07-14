# KYA - your submit guide (the only doc you need)

Deadline: **Jul 17 2026, 23:59 UTC.** Everything is built and verified. This is your ~15-min task.
You are NOT blocked on OKX approving anything (see step 5).

## Do this, in order

**1. Warm it** (30 sec)
```
cd ~/CODE/okx-agent-oracle && bash scripts/demo.sh
```
Expect `DEMO GREEN` and exit 0. It self-verifies against the live URL and retries blips, so if it
goes green you're safe to record. (If it ever prints RED, just run it again - a cold instance warms.)

**2. Record ~90 sec** - narrate from `demo-shotlist.md` (timed beats, exact lines). Two browser tabs open:
`/watchtower` and `/passport?agentId=3820`. Every number on screen is a real live response.

**3. Post the tweet** - it's locked in `draft-x-post.md` (the "THE TWEET (locked)" block). Attach the
video. Post in a morning slot (Tue-Thu 8-10am Paris). Glance at `/watchtower` first and fix the three
numbers if they shifted.

**4. Fill the Google form** - every field is pre-filled in `google-form-answers.md` (real values, public
repo link included). Only three fields need you: your name/contact, the video link, the X post link.

**5. Submit.** ASP #5290 approval is NOT required. If it's still "under review" at the deadline, submit
anyway - the live endpoint and Agent ID work regardless. Do NOT re-activate or change the listing.

## What's already done (you don't touch any of this)
- Live service, signed verdicts, **all 374 OKX agents judged** (16 SAFE / 335 CAUTION / 23 BLOCK) on a persistent board.
- 110 tests green. Barker false-positive fixed. Signing key rotated. Blip-proof demo.
- **Public repo:** https://github.com/Morkeeth/kya-know-your-agent (MIT licensed).
- **#5290 tracker** running: pings your Google Calendar if OKX approves the listing before the deadline.
- Credibility docs in the repo: `docs/THREAT-MODEL.md` (agentic-security coverage, cited).

## After you submit (my queue, nothing for you)
- Deploy the two new detectors sitting on branch `feat/tier1-coverage` (domain-age + reviewer-concentration).
- Build plan for v2 (KYA Guard self-audit, bounded-trust "$X", the handbook) is in your vault:
  `01 Projects/Hackathons/kya-moonshot-roadmap-2026-07-14.md`.
- If you grab an OKLink API key (oklink.com dev portal, ~5 min), I finish and enable the on-chain wash gate.

That's it. Warm, record, post, form, submit.
