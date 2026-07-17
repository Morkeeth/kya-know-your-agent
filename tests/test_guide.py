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
