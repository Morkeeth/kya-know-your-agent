#!/usr/bin/env python3
"""
KYA in the loop — a reference CALLER.

This is how you actually USE KYA: a buyer agent, before it pays or hires a counterparty
ASP, calls KYA, cryptographically verifies the signed verdict against a PINNED oracle key,
and prices the payment against the signed ceiling. Reputation is not advice here — it gates
the payment.

Runs against the live deployment (a real client of the real service):
    kya                 the four beats
    kya 2118 0.50       one agent, one amount
    kya 2118:0.50 3820:5

Trust model: fetch the oracle key ONCE from /pubkey and pin it. Every verdict is checked
with verify_envelope against that pinned key (a rogue oracle can't ship its own key and
self-sign SAFE), against the signed freshness window, and against a digest RECOMPUTED from
the bytes received (never the served `digest` field).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from oracle.signing import verify_envelope, digest_for_body  # noqa: E402

HOST = "https://kya-production-f846.up.railway.app"

# One hue at three luminances, exactly like the boards (oracle/watchtower.py): the verdict
# is carried by POSITION and WORD, and colour only says how much light the agent earned.
# Amber/red traffic lights were the boards' loudest vibe-code tell; the CLI does not get to
# reintroduce them. NO_COLOR / a non-tty disables all of it.
_TTY = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _c(rgb: str) -> str:
    return f"\033[38;2;{rgb}m" if _TTY else ""


LIME = _c("188;232;47")    # earned, full light
DIM = _c("110;138;52")     # unproven / held back
GREY = _c("138;138;142")   # refused, nearly out
INK = _c("255;255;255")
FAINT = _c("90;90;94")
BOLD = "\033[1m" if _TTY else ""
OFF = "\033[0m" if _TTY else ""

_TONE = {"SAFE": LIME, "CAUTION": DIM, "BLOCK": GREY}
_DTONE = {"PROCEED": LIME, "HOLD": DIM, "REFUSE": GREY}


def pin_oracle_key(host: str) -> str:
    """Fetch the oracle's Ed25519 key ONCE and pin it. In a real client this is hardcoded
    after first fetch; here we fetch live for the demo."""
    return httpx.get(f"{host}/pubkey", timeout=10).json()["pubkey"]


def ask_kya(host: str, agent_id: str) -> dict:
    return httpx.get(f"{host}/verify", params={"agentId": agent_id}, timeout=25).json()


def _dwidth(s: str) -> int:
    """Display width in terminal cells. CJK/emoji occupy TWO cells, so len() lies and every
    column right of a Chinese agent name drifts — and this marketplace is full of them
    (这个能吃吗? is one of the four demo beats)."""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def _pad(s: str, width: int) -> str:
    """Right-pad to a true display width."""
    return s + " " * max(0, width - _dwidth(s))


def _why(body: dict) -> str:
    """The headline reason, stripped to one readable clause.

    The raw reason is written for a payload, not a terminal: it carries the basis caveat
    inline and wrapped to three lines on screen, which buried the decision under its own
    footnote. The caveat is real and stays in the JSON; here it gets one line.
    """
    raw = (body.get("reasons") or ["—"])[0]
    # Includes U+FE0F: ⚠️ is TWO codepoints and removing only the base leaves the
    # variation selector behind as a floating mark.
    for ch in ("✅", "⛔", "⚠", "\ufe0f", "🔄"):
        raw = raw.replace(ch, "")
    raw = raw.split("(~")[0].split(" — ")[0].split("(assumes")[0]
    raw = " ".join(raw.split())
    return raw[:64].rstrip(" ;,.")


# The checks KYA runs, in the order it runs them. Each maps to the signal keys that can
# speak for it. A security scanner is a CONTRADICTION detector: silent = it ran and found
# nothing (the scanners run on every call — verified live). A negative signal in a group
# flags it. This is the "scan x, y, z and give a rating" surface, printed honestly.
_CHECKS = [
    ("endpoint liveness",   ("liveness", "uptime", "x402")),
    ("malicious-host scan",  ("malicious",)),
    ("prompt-injection scan", ("content", "tool_poisoning")),
    ("endpoint safety",      ("ssrf",)),
    ("identity binding",     ("domain_binding", "payto")),
    ("domain age",           ("domain_age",)),
    ("reviewer integrity",   ("self_review", "review_ring", "review_concentration")),
    ("operator / sybil",     ("owner_fleet", "owner_fleet_info")),
    ("settled reputation",   ("sales", "reputation", "security_rating", "review")),
]


def audit(host: str, pinned_key: str, agent_id: str) -> None:
    """Print the full audit: every check KYA ran, its result, then the signed verdict."""
    body = ask_kya(host, agent_id)
    sigs = body.get("signals") or []
    by_key = {}
    for s in sigs:
        by_key.setdefault(s["key"], s)

    digest = digest_for_body(body)
    signed = verify_envelope(digest, body.get("signature") or {}, pinned_key) \
        and digest == body.get("digest")

    v = body["verdict"]
    name = (body.get("name") or f"#{agent_id}")[:30]
    t = _TONE.get(v, GREY)

    print()
    print(f"  {LIME}{BOLD}KYA{OFF}  {FAINT}security audit{OFF}"
          f"{FAINT}{'#' + str(agent_id):>48}{OFF}")
    print(f"  {INK}{name}{OFF}")
    print(f"  {FAINT}{'─' * 66}{OFF}")

    for label, keys in _CHECKS:
        hit = [by_key[k] for k in keys if k in by_key]
        bad = [s for s in hit if s["severity"] in ("warn", "critical")]
        if bad:
            mark, tone, note = "FLAG", (GREY if any(s["severity"] == "critical" for s in bad) else DIM), \
                _clip(bad[0]["reason"])
        elif hit:
            mark, tone, note = "PASS", LIME, _clip(hit[0]["reason"])
        else:
            mark, tone, note = "CLEAN", DIM, "scanned, nothing found"
        print(f"    {FAINT}{_pad(label, 22)}{OFF}{tone}{_pad(mark, 7)}{OFF}{FAINT}{note}{OFF}")

    print(f"  {FAINT}{'─' * 66}{OFF}")
    ceil = f"${float(body.get('max_safe_usd') or 0):,.2f}"
    print(f"  {t}{BOLD}{_pad(v, 8)}{OFF}{FAINT}score {OFF}{t}{_pad(str(body.get('score', 0)), 6)}{OFF}"
          f"{FAINT}ceiling {OFF}{t}{_pad(ceil, 9)}{OFF}"
          f"{FAINT}signed {OFF}{LIME if signed else GREY}{'yes' if signed else 'NO'}{OFF}")
    print()


def _clip(reason: str) -> str:
    for ch in ("✅", "⛔", "⚠", "️", "🔄"):
        reason = reason.replace(ch, "")
    reason = " ".join(reason.split()).split("(~")[0].split(" — ")[0].split("(assumes")[0]
    return reason[:40].rstrip(" ;,.")


def gate_transaction(host: str, pinned_key: str, agent_id: str, amount_usd: float,
                     cache: dict) -> str:
    """Gate ONE payment of `amount_usd` on the signed verdict AND the signed ceiling.

    The ceiling is the product. A rating says "this one is good"; `max_safe_usd` says *how
    much* good — the largest single payment this counterparty has EARNED from settled
    volume. So the decision is a function of (verdict, amount), never the verdict alone.

    Returns PROCEED / HOLD / REFUSE.
    """
    body = cache.get(agent_id) or ask_kya(host, agent_id)
    cache[agent_id] = body
    verdict, env = body["verdict"], body["signature"]
    ceiling = float(body.get("max_safe_usd") or 0.0)

    # RECOMPUTE the digest from the bytes we received — never trust body["digest"]. The
    # signature covers the digest, not the body, so replaying the original digest+signature
    # past a naive check would launder a rewritten evidence.cluster.
    digest = digest_for_body(body)
    ok = verify_envelope(digest, env, pinned_key) and digest == body.get("digest")

    if not ok:
        print(f"    {GREY}pay ${amount_usd:<6,.2f} REFUSE{OFF}   signature did not verify")
        return "REFUSE"

    if verdict == "BLOCK":
        d, note = "REFUSE", "BLOCK refuses at any price"
    elif amount_usd > ceiling:
        d, note = "HOLD", f"${amount_usd:,.2f} over a ${ceiling:,.2f} ceiling"
    elif verdict == "CAUTION":
        d, note = "HOLD", "unproven counterparty"
    else:
        d, note = "PROCEED", "within the earned ceiling"

    print(f"    {FAINT}pay{OFF} {INK}${amount_usd:<6,.2f}{OFF} "
          f"{_DTONE[d]}{BOLD}{d:<8}{OFF} {FAINT}{note}{OFF}")
    return d


# (agentId, [amounts]) — the SAME agent at two prices is the whole argument, so the two
# Otto beats sit under one header where the contrast is unmissable.
DEFAULT_BEATS = [("2118", [0.50, 5.00]), ("3345", [5.00]), ("3820", [5.00])]


def _parse(args: list[str]) -> list[tuple[str, list[float]]]:
    """`2118 0.50` or `2118:0.50 3820:5`; a bare id defaults to $5.00."""
    if len(args) == 2 and args[0].isdigit() and ":" not in args[1]:
        return [(args[0], [float(args[1])])]
    out = []
    for a in args:
        aid, _, amt = a.partition(":")
        out.append((aid, [float(amt) if amt else 5.00]))
    return out


def main() -> int:
    args = sys.argv[1:]
    key = pin_oracle_key(HOST)

    # `kya <id>` with no amount => the full security audit for that agent.
    if len(args) == 1 and args[0].isdigit():
        audit(HOST, key, args[0])
        return 0

    beats = _parse(args) if args else DEFAULT_BEATS

    print()
    print(f"  {LIME}{BOLD}KYA{OFF}  {FAINT}know your agent{OFF}"
          f"{FAINT}{'pinned ' + key[:8]:>44}…{OFF}")
    print(f"  {FAINT}{'─' * 66}{OFF}")

    tally, errors, cache = {"PROCEED": 0, "HOLD": 0, "REFUSE": 0}, 0, {}
    for aid, amounts in beats:
        try:
            body = cache.get(aid) or ask_kya(HOST, aid)
            cache[aid] = body
            name = (body.get("name") or f"#{aid}")[:26]
            v = body["verdict"]
            head = _pad(f"{name} #{aid}", 40)
            ceil = f"${float(body.get('max_safe_usd') or 0):,.2f}"
            print()
            print(f"  {INK}{head}{OFF}{_TONE.get(v, GREY)}{_pad(v, 9)}{OFF}"
                  f"{FAINT}ceiling {OFF}{_TONE.get(v, GREY)}{ceil}{OFF}")
            print(f"    {FAINT}{_why(body)}{OFF}")
            for amt in amounts:
                tally[gate_transaction(HOST, key, aid, amt, cache)] += 1
        except (httpx.HTTPError, KeyError, ValueError) as e:
            print(f"    {GREY}#{aid}: no verdict ({type(e).__name__}){OFF}")
            errors += 1

    print()
    print(f"  {FAINT}{'─' * 66}{OFF}")
    print(f"  {LIME}{tally['PROCEED']} paid{OFF} {FAINT}·{OFF} {DIM}{tally['HOLD']} held{OFF} "
          f"{FAINT}·{OFF} {GREY}{tally['REFUSE']} refused{OFF}")
    print(f"  {FAINT}two SAFE agents · the same $5.00 · opposite answers{OFF}")
    print(f"  {FAINT}because one of them earned it.{OFF}")
    print()

    # HOLD and REFUSE are the product WORKING. An ERROR is not: it means the reference
    # integration could not reach a verdict. Exit non-zero so a broken caller can never
    # report green — this script silently exited 0 while failing every call (Jul 17).
    if errors:
        print(f"  {GREY}✗ {errors} agent(s) errored — no verdict obtained.{OFF}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
