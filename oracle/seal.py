"""
KYA visual credentials — a hardened, self-contained SVG "agent passport".

Rendered in the KYA brand identity: brand lime (#BCE82F) on black, white workhorse
text, and the signature EYE as the verdict device —
    CLEARED = an open, watchful lime eye
    WARY    = a narrowed, dimmed eye
    WOLF    = a slashed, nearly-dark eye ("we see through you").

Two renders:
  render_stamp(...)    -> small embeddable eye badge (for READMEs / sites)
  render_passport(...) -> the full passport data-page card (the shareable hero)

Security: every dynamic value is XML-escaped, verdict is allowlisted, no external
refs/scripts/fonts. Serve with a locked-down CSP.
"""
from __future__ import annotations

import base64
import functools
from pathlib import Path

_ASSET = Path(__file__).resolve().parent / "assets" / "kya_wordmark.png"
_LOGO_AR = 348 / 185  # width/height of the extracted wordmark


@functools.lru_cache(maxsize=1)
def _logo_uri() -> str | None:
    """The real KYA wordmark as a data URI (embedded, self-contained). None if absent."""
    try:
        return "data:image/png;base64," + base64.b64encode(_ASSET.read_bytes()).decode()
    except OSError:
        return None


# ---- KYA brand tokens ----
BG = "#0B0B0C"          # near-black page
PANEL = "#141416"       # slightly raised panel
INK = "#FFFFFF"         # primary text
MUTE = "#8A8A8E"        # muted labels
LIME = "#BCE82F"        # brand accent
# ONE hue — see oracle/watchtower.py. The eye's FORM says which verdict; luminance says
# how much light the agent earned. Traffic-light amber/red was the loudest vibe-code tell.
_ACCENT = {"SAFE": LIME, "CAUTION": "#6E8A34", "BLOCK": "#3C4522"}
_STAMP_WORD = {"SAFE": "CLEARED", "CAUTION": "WARY", "BLOCK": "WOLF"}
_EYE_STATE = {"SAFE": "open", "CAUTION": "wary", "BLOCK": "wolf"}
_ALLOWED = {"SAFE", "CAUTION", "BLOCK"}

_ROUND = "'Futura', 'Avenir Next', 'Helvetica Neue', Helvetica, sans-serif"
_SANS = "'Helvetica Neue', Helvetica, Arial, sans-serif"
_MONO = "'SF Mono', 'DejaVu Sans Mono', Menlo, Consolas, monospace"


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def _wrap(text: str, width: int, max_lines: int = 2) -> list[str]:
    """Word-wrap to `width` chars over at most `max_lines`; ellipsize any overflow."""
    lines: list[str] = []
    cur = ""
    for w in text.split():
        cand = f"{cur} {w}".strip()
        if len(cand) <= width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if len(lines) < max_lines and cur and cur not in lines:
        lines.append(cur)
    if not lines:
        lines = [text[:width]]
    if len(" ".join(lines)) < len(text):
        lines[-1] = (lines[-1][:width - 1].rstrip() + "…") if len(lines[-1]) >= width else lines[-1] + "…"
    return lines[:max_lines]


def _accent(verdict: str) -> str:
    return _ACCENT.get(verdict, _ACCENT["BLOCK"])


def _guilloche(cx: float, cy: float, R: float, r: float, d: float,
               color: str, opacity: float, sw: float = 0.6) -> str:
    """A hypotrochoid rosette — the classic banknote/passport security-print lace.
    Pure parametric math -> one path; deterministic, resolution-independent."""
    import math
    k = (R - r) / r
    pts, steps = [], 720
    for i in range(steps + 1):
        t = (i / steps) * 2 * math.pi * (r if r == int(r) else 6)
        x = (R - r) * math.cos(t) + d * math.cos(k * t)
        y = (R - r) * math.sin(t) - d * math.sin(k * t)
        pts.append(f"{cx + x:.1f} {cy + y:.1f}")
    return (f'<path d="M {" L ".join(pts)}" fill="none" stroke="{color}" '
            f'stroke-width="{sw}" opacity="{opacity}"/>')


def _eye(cx: float, cy: float, scale: float, color: str, state: str) -> str:
    """The KYA eye, drawn per verdict state. scale ~ half-width in px.
      open = wide & alert (lashes) · wary = narrowed squint (brow) · wolf = slashed."""
    w = scale
    h = scale * (0.62 if state == "open" else 0.34 if state == "wary" else 0.58)
    almond = (f'M {cx-w:.1f} {cy:.1f} Q {cx:.1f} {cy-h:.1f} {cx+w:.1f} {cy:.1f} '
              f'Q {cx:.1f} {cy+h:.1f} {cx-w:.1f} {cy:.1f} Z')
    sw = max(3, scale * 0.09)
    parts = [f'<path d="{almond}" fill="{color}"/>',
             f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{h*0.58:.1f}" fill="{BG}"/>']  # pupil hole
    if state == "open":
        parts.append("".join(
            f'<line x1="{cx+dx:.1f}" y1="{cy-h-6:.1f}" x2="{cx+dx*1.15:.1f}" y2="{cy-h-scale*0.42:.1f}" '
            f'stroke="{color}" stroke-width="{sw:.1f}" stroke-linecap="round"/>'
            for dx in (-w*0.42, 0, w*0.42)))
    elif state == "wary":
        # a lowered brow over a narrowed eye — suspicion, not a frown
        parts.append(f'<line x1="{cx-w*0.95:.1f}" y1="{cy-h-scale*0.30:.1f}" x2="{cx+w*0.55:.1f}" '
                     f'y2="{cy-h-scale*0.10:.1f}" stroke="{color}" stroke-width="{sw:.1f}" stroke-linecap="round"/>')
    else:  # wolf — a diagonal slash through the eye
        parts.append(f'<line x1="{cx-w*1.05:.1f}" y1="{cy+h*1.4:.1f}" x2="{cx+w*1.05:.1f}" y2="{cy-h*1.4:.1f}" '
                     f'stroke="{color}" stroke-width="{max(5, scale*0.13):.1f}" stroke-linecap="round"/>')
    return f'<g>{"".join(parts)}</g>'


def _wordmark(x: float, y: float, size: float, eye_color: str = LIME) -> str:
    """The real KYA wordmark (embedded PNG) with the eye in the A; text fallback."""
    uri = _logo_uri()
    if uri:
        h = size * 1.15
        return (f'<image x="{x:.1f}" y="{y-size*0.86:.1f}" height="{h:.1f}" '
                f'width="{h*_LOGO_AR:.1f}" href="{uri}" preserveAspectRatio="xMinYMid meet"/>')
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{_ROUND}" font-weight="800" '
            f'font-size="{size:.0f}" letter-spacing="-1" fill="{INK}">KYA</text>'
            f'<circle cx="{x+size*1.62:.1f}" cy="{y-size*0.30:.1f}" r="{size*0.09:.1f}" fill="{eye_color}"/>')


# --------------------------------------------------------------------- stamp
def render_stamp(verdict: str, agent_id: str, date_str: str = "") -> str:
    """A small (260x92) embeddable eye badge."""
    verdict = verdict if verdict in _ALLOWED else "BLOCK"
    col = _accent(verdict)
    word = _STAMP_WORD[verdict]
    aid, date = _esc(agent_id), _esc(date_str)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="260" height="92" viewBox="0 0 260 92" role="img" aria-label="KYA {word}">
  <rect width="260" height="92" rx="14" fill="{BG}"/>
  <rect x="1" y="1" width="258" height="90" rx="13" fill="none" stroke="{col}" stroke-width="1.5" opacity="0.5"/>
  {_eye(52, 46, 26, col, _EYE_STATE[verdict])}
  <text x="94" y="40" font-family="{_MONO}" font-size="10" letter-spacing="2.5" fill="{MUTE}">KYA · KNOW YOUR AGENT</text>
  <text x="94" y="66" font-family="{_ROUND}" font-weight="800" font-size="24" fill="{col}">{word}</text>
  <text x="248" y="84" text-anchor="end" font-family="{_MONO}" font-size="8.5" fill="{MUTE}">#{aid} {date}</text>
</svg>"""


# ------------------------------------------------------------------ passport
def render_passport(verdict: str, name: str, agent_id: str, *,
                    evidence: dict | None = None, pronouncement: str = "",
                    issued: str = "", expires: str = "", digest: str = "",
                    pubkey: str = "") -> str:
    verdict = verdict if verdict in _ALLOWED else "BLOCK"
    ev = evidence or {}
    col = _accent(verdict)
    word = _STAMP_WORD[verdict]

    pron_lines = _wrap((pronouncement or "").strip(), 30, 3)  # narrow column, clears the eye
    pron_svg = "".join(
        f'<text x="0" y="{28 + i*30}" font-family="{_SANS}" font-style="italic" '
        f'font-size="19" fill="{INK}">{_esc(("“" if i == 0 else "") + ln + ("”" if i == len(pron_lines)-1 else ""))}</text>'
        for i, ln in enumerate(pron_lines))

    nm = _esc((name or "UNKNOWN AGENT").strip()[:26])
    aid = _esc(agent_id)
    sales = _esc(ev.get("sales", "—"))
    rating = ev.get("securityRate")
    rating = _esc(f"{rating:.2f}" if isinstance(rating, (int, float)) else "—")
    svc = _esc(ev.get("serviceCount", "—"))
    eps = ev.get("endpoints") or {}
    serving = sum(1 for lbl in eps.values() if "live" in str(lbl))
    ep_txt = _esc(f"{serving}/{len(eps)} serving" if eps else "none")

    mrz1 = _esc(_mrz(f"PAKYA{name or 'UNKNOWN'}", 40))
    mrz2 = _esc(_mrz(f"{agent_id}<{verdict}<{(digest or '')[:16]}", 40))
    pk = _esc((pubkey or "")[:16])
    initial = _esc((name or "?")[:1].upper())
    microtext = _esc(("KYA · KNOW YOUR AGENT · OKX.AI · X LAYER · " * 6)[:150])

    W, H = 680, 960
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="KYA agent passport: {word}">
  <defs>
    <pattern id="tiles" width="17" height="17" patternUnits="userSpaceOnUse">
      <rect width="6" height="6" fill="{INK}" opacity="0.035"/>
    </pattern>
  </defs>
  <rect width="{W}" height="{H}" fill="{BG}"/>
  <rect width="{W}" height="{H}" fill="url(#tiles)"/>
  {_guilloche(238, 706, 132, 24, 36, LIME, 0.10)}
  {_guilloche(238, 706, 84, 15, 22, LIME, 0.07)}
  <rect x="22" y="22" width="{W-44}" height="{H-44}" fill="none" stroke="{INK}" stroke-width="1.5" opacity="0.25"/>
  <rect x="22" y="22" width="{W-44}" height="6" fill="{LIME}"/>

  <!-- header -->
  <g transform="translate(54 104)">
    {_wordmark(0, 0, 40)}
    <text x="0" y="20" font-family="{_MONO}" font-size="10.5" letter-spacing="4" fill="{MUTE}">KNOW YOUR AGENT</text>
    <text x="{W-108}" y="-16" text-anchor="end" font-family="{_MONO}" font-size="10" letter-spacing="2" fill="{MUTE}">AGENT PASSPORT CONTROL</text>
    <text x="{W-108}" y="2" text-anchor="end" font-family="{_MONO}" font-size="10" letter-spacing="2" fill="{LIME}" opacity="0.8">X LAYER · OKX.AI</text>
  </g>
  <line x1="54" y1="128" x2="{W-54}" y2="128" stroke="{INK}" stroke-width="1" opacity="0.2"/>
  <text x="54" y="139" font-family="{_MONO}" font-size="4" letter-spacing="0.6" fill="{MUTE}" opacity="0.65">{microtext}</text>

  <!-- photo box + data -->
  <g transform="translate(54 156)">
    <rect x="0" y="0" width="150" height="182" rx="6" fill="{PANEL}" stroke="{INK}" stroke-opacity="0.15"/>
    <text x="75" y="120" text-anchor="middle" font-family="{_ROUND}" font-weight="800" font-size="94" fill="{INK}" opacity="0.9">{initial}</text>
    <text x="75" y="152" text-anchor="middle" font-family="{_MONO}" font-size="9" letter-spacing="2" fill="{MUTE}">ASP</text>
  </g>
  <g transform="translate(230 156)" font-family="{_MONO}">
    {_field(0, "AGENT / NAME", nm)}
    {_field(1, "AGENT No.", f"#{aid}")}
    {_field(2, "COMPLETED SALES", sales)}
    {_field(3, "SECURITY RATING", f"{rating} / 5")}
    {_field(4, "SERVICES", svc)}
    {_field(5, "ENDPOINTS", ep_txt)}
  </g>

  <!-- verdict: the eye -->
  <g transform="translate(468 480)">
    <circle cx="0" cy="0" r="120" fill="none" stroke="{col}" stroke-width="1.25" opacity="0.4"/>
    {_eye(0, -14, 74, col, _EYE_STATE[verdict])}
    <text x="0" y="72" text-anchor="middle" font-family="{_ROUND}" font-weight="800" font-size="40" letter-spacing="1" fill="{col}">{word}</text>
    <text x="0" y="96" text-anchor="middle" font-family="{_MONO}" font-size="10" letter-spacing="3" fill="{MUTE}">{_esc(issued or '')}</text>
  </g>

  <!-- pronouncement -->
  <g transform="translate(54 400)">
    <text x="0" y="0" font-family="{_MONO}" font-size="10" letter-spacing="2.5" fill="{LIME}" opacity="0.85">VERDICT OF THE WATCH</text>
    {pron_svg}
  </g>

  <!-- signing / validity -->
  <g transform="translate(54 {H-176})" font-family="{_MONO}" font-size="11" fill="{MUTE}">
    <line x1="0" y1="-18" x2="{W-108}" y2="-18" stroke="{INK}" stroke-width="0.75" opacity="0.2"/>
    <text x="0" y="6">ISSUED  <tspan fill="{INK}">{_esc(issued or '—')}</tspan></text>
    <text x="230" y="6">EXPIRES  <tspan fill="{INK}">{_esc(expires or '—')}</tspan></text>
    <text x="0" y="26">ED25519 · {pk}…  ·  re-verify at kya.fyi/verify?agentId={aid}</text>
  </g>

  <!-- machine-readable zone -->
  <g transform="translate(54 {H-96})">
    <rect x="-8" y="-26" width="{W-92}" height="76" rx="4" fill="{LIME}" opacity="0.06"/>
    <text x="0" y="0" font-family="{_MONO}" font-size="18" letter-spacing="2" fill="{INK}" opacity="0.92">{mrz1}</text>
    <text x="0" y="30" font-family="{_MONO}" font-size="18" letter-spacing="2" fill="{INK}" opacity="0.92">{mrz2}</text>
  </g>
</svg>"""


def _mrz(s: str, width: int) -> str:
    out = "".join(c if c.isalnum() else "<" for c in s.upper())
    return (out + "<" * width)[:width]


def _field(row: int, label: str, value: str) -> str:
    # value is already escaped by the caller; label is a trusted literal.
    y = row * 30
    return (f'<text x="0" y="{y}" font-size="9.5" letter-spacing="1.5" fill="{MUTE}">{label}</text>'
            f'<text x="0" y="{y+16}" font-size="15" fill="{INK}">{value}</text>')
