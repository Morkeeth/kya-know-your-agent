#!/usr/bin/env python3
"""Render KYA passports for real live agents into a single HTML page and print
its path (open it in a browser to react to the design).

    python scripts/preview.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle import fetch_agent, probe_endpoints, score_agent  # noqa: E402
from oracle.persona import pronounce  # noqa: E402
from oracle.seal import render_passport, render_stamp  # noqa: E402
from oracle.signing import Signer  # noqa: E402

SAMPLES = [
    ("2118", "SAFE — a proven provider"),
    ("3733", "CAUTION — barely proven"),
    ("3820", "BLOCK — listed but its endpoint is dead"),
    ("1771", "BLOCK — not even a real service"),
]


def _date(ts: int) -> str:
    return time.strftime("%d %b %Y", time.gmtime(ts)).upper()


def main() -> int:
    signer = Signer()
    cards = []
    for aid, caption in SAMPLES:
        info, services = fetch_agent(aid)
        v = score_agent(info, services, probe_endpoints(services), agent_id=aid)
        env = signer.sign_digest(v.digest)
        passport = render_passport(
            v.verdict, v.name, v.agent_id, evidence=v.evidence,
            pronouncement=pronounce(v),
            issued=_date(env["signed_at"]), expires=_date(env["expires_at"]),
            digest=v.digest, pubkey=env["pubkey"],
        )
        stamp = render_stamp(v.verdict, v.agent_id, _date(env["signed_at"]))
        cards.append((caption, passport, stamp))

    blocks = "\n".join(
        f'<figure><figcaption>{c}</figcaption><div class="p">{p}</div>'
        f'<div class="s">{s}</div></figure>'
        for c, p, s in cards
    )
    html = f"""<!doctype html><meta charset="utf-8">
<title>KYA passports</title>
<style>
  body{{margin:0;background:#e9e9e6;font-family:-apple-system,sans-serif;padding:40px}}
  h1{{font:600 20px/1 -apple-system;letter-spacing:2px}}
  .grid{{display:flex;flex-wrap:wrap;gap:40px;align-items:flex-start}}
  figure{{margin:0}}
  figcaption{{font:600 13px/1.4 ui-monospace,monospace;margin-bottom:12px;color:#333}}
  .p svg{{box-shadow:0 12px 40px rgba(0,0,0,.25)}}
  .s{{margin-top:16px}}
</style>
<h1>KYA · KNOW YOUR AGENT — passport + stamp</h1>
<div class="grid">{blocks}</div>"""

    out = Path(__file__).resolve().parent.parent / "preview.html"
    out.write_text(html)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
