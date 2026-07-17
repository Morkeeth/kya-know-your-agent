"""The guide must not be able to lie about the engine.

A hand-written doc restates a threshold and then rots the moment the code moves. The guide
renders its numbers FROM oracle.engine, and these tests pin that: if someone retunes a band
or a ceiling multiplier, the doc follows or the suite fails.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle import engine  # noqa: E402
from oracle.guide import render_guide_md, render_guide_html  # noqa: E402
from oracle.watchtower import _CSS, _eye, _nav  # noqa: E402


def test_guide_quotes_the_engines_real_bands():
    md = render_guide_md()
    assert f"≥ {engine.SAFE_MIN}" in md
    assert f"{engine.CAUTION_MIN}–{engine.SAFE_MIN - 1}" in md
    assert f"< {engine.CAUTION_MIN}" in md


def test_guide_quotes_the_engines_real_ceiling_multipliers():
    md = render_guide_md()
    assert str(engine.CEIL_MULT_SAFE) in md and str(engine.CEIL_MULT_CAUTION) in md


def test_the_worked_ceiling_example_is_actually_true():
    """The guide claims 0.22 x 3.0 x 1.0 = $0.66 (Otto) and 5.50 x 3.0 x 1.0 = $16.50.
    Compute them with the real function — a worked example that doesn't work is worse
    than none, on a product whose whole thesis is 'published != true'."""
    assert engine._safe_ceiling(engine.SAFE, 100, 0.22) == 0.66
    assert engine._safe_ceiling(engine.SAFE, 100, 5.50) == 16.50
    assert engine._safe_ceiling(engine.BLOCK, 100, 999.0) == 0.0   # never pay a BLOCK


def test_both_renderings_come_from_one_source():
    """/guide and /guide.md must not be able to disagree — same blocks, two skins."""
    md = render_guide_md()
    htm = render_guide_html(nav=_nav("guide"), eye=_eye("SAFE", 30), css=_CSS)
    for heading in ("The problem", "What KYA is", "How the score works", "Known limits"):
        assert heading in md and heading in htm


def test_guide_states_its_limits():
    """A trust product that hides its own gaps is not one. These caveats are load-bearing."""
    md = render_guide_md()
    assert "floor" in md                      # the volume basis caveat
    assert "splits across wallets" in md      # fleet detection evasion
    assert "never convicts" in md             # fleet size alone is not fraud


def test_no_raw_markdown_leaks_into_the_html():
    """*italic* and **bold** must render, not print their own asterisks."""
    htm = render_guide_html(nav=_nav("guide"), eye=_eye("SAFE", 30), css=_CSS)
    body = htm.split('<div class="g-foot">')[0]
    assert "**" not in body
    assert "<i>" in body and "<b>" in body


def test_cli_columns_survive_a_chinese_agent_name():
    """The marketplace is full of CJK names (这个能吃吗? is a demo beat). len() counts them
    as one cell and the terminal renders two, so every column right of the name drifts —
    which is exactly what it did on camera-check."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import demo_caller as dc

    assert dc._dwidth("Otto AI") == 7
    assert dc._dwidth("这个能吃吗") == 10          # 5 wide chars = 10 cells
    assert dc._dwidth(dc._pad("这个能吃吗", 20)) == 20
    assert dc._dwidth(dc._pad("Otto AI", 20)) == 20


def test_cli_reason_is_one_readable_clause():
    """The raw reason carries its basis caveat inline and wrapped to three lines on screen,
    burying the decision under its own footnote. The caveat stays in the JSON; the CLI gets
    one line, and no emoji (they are on the design kill list)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import demo_caller as dc

    raw = {"reasons": ["✅ 220 sales (~0.22 USDT settled @ ≥0.001; services priced 0.001-0.15, "
                       "so this is the floor (assumes every sale was the cheapest)) — high "
                       "count offsets sub-cent pricing."]}
    why = dc._why(raw)
    assert why == "220 sales"
    assert len(why) <= 64
    for emoji in ("✅", "⛔", "⚠️"):
        assert emoji not in why


def test_cli_never_uses_traffic_light_colour():
    """Same rule as the boards: one hue at three luminances. If a red/amber ANSI escape
    appears in the CLI, the brand has split again."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import demo_caller as dc

    # Under pytest there is no tty, so _TTY is False and every tone is "" — which is the
    # correct behaviour (NO_COLOR / piped output must stay plain). So assert on the palette
    # the module declares, not on the runtime-disabled values.
    src = (Path(__file__).resolve().parent.parent / "scripts" / "demo_caller.py").read_text()
    import re as _re
    rgbs = set(_re.findall(r'_c\("(\d+;\d+;\d+)"\)', src))
    assert len(rgbs) >= 3, f"expected a 3-step ramp, found {rgbs}"
    assert "188;232;47" in rgbs                  # brand lime, same as the boards
    for banned in ("31m", "33m", "91m", "93m"):  # ansi red / yellow
        assert f"\\033[{banned}" not in src
