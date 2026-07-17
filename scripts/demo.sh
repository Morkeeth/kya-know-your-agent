#!/usr/bin/env bash
# KYA - the full demo, narrated. One reproducible script.
#
# TWO fenced sections, never blurred (demo integrity):
#   [LIVE]        real GET /verify responses from the DEPLOYED service, on REAL
#                 OKX.AI marketplace agents. Nothing local, nothing mocked.
#   [CONTROLLED]  the real engine / scanner / probe / store, driven against a
#                 clearly-labelled TEST agent - because no real agent will flip a
#                 dead endpoint or poison a tool description on cue. The DETECTION
#                 is 100% real; only the subject is a fixture.
#
# The [LIVE] section SELF-VERIFIES: if the deployed service stops returning the
# headline verdict for any agent, the script exits non-zero. "Green" therefore
# means the demo's claims actually held against production at run time.
#
#   bash scripts/demo.sh              # against the live deployed URL
#   KYA_URL=http://localhost:8000 bash scripts/demo.sh   # against a local server
set -euo pipefail
cd "$(dirname "$0")/.."

KYA_URL="${KYA_URL:-https://kya-production-f846.up.railway.app}"
PY="${PY:-./.venv/bin/python}"
[ -x "$PY" ] || PY="python3"
export ONCHAINOS_BIN="${ONCHAINOS_BIN:-$HOME/.local/bin/onchainos}"
FAIL=0

# One hue at three luminances — the same ramp as oracle/watchtower.py and demo_caller.py.
# This script was the last surface still shouting in the old voice (block banners, emoji
# status icons, ═ rules) while the rest of the product had been quieted down.
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  LIME=$'\033[38;2;188;232;47m'; DIM=$'\033[38;2;110;138;52m'
  GREY=$'\033[38;2;138;138;142m'; FAINT=$'\033[38;2;90;90;94m'
  INK=$'\033[38;2;255;255;255m'; B=$'\033[1m'; O=$'\033[0m'
else
  LIME=""; DIM=""; GREY=""; FAINT=""; INK=""; B=""; O=""
fi
export LIME DIM GREY FAINT INK B O

rule() { printf "%s" "$FAINT"; printf '─%.0s' {1..66}; printf "%s\n" "$O"; }
head2() { echo; echo "  ${FAINT}$1${O}"; }

# live_verify <agentId> <expected-verdict> <label>
# Curls the DEPLOYED service, pretty-prints the real response, and asserts the
# headline verdict. Any divergence flips FAIL so the script ends red.
live_verify() {
  local id="$1" want="$2" label="$3"
  local body=""
  # Retry transient empties/5xx (e.g. a cold instance) so a single network blip during
  # recording can't red the demo. Real responses only; no fabrication.
  for attempt in 1 2 3 4; do
    body=$(curl -s --max-time 30 "$KYA_URL/verify?agentId=$id")
    printf '%s' "$body" | "$PY" -c 'import sys,json;sys.exit(0 if "verdict" in (json.load(sys.stdin) or {}) else 1)' 2>/dev/null && break
    [ "$attempt" -lt 4 ] && sleep 2
  done
  printf '%s' "$body" | "$PY" -c '
import sys, json, unicodedata, os
# No nested quotes inside the f-strings: this python lives inside a single-quoted bash
# block, so an escaped double-quote arrives as a literal backslash and kills the parse.
# Every value is computed first, then interpolated bare.
want, label = sys.argv[1], sys.argv[2]
L,D,G,F,I,B,O = (os.environ.get(k,"") for k in ("LIME","DIM","GREY","FAINT","INK","B","O"))
TONE = {"SAFE": L, "CAUTION": D, "BLOCK": G}
def w(s): return sum(2 if unicodedata.east_asian_width(c) in ("W","F") else 1 for c in s)
def pad(s,n): return s + " " * max(0, n - w(s))
try:
    d = json.load(sys.stdin)
except Exception as e:
    print(f"  {G}no JSON from the deployed service: {e}{O}"); sys.exit(3)
if "verdict" not in d:
    detail = d.get("detail", d)
    print(f"  {G}{detail}{O}"); sys.exit(3)
got = d["verdict"]
t = TONE.get(got, G)
name = (d.get("name") or "(no ASP record)")[:26]
aid = str(d.get("agent_id", ""))
head = pad(name + " #" + aid, 40)
ceil = float(d.get("max_safe_usd") or 0)
why = (d.get("reasons") or ["-"])[0]
# strip emoji AND the variation selector U+FE0F that trails them, or a stray
# accent glyph survives the removal and prints as a floating tick.
for ch in ("\u2705","\u26d4","\u26a0","\ufe0f","\U0001f504"): why = why.replace(ch,"")
why = why.strip()
why = " ".join(why.split()).split("(~")[0].split(" \u2014 ")[0].split("(assumes")[0]
why = why[:60].rstrip(" ;,.")
print()
print(f"  {I}{head}{O}{t}{pad(got,9)}{O}{F}ceiling {O}{t}${ceil:,.2f}{O}")
print(f"    {F}{why}{O}")
print(f"    {F}{label}{O}")
if got != want:
    print(f"    {G}diverged - expected {want}{O}"); sys.exit(1)
' "$want" "$label" || FAIL=1
}

echo
echo "  ${LIME}${B}KYA${O}  ${FAINT}know your agent · the trust layer for the agent economy${O}"
rule
curl -s --max-time 15 "$KYA_URL/health" | "$PY" -c 'import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get("ok") else 2)' \
  || { echo "  ${GREY}service unhealthy - aborting${O}"; exit 2; }

# ══ [LIVE] the clean spread - real deployed responses, real agents ═══════════
head2 "[LIVE] · the spread · real deployed responses, real agents"
live_verify 2118 SAFE    "proven provider · 220 settled sales"
live_verify 3345 SAFE    "earned a real ceiling · 550 sales, 5.50 USDT settled"
live_verify 3733 CAUTION "barely proven · one sale"
live_verify 3369 CAUTION "live but unproven · nobody has used it"
live_verify 3820 BLOCK   "listed, online, rated · endpoints dead, zero sales"

# ══ [LIVE] KYA in the payment loop - the caller REFUSES on BLOCK ══════════════
head2 "[LIVE] · in the loop · a buyer agent prices its payments"

KYA_URL="$KYA_URL" "$PY" scripts/demo_caller.py || FAIL=1

# ══ [CONTROLLED] the detectors firing - real engine, labelled TEST agent ══════
head2 "[CONTROLLED] · the detectors · real engine, labelled TEST fixture"
echo "Not the deployed service and not a real agent: a controlled subject so the REAL"
echo "detector can be seen firing. Trust is a timeline - a clean agent can turn."
echo
echo "› rug-pull #1 - a patched/decaying endpoint, re-verified (BLOCK⇄SAFE transition):"
"$PY" scripts/demo_flip.py || FAIL=1
echo
echo "› rug-pull #2 - a tool description silently poisoned after approval (SAFE→BLOCK):"
"$PY" scripts/demo_poison.py || FAIL=1

# ══ live board pointer ═══════════════════════════════════════════════════════
head2 "[LIVE] · the boards"
echo "  open $KYA_URL/watchtower                  # live verdict board + crossings"
echo "  open $KYA_URL/passport?agentId=3820       # the shareable BLOCK passport"

echo
rule
if [ "$FAIL" -eq 0 ]; then
  echo "  ${LIME}DEMO GREEN${O}  ${FAINT}every [LIVE] claim held against the deployed service${O}"
else
  echo "  ${GREY}DEMO RED${O}  ${FAINT}a live claim diverged or a beat errored${O}"
fi
rule
exit "$FAIL"
