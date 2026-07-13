"""Seal / passport SVG tests — well-formed, escaped, allowlisted, wrapped."""
import sys
import xml.dom.minidom as minidom
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle.seal import render_stamp, render_passport, _wrap  # noqa: E402
from oracle.persona import pronounce, rank  # noqa: E402


class _V:  # minimal stand-in for a Verdict
    def __init__(self, verdict, evidence=None, signals=None):
        self.verdict, self.evidence, self.signals = verdict, evidence or {}, signals or []


def _valid_xml(svg: str) -> bool:
    minidom.parseString(svg)
    return True


def test_stamp_is_valid_svg_each_verdict():
    for v in ("SAFE", "CAUTION", "BLOCK"):
        assert _valid_xml(render_stamp(v, "2118", "13 JUL 2026"))


def test_passport_is_valid_svg():
    assert _valid_xml(render_passport("SAFE", "Otto AI", "2118",
                      evidence={"sales": 169, "securityRate": 4.75, "endpoints": {"x": "live"}},
                      pronouncement="A well-worn path.", issued="13 JUL 2026", digest="ab" * 16))


def test_malicious_name_is_escaped_not_injected():
    svg = render_passport("BLOCK", 'Wolf<script>alert(1)</script>&"x"', "1771",
                          evidence={}, pronouncement='hi "there" <b>', digest="")
    assert "<script>" not in svg           # raw tag must not survive
    assert "&lt;script&gt;" in svg          # it's escaped
    assert _valid_xml(svg)                  # still parses


def test_bad_verdict_is_allowlisted():
    # An unexpected verdict string must not render raw; it falls back to BLOCK theme.
    svg = render_stamp("SAFE'; DROP", "1", "")
    assert _valid_xml(svg)
    assert "WOLF" in svg


def test_wrap_two_lines_no_overflow():
    lines = _wrap("It knocks, but nothing answers. The house is empty — turned away.", 42, 2)
    assert len(lines) <= 2
    assert all(len(l) <= 43 for l in lines)  # +1 for the ellipsis char


def test_persona_lines_per_tier():
    assert "Come in" in pronounce(_V("SAFE", {"sales": 169}))
    assert pronounce(_V("CAUTION", {"sales": 0}, [{"key": "sales"}]))
    assert "wolf" in pronounce(_V("BLOCK", {"isAsp": False})).lower() or \
           "turn back" in pronounce(_V("BLOCK", {"isAsp": False})).lower()
    assert rank(_V("BLOCK")) == "WOLF"
