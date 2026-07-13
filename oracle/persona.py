"""
KYA's voice — "Know Your Agent".

The persona is a wolf-hunter / gatekeeper: it decides nothing, it only *announces*
the verdict the engine already computed (the Octocat rule — character in the
packaging, rigour in the payload). So the signed verdict is untouched; this just
adds a human-memorable `pronouncement` headline for the card, the CLI, and X.

Voice: deadpan, confident, bites only on a BLOCK — and the bite always rides on
the receipt (the real reasons stay attached).
"""
from __future__ import annotations

TAGLINE = "Know Your Agent — check who you're dealing with, before you deal."


def _reason_keys(verdict) -> set[str]:
    return {s.get("key") for s in (verdict.signals or [])}


def pronounce(verdict) -> str:
    """One headline line in KYA's voice, chosen from what actually drove the verdict."""
    v = verdict.verdict
    keys = _reason_keys(verdict)
    ev = verdict.evidence or {}

    if v == "BLOCK":
        if ev.get("isAsp") is False:
            return "No one lives here. This isn't a service you can transact with — turn back."
        if "test_account" in keys:
            return "A costume, not a service. Turned away."
        if "liveness" in keys and ev.get("endpoints"):
            return "It knocks, but nothing answers. The house is empty — turned away."
        return "My, what big teeth you have. This one's a wolf — turned away."

    if v == "CAUTION":
        if "sales" in keys and ev.get("sales") == 0:
            return "Dressed for the part, but no one has ever come to eat. Mind the teeth."
        return "Only a soul or two have crossed this threshold. Step carefully."

    # SAFE
    if (ev.get("sales") or 0) >= 100:
        return "A well-worn path, and no wolves on it. Come in."
    return "Cleared — this one is who it claims to be. Come in."


def rank(verdict) -> str:
    """A short badge word for the seal/card."""
    return {"SAFE": "CLEARED", "CAUTION": "WARY", "BLOCK": "WOLF"}.get(verdict.verdict, "—")
