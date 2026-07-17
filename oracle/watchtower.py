"""
The Watchtower — KYA's live board of agent trust verdicts and changes.

Renders in the KYA passport identity (lime #BCE82F on near-black, the eye motif,
verdicts SAFE / CAUTION / BLOCK). Self-contained HTML, no external
assets, so it serves under the same locked-down surface as the passport.
"""
from __future__ import annotations

import html
import time

# ONE hue. Verdict is carried by the eye's FORM (open / wary / slashed) and by LUMINANCE —
# never by hue. Amber/green/red status lights were the board's loudest vibe-code tell, and
# they were redundant: the eye already says which verdict it is. A single-hue ramp says
# something a traffic light cannot — how much light an agent has EARNED. SAFE glows at full
# brand lime, CAUTION is dimmed, BLOCK is nearly dark. Trust as luminance.
# Lime is the avatar's exact green (#BCE82F), so the board and the mark are one brand.
_C = {
    "bg": "#0B0B0C", "panel": "#141416", "line": "#26262A", "ink": "#FFFFFF",
    "mute": "#8A8A8E",
    "lime": "#BCE82F",   # earned, full light
    "dim": "#6E8A34",    # unproven, half light
    "dark": "#3C4522",   # refused, nearly out
}
_ACCENT = {"SAFE": _C["lime"], "CAUTION": _C["dim"], "BLOCK": _C["dark"]}
# The board says exactly what the API says. It used to read CLEARED / WARY / WOLF —
# a second vocabulary for the same three values, so a judge cross-referencing the
# payload saw drift, and "WOLF" is a costume on a security product.
_STAMP = {"SAFE": "SAFE", "CAUTION": "CAUTION", "BLOCK": "BLOCK"}


def _ago(ts: int) -> str:
    if not ts:
        return "—"
    d = max(0, int(time.time()) - int(ts))
    if d < 60:
        return f"{d}s ago"
    if d < 3600:
        return f"{d // 60}m ago"
    if d < 86400:
        return f"{d // 3600}h ago"
    return f"{d // 86400}d ago"


def _eye(state: str, size: int = 26) -> str:
    """The KYA eye, matched to the verdict: open (full light), wary (dimmed), slashed (nearly out).

    Form carries the verdict; luminance carries how much trust was earned. One hue only.
    """
    c = _ACCENT.get(state, _C["lime"])
    slash = (f'<line x1="4" y1="20" x2="22" y2="6" stroke="{c}" stroke-width="2.4" '
             f'stroke-linecap="round"/>') if state == "BLOCK" else ""
    ry = 3.2 if state == "CAUTION" else 5.2
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 26 26" fill="none" aria-hidden="true">'
            f'<path d="M2 13 Q13 3 24 13 Q13 23 2 13 Z" stroke="{c}" stroke-width="1.8" fill="none"/>'
            f'<ellipse cx="13" cy="13" rx="3.4" ry="{ry}" fill="{c}"/>{slash}</svg>')



def _nav(active: str, host: str = "") -> str:
    """One bar, three surfaces. There was no way to get from the board to the operator
    graph except by typing the URL — the two halves of the product never linked to each
    other. Active surface is the only lit item; the rest stay muted until hovered."""
    items = [("watchtower", "WATCHTOWER"), ("operators", "OPERATORS"),
             ("changes", "CHANGES"), ("guide", "GUIDE")]
    links = "".join(
        f'<a class="nav-a{" on" if k == active else ""}" href="{host}/{k}">{label}</a>'
        for k, label in items)
    return f'<nav class="nav">{links}<span class="nav-tag">X LAYER · OKX.AI</span></nav>'

def render_watchtower(verdicts: list[dict], changes: list[dict], *, host: str = "") -> str:
    counts = {"SAFE": 0, "CAUTION": 0, "BLOCK": 0}
    for v in verdicts:
        counts[v.get("verdict", "BLOCK")] = counts.get(v.get("verdict", "BLOCK"), 0) + 1

    rows = "".join(_row(v, host) for v in verdicts) or _empty_row()
    crossings = "".join(_crossing(c) for c in changes) or (
        f'<div class="cx-empty">No changes yet — verdicts are stable.</div>')

    tally = "".join(
        f'<div class="tally"><span class="tnum" style="color:{_ACCENT[k]}">{counts[k]}</span>'
        f'<span class="tlab">{_STAMP[k]}</span></div>'
        for k in ("SAFE", "CAUTION", "BLOCK"))

    now = time.strftime("%d %b %Y · %H:%M UTC", time.gmtime()).upper()
    return _PAGE.format(css=_CSS, eye=_eye("SAFE", 30), rows=rows, crossings=crossings,
                        tally=tally, now=now, total=len(verdicts),
                        nav=_nav("watchtower", host))


def _row(v: dict, host: str) -> str:
    verdict = v.get("verdict", "BLOCK")
    c = _ACCENT.get(verdict, _C["dark"])
    aid = html.escape(str(v.get("agent_id", "")))
    name = html.escape(v.get("name") or "—")
    link = f'{host}/passport?agentId={aid}' if host else f'/passport?agentId={aid}'
    return (
        f'<a class="row v-{verdict}" href="{link}">'
        f'<span class="eye">{_eye(verdict)}</span>'
        f'<span class="id">#{aid}</span>'
        f'<span class="name">{name}</span>'
        f'<span class="stamp" style="color:{c};border-color:{c}">{_STAMP[verdict]}</span>'
        f'<span class="score" style="color:{c}">{v.get("score", 0)}</span>'
        f'<span class="seen">{_ago(v.get("issued_at", 0))}</span>'
        f'</a>')


def _crossing(c: dict) -> str:
    frm, to = c.get("from_verdict", "?"), c.get("to_verdict", "?")
    up = ("SAFE", "CAUTION", "BLOCK").index(to) < ("SAFE", "CAUTION", "BLOCK").index(frm) \
        if frm in _STAMP and to in _STAMP else False
    arrow_c = _ACCENT.get(to, _C["mute"])
    name = html.escape(c.get("name") or f"#{c.get('agent_id','')}")
    return (
        f'<div class="cx">'
        f'<span class="cx-name">{name}</span>'
        f'<span class="cx-move"><span style="color:{_ACCENT.get(frm,_C["mute"])}">{_STAMP.get(frm,frm)}</span>'
        f'<span class="cx-arrow" style="color:{arrow_c}">{"↑" if up else "↓"}</span>'
        f'<span style="color:{arrow_c}">{_STAMP.get(to,to)}</span></span>'
        f'<span class="cx-when">{_ago(c.get("at", 0))}</span>'
        f'</div>')


def _empty_row() -> str:
    return ('<div class="row-empty">No agents verified yet. '
            'Call <code>/verify?agentId=…</code> to admit one.</div>')


_CSS = """

.nav{display:flex;align-items:center;gap:0;margin-top:16px;border-top:1px solid #26262A;
  border-bottom:1px solid #26262A}
.nav-a{font-family:'SF Mono',Menlo,monospace;font-size:10px;letter-spacing:2.5px;color:#8A8A8E;
  text-decoration:none;padding:11px 16px;border-right:1px solid #26262A;transition:color .12s,background .12s}
.nav-a:first-child{padding-left:0;border-left:none}
.nav-a:hover{color:#FFFFFF;background:#141416}
.nav-a.on{color:#BCE82F}
.nav-tag{margin-left:auto;font-family:'SF Mono',Menlo,monospace;font-size:10px;letter-spacing:2.5px;
  color:#8A8A8E;padding:11px 0}
.tallies{border-bottom:1px solid #26262A}
.tally{padding:18px 26px 18px 0;border-right:1px solid #26262A}
.tally:last-child{border-right:none}
.board{border:1px solid #26262A}
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0B0B0C;color:#FFFFFF;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;padding:clamp(16px,4vw,48px);line-height:1.4;overflow-x:hidden}
.mono{font-family:'SF Mono',Menlo,Consolas,monospace}
.wrap{max-width:960px;margin:0 auto}
.top{border-bottom:1px solid #26262A;padding-bottom:20px;margin-bottom:28px}
.brand{display:flex;align-items:center;gap:12px}
.brand h1{font-family:'Futura','Avenir Next','Helvetica Neue',sans-serif;font-size:clamp(30px,6vw,44px);
  font-weight:900;letter-spacing:-1px;color:#BCE82F}
.kicker{font-family:'SF Mono',Menlo,monospace;font-size:11px;letter-spacing:3px;color:#8A8A8E;
  text-transform:uppercase;margin-top:10px}
.kicker b{color:#FFF;font-weight:400}
.tallies{display:flex;gap:28px;margin-top:22px;flex-wrap:wrap}
.tally{display:flex;flex-direction:column}
.tnum{font-family:'SF Mono',Menlo,monospace;font-size:clamp(34px,7vw,52px);font-weight:700;line-height:1}
.tlab{font-family:'SF Mono',Menlo,monospace;font-size:10px;letter-spacing:2.5px;color:#8A8A8E;margin-top:6px}
.grid{display:grid;grid-template-columns:minmax(0,1fr);gap:28px}
.grid>section{min-width:0}
@media(min-width:760px){.grid{grid-template-columns:minmax(0,1.55fr) minmax(0,1fr)}}
.sec-h{font-family:'SF Mono',Menlo,monospace;font-size:11px;letter-spacing:3px;color:#8A8A8E;
  text-transform:uppercase;margin-bottom:12px;display:flex;justify-content:space-between}
.board{display:flex;flex-direction:column;border:1px solid #26262A;border-radius:4px;overflow:hidden;background:#141416;min-width:0}
.row{display:grid;grid-template-columns:30px 66px minmax(0,1fr) auto auto 74px;align-items:center;gap:12px;
  min-width:0;padding:14px 16px;border-bottom:1px solid #1d1d20;text-decoration:none;color:#FFF;transition:background .15s}
.row:last-child{border-bottom:none}
.row:hover{background:#1a1a1d}
.eye{display:flex}
.id{font-family:'SF Mono',Menlo,monospace;font-size:13px;color:#8A8A8E}
.name{font-size:15px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.stamp{font-family:'SF Mono',Menlo,monospace;font-size:10px;font-weight:700;letter-spacing:1.5px;
  border:1px solid;border-radius:3px;padding:3px 7px}
.score{font-family:'SF Mono',Menlo,monospace;font-size:18px;font-weight:700;text-align:right;min-width:34px}
.seen{font-family:'SF Mono',Menlo,monospace;font-size:11px;color:#8A8A8E;text-align:right}
.v-BLOCK .name{color:#C9C9CD}
.cx-panel{border:1px solid #26262A;border-radius:4px;background:#141416;padding:6px 0}
.cx{display:flex;flex-direction:column;gap:3px;padding:11px 16px;border-bottom:1px solid #1d1d20}
.cx:last-child{border-bottom:none}
.cx-name{font-size:13px;font-weight:500}
.cx-move{font-family:'SF Mono',Menlo,monospace;font-size:11px;font-weight:700;letter-spacing:1px;
  display:flex;align-items:center;gap:8px}
.cx-arrow{font-size:14px}
.cx-when{font-family:'SF Mono',Menlo,monospace;font-size:10px;color:#8A8A8E}
.cx-empty,.row-empty{padding:20px 16px;color:#8A8A8E;font-size:13px}
.row-empty code{font-family:'SF Mono',monospace;color:#BCE82F}
.foot{margin-top:28px;padding-top:16px;border-top:1px solid #26262A;
  font-family:'SF Mono',Menlo,monospace;font-size:10px;letter-spacing:1.5px;color:#8A8A8E;
  display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
.foot b{color:#BCE82F;font-weight:400}
@media(max-width:520px){
  /* verdict is already encoded by the coloured eye + coloured score, so the
     stamp/timestamp columns drop out and the row can't out-width the viewport. */
  .row{grid-template-columns:24px 50px minmax(0,1fr) auto;gap:10px;padding:13px 13px}
  .seen,.stamp{display:none}
  .kicker{font-size:10px;letter-spacing:1.5px;line-height:1.8;word-break:break-word}
  .score{font-size:17px}
  .name{font-size:14px;max-width:calc(100vw - 190px)}
  .foot{font-size:9px;letter-spacing:1px}
}
"""

_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KYA · Watchtower</title><style>{css}</style></head><body><div class="wrap">
<header class="top">
  <div class="brand">{eye}<h1>KYA</h1></div>
  {nav}
  <div class="tallies">{tally}</div>
</header>
<div class="grid">
  <section>
    <div class="sec-h"><span>{total} agents verified</span><span>VERDICT</span></div>
    <div class="board">{rows}</div>
  </section>
  <section>
    <div class="sec-h"><span>Recent changes</span><span>WHAT MOVED</span></div>
    <div class="cx-panel">{crossings}</div>
  </section>
</div>
<footer class="foot"><span>EVERY VERDICT ED25519-SIGNED · RE-VERIFIED ON CHANGE</span><span>{now}</span></footer>
</div></body></html>"""


# --------------------------------------------------------------- operators board
def _stems(names: list[str]) -> list[str]:
    """Name templates a farm was generated from: PulseBTC/PulseETH -> 'Pulse'."""
    import re as _re
    from collections import Counter as _C
    c: _C = _C()
    for n in names:
        s = _re.sub(r"[A-Z0-9]{2,}$", "", (n or "").strip()).strip()
        if s:
            c[s] += 1
    return [k for k, v in c.most_common(4) if v >= 3]


def _op_verdict(o: dict) -> tuple[str, str]:
    """(verdict, label) for an OPERATOR. Same three states as an agent — this is the
    same passport desk, just looking at the face instead of the document."""
    agents = int(o.get("agents") or 0)
    sales = int(o.get("sales") or 0)
    # A fleet is only called a farm when it shows no real customers AND looks
    # generated. An operator with genuine sales is a business, not a farm.
    if agents >= 5 and sales < agents and _stems(o.get("names") or []):
        return "BLOCK", "ONE OWNER"
    if sales >= agents:
        return "SAFE", "BUSINESS"
    return "CAUTION", "THIN"


def _op_row(o: dict, rank: int) -> str:
    owner = o.get("owner") or ""
    agents = int(o.get("agents") or 0)
    sales = int(o.get("sales") or 0)
    verdict, label = _op_verdict(o)
    c = _ACCENT.get(verdict, _C["dark"])
    stems = _stems(o.get("names") or [])
    short = html.escape(owner[:10] + "…" + owner[-6:]) if len(owner) > 18 else html.escape(owner)
    tmpl = html.escape(" · ".join(f"{s}*" for s in stems)) if stems else "—"
    return (
        f'<div class="row v-{verdict}">'
        f'<div class="eye">{_eye(verdict, 22)}</div>'
        f'<div class="id mono">#{rank}</div>'
        f'<div class="name mono">{short}</div>'
        f'<div class="op-tmpl mono">{tmpl}</div>'
        f'<div class="stamp" style="color:{c};border-color:{c}">{label}</div>'
        f'<div class="score mono" style="color:{c}">{agents}</div>'
        f'<div class="seen mono">{sales} sold</div>'
        f"</div>"
    )


def render_operators(data: dict, *, host: str = "") -> str:
    ops = data.get("operators") or []
    total_agents = int(data.get("total_agents") or 0)
    total_owners = int(data.get("total_owners") or 0)
    top = ops[0] if ops else {}
    top_n = int(top.get("agents") or 0)
    # Agents that sit behind a farm: the number that reframes the marketplace.
    behind = sum(int(o.get("agents") or 0) for o in ops if _op_verdict(o)[0] == "BLOCK")
    tally = "".join(
        f'<div class="tally"><div class="tnum mono" style="color:{col}">{val}</div>'
        f'<div class="tlab">{lab}</div></div>'
        for val, lab, col in [
            (total_agents, "AGENTS INDEXED", _C["ink"]),
            (total_owners, "ACTUAL OPERATORS", _C["ink"]),
            (top_n, "BEHIND ONE WALLET", _C["lime"]),
            (behind, "AGENTS THAT ARE SHELLS", _C["lime"]),
        ]
    )
    rows = "".join(_op_row(o, i + 1) for i, o in enumerate(ops)) or _empty_row()
    return _OPS_PAGE.format(
        css=_CSS + _OPS_CSS, eye=_eye("BLOCK", 34), tally=tally, rows=rows,
        nav=_nav("operators", host),
        total=total_owners, top_n=top_n,
        now=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
    )


_OPS_CSS = """

.nav{display:flex;align-items:center;gap:0;margin-top:16px;border-top:1px solid #26262A;
  border-bottom:1px solid #26262A}
.nav-a{font-family:'SF Mono',Menlo,monospace;font-size:10px;letter-spacing:2.5px;color:#8A8A8E;
  text-decoration:none;padding:11px 16px;border-right:1px solid #26262A;transition:color .12s,background .12s}
.nav-a:first-child{padding-left:0;border-left:none}
.nav-a:hover{color:#FFFFFF;background:#141416}
.nav-a.on{color:#BCE82F}
.nav-tag{margin-left:auto;font-family:'SF Mono',Menlo,monospace;font-size:10px;letter-spacing:2.5px;
  color:#8A8A8E;padding:11px 0}
.tallies{border-bottom:1px solid #26262A}
.tally{padding:18px 26px 18px 0;border-right:1px solid #26262A}
.tally:last-child{border-right:none}
.board{border:1px solid #26262A}
.row{grid-template-columns:26px 44px minmax(0,1fr) minmax(0,1.1fr) auto 58px 74px}
.op-tmpl{font-size:11px;color:#8A8A8E;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lede{font-size:15px;color:#C9C9CD;margin:18px 0 4px;line-height:1.55}
.lede b{color:#BCE82F;font-weight:400}
@media(max-width:520px){
  .row{grid-template-columns:22px minmax(0,1fr) auto 46px;gap:10px}
  .op-tmpl,.seen,.id{display:none}
}
"""

_OPS_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KYA · Operators</title><style>{css}</style></head><body><div class="wrap">
<header class="top">
  <div class="brand">{eye}<h1>KYA</h1></div>
  {nav}
  <div class="lede">The marketplace shows you agents. It never shows you <b>who owns them</b> —
  OKX's own search API does not return the owner address. Group the same listings by wallet and
  <b>one wallet is running {top_n} of them</b>. Counts are what KYA has actually indexed, never
  a claim about what it hasn't looked at.</div>
  <div class="tallies">{tally}</div>
</header>
<div class="grid" style="grid-template-columns:minmax(0,1fr)">
  <section>
    <div class="sec-h"><span>Operators · {total} distinct wallets</span><span>AGENTS HELD</span></div>
    <div class="board">{rows}</div>
  </section>
</div>
<footer class="foot"><span>OWNER INDEX BUILT FROM get-agents · SEARCH CANNOT SEE THIS</span><span>{now}</span></footer>
</div></body></html>"""
