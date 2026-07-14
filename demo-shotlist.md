# Demo shot-list - 90 seconds, keyed to demo.sh

Screen-record a terminal running `bash scripts/demo.sh` plus two browser tabs
(/watchtower and /passport?agentId=3820). Every number on screen is a real live response;
the script self-verifies and exits green, so if it runs clean you are safe to keep the take.
Do a dry run once before recording (the service can be cold on the first call).

Setup: terminal in ~/CODE/okx-agent-oracle, font large, two browser tabs pre-opened.

---

**0:00-0:12 - the problem** (talk over a clean terminal)
> "On OKX, agents now hire and pay each other. Everyone checks the token and the wallet.
>  Nobody checks the agent you're about to pay. There's no npm audit for agents. So I built one."
Then type: `bash scripts/demo.sh`

**0:12-0:38 - the live spread** (demo.sh [LIVE] THE SPREAD section)
On screen: Otto SAFE 100, Explorer SAFE, Scope + WhalePulse CAUTION, Sentiment Oracle BLOCK,
each with "✓ live verdict matches", a **MAX SAFE $X** line, and an ed25519 signature.
> "These are real OKX agents, judged live. Otto is proven, safe. Sentiment Oracle looks listed
>  and online, but KYA probed its endpoints and they're dead. Blocked. Every verdict is signed."
> "And look at this line - MAX SAFE. KYA doesn't just say safe or not, it tells you the max
>  dollar amount you should pay each agent, earned from its real settled volume. The dead one
>  gets zero. A proven agent gets a real number. A star rating gives everyone five stars;
>  KYA prices trust in dollars." (point at Otto $0.66 vs Sentiment Oracle $0)

**0:38-0:58 - KYA in the payment loop** (demo.sh [LIVE] KYA IN THE LOOP section)
On screen: the caller pays Otto, pays Explorer, then REFUSE on Sentiment Oracle, signatures VALID.
> "Here's a buyer agent using it. It fetches the verdict, checks the signature against KYA's key,
>  and refuses to send funds on BLOCK. That's the whole product: don't pay a bad counterparty."

**0:58-1:15 - trust is a timeline** (demo.sh [CONTROLLED] THE DETECTORS section)
On screen: BLOCK -> SAFE flip, then SAFE -> BLOCK tool-poisoning catch.
> "A verdict isn't a one-time stamp. When an agent patches a dead endpoint it re-clears; when it
>  silently poisons a tool description after approval, KYA catches the rug and flips it to BLOCK."
(Say plainly: "this beat is a controlled test agent driving the real detector.")

**1:15-1:30 - the board + close** (switch to browser)
Tab 1: /watchtower - the full board, 371 agents judged, the SAFE/CAUTION/BLOCK tally.
Tab 2: /passport?agentId=3820 - the red slashed-eye WOLF passport.
> "KYA has already judged the whole marketplace. 371 agents, only 15 earned safe. A star rating
>  is a claim. KYA checks the receipts. Know Your Agent."

---

## If a beat blips while recording
demo.sh retries transient empty responses automatically. If it still prints DEMO RED, just
re-run it (a cold instance warms after one call). Never narrate a number that isn't on screen.
