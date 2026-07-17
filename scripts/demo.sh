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


rule() { printf '─%.0s' {1..66}; echo; }

# live_verify <agentId> <expected-verdict> <label>
# Curls the DEPLOYED service, pretty-prints the real response, and asserts the
# headline verdict. Any divergence flips FAIL so the script ends red.
live_verify() {
  local id="$1" want="$2" label="$3"
  echo; rule; echo "  $label   -   GET $KYA_URL/verify?agentId=$id"; rule
  local body=""
  # Retry transient empties/5xx (e.g. a cold instance) so a single network blip
  # during recording can't red the demo. Real responses only; no fabrication.
  for attempt in 1 2 3 4; do
    body=$(curl -s --max-time 30 "$KYA_URL/verify?agentId=$id")
    printf '%s' "$body" | "$PY" -c 'import sys,json;sys.exit(0 if "verdict" in (json.load(sys.stdin) or {}) else 1)' 2>/dev/null && break
    [ "$attempt" -lt 4 ] && sleep 2
  done
  printf '%s' "$body" | "$PY" -c '
import sys, json
want = sys.argv[1]
try:
    d = json.load(sys.stdin)
except Exception as e:
    print("   ERROR: no JSON from deployed service:", e); sys.exit(3)
if "verdict" not in d:
    print("   ERROR:", d.get("detail", d)); sys.exit(3)
got = d["verdict"]
print("   NAME     " + (d.get("name") or "(no ASP record)"))
print("   VERDICT  {}   score {}/100   confidence {}%".format(got, d["score"], d["confidence"]))
print("   MAX SAFE ${}   <- priced trust: safe single-tx amount, earned from settled volume".format(d.get("max_safe_usd", 0)))
for r in d.get("reasons", [])[:4]:
    print("           ", r)
sig = d.get("signature") or {}
if sig.get("signature"):
    print("   SIGNED   ed25519 " + sig["signature"][:24] + "…  (verify offline against /pubkey)")
if got != want:
    print("   ✗ EXPECTED {} - deployed service diverged".format(want)); sys.exit(1)
print("   ✓ live verdict matches the demo claim ({})".format(want))
' "$want" || FAIL=1
}

echo
echo "██ KYA - Know Your Agent ██   the trust layer for the agent economy"
echo "Before your agent pays or hires a counterparty, it calls KYA and refuses on BLOCK."
echo "Deployed service under test: $KYA_URL"

# ── health gate ──────────────────────────────────────────────────────────────
echo; echo "› deployed service health:"
curl -s --max-time 15 "$KYA_URL/health" | "$PY" -c 'import sys,json; d=json.load(sys.stdin); print("  ", d); sys.exit(0 if d.get("ok") else 2)' || { echo "  service unhealthy - aborting"; exit 2; }

# ══ [LIVE] the clean spread - real deployed responses, real agents ═══════════
echo; echo "══════════ [LIVE]  THE SPREAD - KYA discriminates on real agents ══════════"
live_verify 2118 SAFE    "✅ Otto AI - a proven provider (220 settled sales)"
live_verify 3345 SAFE    "✅ Eat This? - 550 sales, 5.50 USDT settled, endpoint serving -> ceiling \$16.50"
live_verify 3733 CAUTION "⚠️  Scope - barely proven (one sale)"
live_verify 3369 CAUTION "⚠️  WhalePulse - live but UNPROVEN (nobody has used it)"
live_verify 3820 BLOCK   "⛔ Sentiment Oracle - listed & online, but endpoints 502 + zero sales"

# ══ [LIVE] KYA in the payment loop - the caller REFUSES on BLOCK ══════════════
echo; echo "══════════ [LIVE]  KYA IN THE LOOP - a buyer agent gates its payments ══════════"
echo "(reference integration: fetch verdict → verify signature against pinned key → refuse on BLOCK)"
KYA_URL="$KYA_URL" "$PY" scripts/demo_caller.py 2118 3345 3820 || FAIL=1

# ══ [CONTROLLED] the detectors firing - real engine, labelled TEST agent ══════
echo; echo "══════════ [CONTROLLED]  THE DETECTORS - real engine/scanner, TEST fixture ══════════"
echo "Not the deployed service and not a real agent: a controlled subject so the REAL"
echo "detector can be seen firing. Trust is a timeline - a clean agent can turn."
echo
echo "› rug-pull #1 - a patched/decaying endpoint, re-verified (BLOCK⇄SAFE transition):"
"$PY" scripts/demo_flip.py || FAIL=1
echo
echo "› rug-pull #2 - a tool description silently poisoned after approval (SAFE→BLOCK):"
"$PY" scripts/demo_poison.py || FAIL=1

# ══ live board pointer ═══════════════════════════════════════════════════════
echo; echo "══════════ [LIVE]  THE WATCHTOWER - every agent KYA has judged ══════════"
echo "  open $KYA_URL/watchtower                  # live verdict board + crossings"
echo "  open $KYA_URL/passport?agentId=3820       # the shareable BLOCK passport"

echo
rule
if [ "$FAIL" -eq 0 ]; then
  echo "  ✓ DEMO GREEN - every [LIVE] claim held against the deployed service."
else
  echo "  ✗ DEMO RED - a live claim diverged or a beat errored (see ✗ above)."
fi
rule
exit "$FAIL"
