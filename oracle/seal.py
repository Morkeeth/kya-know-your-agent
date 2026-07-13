"""
KYA visual credentials — a hardened, self-contained SVG "agent passport".

Two renders:
  render_stamp(...)    -> small embeddable entry-stamp badge (for READMEs / sites)
  render_passport(...) -> the full passport data-page card (the shareable hero)

Aesthetic: OKX border-control brutalism — stark ink on off-white, a square-tile
security grid (the OKX "building blocks" motif), a serif passport header, and an
OCR-style monospace machine-readable zone (MRZ) that actually encodes the signed
verdict digest. The verdict is an ink ENTRY STAMP: CLEARED / WARY / WOLF.

Security (per SVG best practice): every dynamic value is XML-escaped, verdict is
allowlisted, no external refs/scripts/fonts. Serve with a locked-down CSP.
"""
from __future__ import annotations

# ink + paper + one accent per verdict (kept off the cream/serif slop cluster:
# cool near-white paper, true-ink text, a single saturated stamp colour).
INK = "#111111"
PAPER = "#F7F7F4"
FAINT = "#111111"  # used at low opacity for the security grid
_ACCENT = {
    "SAFE": "#1f8f4e",     # clearance green
    "CAUTION": "#b8860b",  # wary amber
    "BLOCK": "#c0392b",    # wolf red
}
_STAMP_WORD = {"SAFE": "CLEARED", "CAUTION": "WARY", "BLOCK": "WOLF"}
_ALLOWED = {"SAFE", "CAUTION", "BLOCK"}

_SERIF = "Georgia, 'Times New Roman', serif"
_MONO = "'SF Mono', 'DejaVu Sans Mono', Menlo, Consolas, monospace"
_SANS = "'Helvetica Neue', Helvetica, Arial, sans-serif"


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
    # if the text didn't fully fit, mark the last line
    if len(" ".join(lines)) < len(text):
        lines[-1] = (lines[-1][:width - 1].rstrip() + "…") if len(lines[-1]) >= width else lines[-1] + "…"
    return lines[:max_lines]


def _mrz(s: str, width: int) -> str:
    """Passport machine-readable-zone formatting: uppercase, spaces->'<', padded."""
    out = "".join(c if (c.isalnum()) else "<" for c in s.upper())
    return (out + "<" * width)[:width]


def _accent(verdict: str) -> str:
    return _ACCENT.get(verdict, INK)


# --------------------------------------------------------------------- stamp
def render_stamp(verdict: str, agent_id: str, date_str: str = "") -> str:
    """A small (240x84) embeddable entry-stamp badge."""
    verdict = verdict if verdict in _ALLOWED else "BLOCK"
    col = _accent(verdict)
    word = _STAMP_WORD[verdict]
    aid = _esc(agent_id)
    date = _esc(date_str)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="240" height="84" viewBox="0 0 240 84" role="img" aria-label="KYA {word}">
  <rect width="240" height="84" fill="{PAPER}"/>
  <g transform="rotate(-4 120 42)">
    <rect x="10" y="12" width="220" height="60" fill="none" stroke="{col}" stroke-width="3" rx="4"/>
    <rect x="16" y="18" width="208" height="48" fill="none" stroke="{col}" stroke-width="1" opacity="0.6" rx="2"/>
    <text x="24" y="38" font-family="{_MONO}" font-size="10" letter-spacing="2" fill="{col}">KYA · KNOW YOUR AGENT</text>
    <text x="24" y="60" font-family="{_SERIF}" font-weight="700" font-size="26" fill="{col}">{word}</text>
    <text x="228" y="60" text-anchor="end" font-family="{_MONO}" font-size="9" fill="{col}" opacity="0.8">#{aid} {date}</text>
  </g>
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

    pron_lines = _wrap((pronouncement or "").strip(), 42, 2)
    pron_svg = "".join(
        f'<text x="0" y="{30 + i*30}" font-family="{_SERIF}" font-style="italic" '
        f'font-size="20" fill="{INK}">{_esc(("“" if i == 0 else "") + ln + ("”" if i == len(pron_lines)-1 else ""))}</text>'
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

    # MRZ: two OCR-style lines; line 2 embeds verdict + agent + digest head.
    mrz1 = _mrz(f"PAKYA{name or 'UNKNOWN'}", 40)
    mrz2 = _mrz(f"{agent_id}<{verdict}<{(digest or '')[:16]}", 40)
    mrz1, mrz2 = _esc(mrz1), _esc(mrz2)
    pk = _esc((pubkey or "")[:16])

    W, H = 680, 960
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="KYA agent passport: {word}">
  <defs>
    <pattern id="tiles" width="16" height="16" patternUnits="userSpaceOnUse">
      <rect width="7" height="7" fill="{FAINT}" opacity="0.05"/>
    </pattern>
  </defs>
  <rect width="{W}" height="{H}" fill="{PAPER}"/>
  <rect width="{W}" height="{H}" fill="url(#tiles)"/>
  <rect x="24" y="24" width="{W-48}" height="{H-48}" fill="none" stroke="{INK}" stroke-width="2"/>
  <rect x="34" y="34" width="{W-68}" height="{H-68}" fill="none" stroke="{INK}" stroke-width="0.75" opacity="0.5"/>

  <!-- header -->
  <g transform="translate(56 92)">
    <!-- KYA tile wordmark -->
    <g fill="{INK}">
      <rect x="0" y="-26" width="10" height="10"/><rect x="0" y="-13" width="10" height="10"/><rect x="0" y="0" width="10" height="10"/>
      <rect x="13" y="-26" width="10" height="10"/><rect x="26" y="-26" width="10" height="10"/>
    </g>
    <text x="52" y="-4" font-family="{_SERIF}" font-weight="700" font-size="34" letter-spacing="4" fill="{INK}">KYA</text>
    <text x="52" y="18" font-family="{_MONO}" font-size="11" letter-spacing="3" fill="{INK}" opacity="0.7">KNOW YOUR AGENT</text>
    <text x="{W-112}" y="-8" text-anchor="end" font-family="{_MONO}" font-size="10" letter-spacing="2" fill="{INK}" opacity="0.7">AGENT PASSPORT CONTROL</text>
    <text x="{W-112}" y="10" text-anchor="end" font-family="{_MONO}" font-size="10" letter-spacing="2" fill="{INK}" opacity="0.5">X LAYER · OKX.AI</text>
  </g>
  <line x1="56" y1="120" x2="{W-56}" y2="120" stroke="{INK}" stroke-width="1"/>

  <!-- photo box (monogram) + data fields -->
  <g transform="translate(56 150)">
    <rect x="0" y="0" width="150" height="180" fill="none" stroke="{INK}" stroke-width="1.5"/>
    <rect x="0" y="0" width="150" height="180" fill="url(#tiles)"/>
    <text x="75" y="118" text-anchor="middle" font-family="{_SERIF}" font-weight="700" font-size="96" fill="{INK}" opacity="0.85">{_esc((name or '?')[:1].upper())}</text>
    <text x="75" y="150" text-anchor="middle" font-family="{_MONO}" font-size="9" fill="{INK}" opacity="0.55">ASP</text>
  </g>
  <g transform="translate(232 150)" font-family="{_MONO}">
    {_field(0, "AGENT / NAME", nm)}
    {_field(1, "AGENT No.", f"#{aid}")}
    {_field(2, "COMPLETED SALES", sales)}
    {_field(3, "SECURITY RATING", f"{rating} / 5")}
    {_field(4, "SERVICES", svc)}
    {_field(5, "ENDPOINTS", ep_txt)}
  </g>

  <!-- entry stamp -->
  <g transform="translate(468 470) rotate(-11)" opacity="0.92">
    <ellipse cx="0" cy="0" rx="132" ry="86" fill="none" stroke="{col}" stroke-width="4"/>
    <ellipse cx="0" cy="0" rx="120" ry="75" fill="none" stroke="{col}" stroke-width="1.25" opacity="0.7"/>
    <text x="0" y="-40" text-anchor="middle" font-family="{_MONO}" font-size="11" letter-spacing="3" fill="{col}">KYA CONTROL</text>
    <text x="0" y="22" text-anchor="middle" font-family="{_SERIF}" font-weight="700" font-size="58" letter-spacing="2" fill="{col}">{word}</text>
    <text x="0" y="52" text-anchor="middle" font-family="{_MONO}" font-size="11" letter-spacing="2" fill="{col}">{_esc(issued or '')}</text>
  </g>

  <!-- pronouncement -->
  <g transform="translate(56 384)">
    <text x="0" y="0" font-family="{_MONO}" font-size="10" letter-spacing="2" fill="{INK}" opacity="0.55">VERDICT OF THE WATCH</text>
    {pron_svg}
  </g>

  <!-- signing / validity -->
  <g transform="translate(56 {H-176})" font-family="{_MONO}" font-size="11" fill="{INK}">
    <line x1="0" y1="-18" x2="{W-112}" y2="-18" stroke="{INK}" stroke-width="0.75" opacity="0.5"/>
    <text x="0" y="6" opacity="0.7">ISSUED  {_esc(issued or '—')}</text>
    <text x="220" y="6" opacity="0.7">EXPIRES  {_esc(expires or '—')}</text>
    <text x="0" y="26" opacity="0.7">ED25519 · {pk}…  ·  re-verify at /verify?agentId={aid}</text>
  </g>

  <!-- machine-readable zone -->
  <g transform="translate(56 {H-96})">
    <rect x="-8" y="-26" width="{W-96}" height="76" fill="{INK}" opacity="0.04"/>
    <text x="0" y="0" font-family="{_MONO}" font-size="18" letter-spacing="2" fill="{INK}">{mrz1}</text>
    <text x="0" y="30" font-family="{_MONO}" font-size="18" letter-spacing="2" fill="{INK}">{mrz2}</text>
  </g>
</svg>"""


def _field(row: int, label: str, value: str) -> str:
    # value is already escaped by the caller; label is a trusted literal. Escaping
    # here too would double-encode (a name's '<' would render as literal "&lt;").
    y = row * 30
    return (f'<text x="0" y="{y}" font-size="9.5" letter-spacing="1.5" fill="{INK}" opacity="0.5">{label}</text>'
            f'<text x="0" y="{y+16}" font-size="15" fill="{INK}">{value}</text>')
