# Demo shot-list — 90 SECONDS HARD CAP (rules: "Demo content should be no longer than 90 seconds")

> Rewritten Jul 15. The old cut led with "agents hire each other", never mentioned the strongest
> thing we have, and said 371. **Lead with the finding.** A judge decides in five seconds, and
> "one wallet owns 99 agents" is a better five seconds than any setup of the problem.
>
> **Cut from the old version:** the flip / tool-poisoning detector beat. Good work, but it runs on
> a *controlled test agent*, and spending 17 of 90 seconds on a synthetic case while the real
> finding goes unshown is the wrong trade. It stays in the repo and the threat model.

Setup: terminal in `~/CODE/okx-agent-oracle`, big font. Browser tabs pre-loaded (**/operators**,
/watchtower). Dry-run once first, the service can be cold on the first call.
**Never narrate a number that is not on screen.**

---

**0:00-0:12 — THE HOOK** (open on `/operators`, already loaded)
On screen: rows #1 and #2. Both red slashed eyes, `ONE FACE`, 99 and 75, identical stems.
> "One wallet owns 99 agents on OKX's marketplace. The one under it owns another 75, running the
>  exact same naming template. That's one operator wearing 174 costumes."

**0:12-0:26 — WHY NOBODY HAS SEEN IT** (stay on /operators, point at the tallies)
On screen: `603 AGENTS INDEXED · 345 ACTUAL OPERATORS · 99 BEHIND ONE WALLET`.
> "Nobody's seen this because OKX's own search API never returns the owner address. The
>  marketplace can only show you listings. Group those same listings by wallet and a big chunk of
>  the place is two people."

**0:26-0:46 — WHAT KYA DOES ABOUT IT** (switch to terminal, run it live)
Type: `python cli.py 5335`
On screen, two reasons stacked:
`⚠️ One wallet (0x3256c679…) controls 99 known agents…` directly above `✅ Passed OKX listing review.`
> "Here's one of the 99. KYA calls it: not an independent provider. You're trusting one operator,
>  not 99 reputations. Now read the line underneath it."
**(Beat. Say nothing. Let them read "Passed OKX listing review." It's the best two seconds in the video.)**

**0:46-1:00 — IT DOESN'T JUST PUNISH SCALE** (terminal)
Type: `python cli.py 4413`
On screen: `ℹ️ Owner runs 32 known agents (69 settled sales across them) — concentration disclosed,
no penalty: the fleet has real customers.`
> "This operator runs 32 agents too. But they have real customers, so KYA discloses the
>  concentration and doesn't touch their score. Size isn't fraud. No customers anywhere, plus
>  machine-generated names, is."

**1:00-1:20 — PRICED TRUST + THE REFUSAL** (terminal)
Type: `python cli.py 2118`, then the caller beat from `bash scripts/demo.sh`
On screen: Otto SAFE 100, **max_safe_usd 0.66**, signed. Then the caller REFUSING on BLOCK.
> "Otto is the best agent here. Proven, live, signed. KYA says trust it with sixty-six cents.
>  That's not KYA being harsh, that's what it has actually earned. A star rating gives everyone
>  five stars. This gives you a dollar limit. And here's a buyer agent using it: checks the
>  signature, refuses to pay on BLOCK."

**1:20-1:30 — CLOSE**
> "Every verdict is signed and re-derived, never passed through from a registry. A star rating is
>  a claim. I wanted receipts. KYA. Know Your Agent."

---

## Re-verify these RIGHT BEFORE recording (they move)
- `/operators` → the 99 / 75 / 603 / 345 tallies
- `python cli.py 2118` → Otto's `max_safe_usd` (0.66 at last check)
- `/watchtower` → the CLEARED / WARY / WOLF spread

If a number on screen differs from this script, **say the number on screen**. The entire product is
"don't trust a claim you haven't checked". Narrating a stale figure over live output is the one
mistake that would actually undercut the pitch.
