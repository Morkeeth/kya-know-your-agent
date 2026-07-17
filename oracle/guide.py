"""
The KYA guide — one source, two renderings.

An agent cannot read a styled HTML page, and a human will not read a JSON blob. So the
guide is defined ONCE as structured blocks and rendered to both:

    GET /guide      -> HTML, in the board's identity, for a person
    GET /guide.md   -> markdown, for an agent (or an LLM) to fetch and follow

Everything factual here is generated from or checked against the engine, so the guide
cannot drift from the code the way a hand-written doc does (`test_guide.py` pins the
scoring numbers against oracle.engine).
"""
from __future__ import annotations

import html as _html

from oracle.engine import BLOCK_MAX, CAUTION_MIN, SAFE_MIN, CEIL_MULT_CAUTION, CEIL_MULT_SAFE

# --- content -----------------------------------------------------------------------
# ("h", text) heading · ("p", text) paragraph · ("code", text) · ("table", [head], [[row]])
# ("note", text) a called-out honest caveat. Inline `code` and **bold** are supported.

GUIDE: list[tuple] = [
    ("h", "The problem"),
    ("p", "On OKX.AI, agents hire and pay other agents unattended. Before your agent sends "
          "funds to a counterparty it has one question: **can I trust this one, and for how "
          "much?** Today it cannot ask. Every listing looks the same — a name, a rating, an "
          "online dot. All of that is a *claim* the seller makes about itself."),
    ("p", "The marketplace shows you agents. It never shows you **who owns them**. OKX's own "
          "`agent search` does not return `ownerAddress`, so a buyer browsing listings cannot "
          "tell ninety-nine independent providers from one wallet wearing ninety-nine names. "
          "We checked: one wallet runs **99 agents** with **19 settled sales between all of "
          "them**. Search surfaced 24 of the 99; enumeration found all 99 in ten seconds."),

    ("h", "What KYA is"),
    ("p", "A trust oracle for the agent economy. Your agent calls KYA before it pays or hires "
          "a counterparty and gets back a signed `SAFE` / `CAUTION` / `BLOCK` verdict **and a "
          "dollar ceiling** — the largest single payment that counterparty has *earned* the "
          "right to receive."),
    ("p", "A star rating is a claim. A ceiling is a decision. Everyone else on the marketplace "
          "vets the **asset** you are transacting in. KYA vets the **counterparty** you are "
          "transacting with."),

    ("h", "Use it"),
    ("p", "The listed service is free (fee 0) and returns the verdict directly. No key, no "
          "header, no account."),
    ("code", 'curl "https://kya-production-f846.up.railway.app/verify?agentId=2118"'),
    ("p", "From an agent, the only thing that matters is that you branch on **both** the "
          "verdict and the ceiling. The verdict alone is a rating; the pair is a decision:"),
    ("code", '''import httpx

KYA = "https://kya-production-f846.up.railway.app"

def may_i_pay(agent_id: str, amount_usd: float) -> bool:
    v = httpx.get(f"{KYA}/verify", params={"agentId": agent_id}, timeout=20).json()
    if v["verdict"] == "BLOCK":
        return False                      # refuse at any price
    if amount_usd > v["max_safe_usd"]:
        return False                      # over what it has earned — split or review
    return v["verdict"] == "SAFE"'''),
    ("p", "On OKX.AI itself, KYA is **Agent #5290**. It offers two services: `Agent Trust "
          "Verdict` (free) and `Agent Deep Audit` (0.1 USDT, settled through OKX's own x402 "
          "facilitator)."),

    ("h", "How the score works"),
    ("p", "Every *listed* ASP already passed OKX review, is online, and has a live endpoint. "
          "That is table stakes, not trust. So the engine is **gated, not additive**: it starts "
          "neutral, applies signal deltas, then clamps the result to the **lowest cap** any "
          "single signal imposed. One hard failure overrides a pile of good signals — you "
          "cannot buy back a dead endpoint or a poisoned tool description with a nice rating."),
    ("table", ["Band", "Score", "Means"], [
        ["`SAFE`", f"≥ {SAFE_MIN}", "Proven by settled volume, live, clean"],
        ["`CAUTION`", f"{CAUTION_MIN}–{SAFE_MIN - 1}", "Live but unproven, or soft flags"],
        ["`BLOCK`", f"< {CAUTION_MIN}", "Dead endpoint, failed review, anomalous, or not an ASP"],
    ]),
    ("p", "A few of the caps, so the gating is concrete rather than a claim: no ASP record "
          "caps at 25 · all endpoints dead caps at 20 · a malicious/blacklisted host is −60 · "
          "a `.well-known` domain-binding mismatch (endpoint-borrowing) is −45 · a self-review "
          "ring is −45 · partial endpoint outage caps at 62."),

    ("h", "The ceiling: max_safe_usd"),
    ("p", "The number KYA exists to return. It is **earned, never invented** — derived from "
          "*settled volume*, not review counts, so a review ring cannot inflate it:"),
    ("code", f'''max_safe_usd = settled_volume × multiplier × confidence

  multiplier   {CEIL_MULT_SAFE}   if SAFE
               {CEIL_MULT_CAUTION}   if CAUTION   (trivial amounts only, until proven)
               0     if BLOCK      (never pay)

  confidence   0..1 — how much evidence existed to judge on at all'''),
    ("p", "Worked from live agents: Otto AI has settled ≈$0.22 and is SAFE at confidence 100, "
          "so `0.22 × 3.0 × 1.0` = **$0.66**. Eat This? has settled ≈$5.50, so `5.50 × 3.0 × "
          "1.0` = **$16.50**. Same verdict, same confidence — a nine-times-larger ceiling, "
          "because it earned one."),
    ("note", "The ceiling is **sub-dollar for a sub-cent-proven agent by design**. It is not a "
             "guess at what an agent is worth; it is what it has *provably* settled. It grows "
             "as the agent earns. A number that started high would be a number we made up."),

    ("h", "Verify it yourself"),
    ("p", "Every verdict is Ed25519-signed and time-bounded. Fetch the key once from `/pubkey` "
          "and **pin it** — otherwise a rogue oracle ships its own key and self-signs `SAFE`. "
          "Then recompute the digest from the bytes you received: the signature covers the "
          "digest, so trusting the served `digest` field lets an attacker edit the body and "
          "replay the original signature."),
    ("code", '''from oracle.signing import verify_envelope, digest_for_body

digest = digest_for_body(body)                       # recompute — never trust body["digest"]
ok = verify_envelope(digest, body["signature"], PINNED_KEY) and digest == body["digest"]'''),
    ("p", "The signed core covers the verdict, score, confidence, ceiling **and a hash of the "
          "evidence** — so `evidence.cluster.fleet_size` cannot be rewritten from 99 to 1 "
          "while the signature still verifies."),

    ("h", "The research"),
    ("p", "The engine is built from the attack classes that actually happen in this market, "
          "not from a generic rubric. Each maps to a documented agent/MCP attack:"),
    ("table", ["Attack", "What KYA does"], [
        ["Rug pull — approved clean, turns later",
         "Persisted verdicts + re-verification on change; flips land on `/changes`"],
        ["Tool poisoning — hidden instructions in a tool description",
         "Content scanner: injected instructions, secret-exfil, zero-width/bidi unicode"],
        ["Wash-traded reputation",
         "Sample-size-aware Wilson bound + settled-volume basis, never a raw count"],
        ["Supply-side sybil — one wallet, N shells",
         "Owner-graph enumeration; the marketplace's own search cannot show this"],
        ["Impersonation / endpoint-borrowing",
         "`.well-known` domain-binding + x402 `payTo` cross-check"],
        ["Dead / hijacked / parked endpoint",
         "Behaviour-aware liveness probe (x402/api = serving, off-host redirect = hijacked)"],
        ["Reviewer rings / self-review", "Reviewer-wallet integrity audit"],
        ["KYA attacking itself (SSRF)",
         "The prober refuses internal / loopback / cloud-metadata targets"],
    ]),
    ("p", "Full threat model: `docs/THREAT-MODEL.md`. The wash gate and its honest limits: "
          "`docs/WASH-GATE.md`."),

    ("h", "Known limits"),
    ("p", "Stated because a trust product that hides its own gaps is not one:"),
    ("note", "**Volume basis is a floor.** Without a settlement-explorer key the engine assumes "
             "every sale happened at the agent's *cheapest* service price, so ceilings read low. "
             "The verdict says which basis it used (`evidence.volumeBasis`)."),
    ("note", "**Fleet detection keys on the wallet.** An operator who splits across wallets "
             "evades it — and the one in the wild already does. Template-clustering across "
             "wallets is the next slice."),
    ("note", "**Fleet size alone never convicts.** Two wallets run 32 and 7 agents with real "
             "customers; both are disclosed and *not* penalised. A penalty needs corroboration: "
             "no customers anywhere in the fleet, machine-generated naming, and zero settled "
             "volume on the agent itself. A shell that earns real sales heals out on re-verify."),
]


# --- rendering ---------------------------------------------------------------------
def _inline_md(t: str) -> str:
    """`code` and **bold** -> markdown passthrough (already markdown)."""
    return t


def _inline_html(t: str) -> str:
    """`code`, **bold**, *italic* -> HTML. Order matters: bold must be consumed before
    italic, or `**x**` splits on its own asterisks and renders as an empty emphasis."""
    esc = _html.escape(t)
    parts = esc.split("`")
    s = "".join(f"<code>{seg}</code>" if n % 2 else seg for n, seg in enumerate(parts))
    s = "".join(f"<b>{b}</b>" if n % 2 else b for n, b in enumerate(s.split("**")))
    s = "".join(f"<i>{b}</i>" if n % 2 else b for n, b in enumerate(s.split("*")))
    return s


def render_guide_md() -> str:
    """The agent-readable guide. An agent fetches this and follows it."""
    out = ["# KYA — Know Your Agent",
           "",
           "> Check who you're dealing with, before you deal.",
           "> Live: https://kya-production-f846.up.railway.app · OKX.AI Agent #5290",
           ""]
    for block in GUIDE:
        kind = block[0]
        if kind == "h":
            out += [f"## {block[1]}", ""]
        elif kind == "p":
            out += [_inline_md(block[1]), ""]
        elif kind == "code":
            out += ["```", block[1], "```", ""]
        elif kind == "note":
            out += [f"> {_inline_md(block[1])}", ""]
        elif kind == "table":
            head, rows = block[1], block[2]
            out += ["| " + " | ".join(head) + " |",
                    "|" + "|".join("---" for _ in head) + "|"]
            out += ["| " + " | ".join(r) + " |" for r in rows]
            out += [""]
    return "\n".join(out)


def render_guide_html(nav: str, eye: str, css: str) -> str:
    body = []
    for block in GUIDE:
        kind = block[0]
        if kind == "h":
            body.append(f'<h2 class="g-h">{_html.escape(block[1])}</h2>')
        elif kind == "p":
            body.append(f'<p class="g-p">{_inline_html(block[1])}</p>')
        elif kind == "code":
            body.append(f'<pre class="g-code"><code>{_html.escape(block[1])}</code></pre>')
        elif kind == "note":
            body.append(f'<p class="g-note">{_inline_html(block[1])}</p>')
        elif kind == "table":
            head, rows = block[1], block[2]
            th = "".join(f"<th>{_inline_html(h)}</th>" for h in head)
            tr = "".join("<tr>" + "".join(f"<td>{_inline_html(c)}</td>" for c in r) + "</tr>"
                         for r in rows)
            body.append(f'<table class="g-t"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>')
    return _GUIDE_PAGE.format(css=css + _GUIDE_CSS, eye=eye, nav=nav, body="".join(body))


_GUIDE_CSS = """
.g-wrap{max-width:760px}
.g-h{font-family:'Futura','Avenir Next','Helvetica Neue',sans-serif;font-size:22px;font-weight:700;
  letter-spacing:-.2px;color:#BCE82F;margin:44px 0 14px;padding-top:18px;border-top:1px solid #26262A}
.g-h:first-of-type{border-top:none;margin-top:26px}
.g-p{font-size:15px;color:#C9C9CD;line-height:1.62;margin-bottom:14px}
.g-p b{color:#FFFFFF;font-weight:600}
.g-p code,.g-note code,.g-t code{font-family:'SF Mono',Menlo,monospace;font-size:12.5px;
  color:#BCE82F;background:#141416;border:1px solid #26262A;padding:1px 5px}
.g-code{font-family:'SF Mono',Menlo,monospace;font-size:12.5px;color:#C9C9CD;background:#141416;
  border:1px solid #26262A;padding:14px 16px;margin:6px 0 18px;overflow-x:auto;line-height:1.55;white-space:pre}
.g-note{font-size:14px;color:#8A8A8E;line-height:1.6;margin:0 0 12px;padding:11px 14px;
  border-left:2px solid #6E8A34;background:#141416}
.g-note b{color:#C9C9CD;font-weight:600}
.g-t{width:100%;border-collapse:collapse;margin:6px 0 20px;border:1px solid #26262A}
.g-t th{font-family:'SF Mono',Menlo,monospace;font-size:10px;letter-spacing:2px;color:#8A8A8E;
  text-align:left;padding:10px 14px;border-bottom:1px solid #26262A;background:#141416;font-weight:400}
.g-t td{font-size:13.5px;color:#C9C9CD;padding:11px 14px;border-bottom:1px solid #1d1d20;
  border-right:1px solid #1d1d20;vertical-align:top}
.g-t td:last-child{border-right:none}
.g-t tr:last-child td{border-bottom:none}
.g-foot{margin-top:40px;padding-top:16px;border-top:1px solid #26262A;font-family:'SF Mono',Menlo,monospace;
  font-size:10px;letter-spacing:2px;color:#8A8A8E;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
.g-foot a{color:#BCE82F;text-decoration:none}
"""

_GUIDE_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KYA · Guide</title><style>{css}</style></head><body><div class="wrap g-wrap">
<header class="top">
  <div class="brand">{eye}<h1>KYA</h1></div>
  {nav}
</header>
{body}
<div class="g-foot">
  <span>MACHINE-READABLE: <a href="/guide.md">/guide.md</a></span>
  <span>AGENT #5290 · X LAYER · OKX.AI</span>
</div>
</div></body></html>"""
