"""
The Watchtower — KYA's live board of agent trust verdicts and crossings.

Renders in the KYA passport identity (lime #D9F94C on near-black, the eye motif,
customs-stamp verdicts CLEARED / WARY / WOLF). Self-contained HTML, no external
assets, so it serves under the same locked-down surface as the passport.
"""
from __future__ import annotations

import html
import time

_C = {
    "bg": "#0B0B0C", "panel": "#141416", "line": "#26262A", "ink": "#FFFFFF",
    "mute": "#8A8A8E", "lime": "#D9F94C", "amber": "#F4B740", "red": "#FF5247",
}
_ACCENT = {"SAFE": _C["lime"], "CAUTION": _C["amber"], "BLOCK": _C["red"]}
_STAMP = {"SAFE": "CLEARED", "CAUTION": "WARY", "BLOCK": "WOLF"}


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
    """The KYA eye, matched to the verdict: open (lime), wary (amber), slashed (red)."""
    c = _ACCENT.get(state, _C["lime"])
    slash = (f'<line x1="4" y1="20" x2="22" y2="6" stroke="{c}" stroke-width="2.4" '
             f'stroke-linecap="round"/>') if state == "BLOCK" else ""
    ry = 3.2 if state == "CAUTION" else 5.2
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 26 26" fill="none" aria-hidden="true">'
            f'<path d="M2 13 Q13 3 24 13 Q13 23 2 13 Z" stroke="{c}" stroke-width="1.8" fill="none"/>'
            f'<ellipse cx="13" cy="13" rx="3.4" ry="{ry}" fill="{c}"/>{slash}</svg>')


def render_watchtower(verdicts: list[dict], changes: list[dict], *, host: str = "") -> str:
    counts = {"SAFE": 0, "CAUTION": 0, "BLOCK": 0}
    for v in verdicts:
        counts[v.get("verdict", "BLOCK")] = counts.get(v.get("verdict", "BLOCK"), 0) + 1

    rows = "".join(_row(v, host) for v in verdicts) or _empty_row()
    crossings = "".join(_crossing(c) for c in changes) or (
        f'<div class="cx-empty">No crossings yet — verdicts are stable.</div>')

    tally = "".join(
        f'<div class="tally"><span class="tnum" style="color:{_ACCENT[k]}">{counts[k]}</span>'
        f'<span class="tlab">{_STAMP[k]}</span></div>'
        for k in ("SAFE", "CAUTION", "BLOCK"))

    now = time.strftime("%d %b %Y · %H:%M UTC", time.gmtime()).upper()
    return _PAGE.format(css=_CSS, eye=_eye("SAFE", 30), rows=rows, crossings=crossings,
                        tally=tally, now=now, total=len(verdicts))


def _row(v: dict, host: str) -> str:
    verdict = v.get("verdict", "BLOCK")
    c = _ACCENT.get(verdict, _C["red"])
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
    return ('<div class="row-empty">No agents on the board yet. '
            'Call <code>/verify?agentId=…</code> to admit one.</div>')


_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0B0B0C;color:#FFFFFF;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;padding:clamp(16px,4vw,48px);line-height:1.4;overflow-x:hidden}
.mono{font-family:'SF Mono',Menlo,Consolas,monospace}
.wrap{max-width:960px;margin:0 auto}
.top{border-bottom:1px solid #26262A;padding-bottom:20px;margin-bottom:28px}
.brand{display:flex;align-items:center;gap:12px}
.brand h1{font-family:'Arial Rounded MT Bold','Helvetica Neue',sans-serif;font-size:clamp(30px,6vw,44px);
  font-weight:900;letter-spacing:-1px;color:#D9F94C}
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
.row-empty code{font-family:'SF Mono',monospace;color:#D9F94C}
.foot{margin-top:28px;padding-top:16px;border-top:1px solid #26262A;
  font-family:'SF Mono',Menlo,monospace;font-size:10px;letter-spacing:1.5px;color:#8A8A8E;
  display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
.foot b{color:#D9F94C;font-weight:400}
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
  <div class="kicker">AGENT PASSPORT CONTROL · WATCHTOWER &nbsp;·&nbsp; <b>X LAYER · OKX.AI</b></div>
  <div class="tallies">{tally}</div>
</header>
<div class="grid">
  <section>
    <div class="sec-h"><span>Manifest · {total} on watch</span><span>VERDICT</span></div>
    <div class="board">{rows}</div>
  </section>
  <section>
    <div class="sec-h"><span>Recent crossings</span><span>WHO TURNED</span></div>
    <div class="cx-panel">{crossings}</div>
  </section>
</div>
<footer class="foot"><span>EVERY VERDICT ED25519-SIGNED · RE-VERIFIED ON CHANGE</span><span>{now}</span></footer>
</div></body></html>"""
