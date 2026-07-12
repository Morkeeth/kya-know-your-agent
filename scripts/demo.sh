#!/usr/bin/env bash
# 90-second demo: an agent about to transact calls The Oracle to vet the
# counterparty ASP. Watch SAFE vs CAUTION vs BLOCK on real live OKX.AI agents.
#
#   bash scripts/demo.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PY:-./.venv/bin/python}"
export ONCHAINOS_BIN="${ONCHAINOS_BIN:-$HOME/.local/bin/onchainos}"

show() {
  local id="$1" label="$2"
  echo
  echo "──────────────────────────────────────────────────────────────"
  echo "  $label  (agent #$id)"
  echo "──────────────────────────────────────────────────────────────"
  "$PY" cli.py "$id" | "$PY" -c '
import json, sys
d = json.load(sys.stdin)
print("   NAME     " + (d["name"] or "(no ASP record)"))
print("   VERDICT  {}   score {}/100   confidence {}%".format(d["verdict"], d["score"], d["confidence"]))
for r in d["reasons"][:4]:
    print("           ", r)
'
}

echo "THE ORACLE — trust verdicts for OKX.AI agents"
echo "Before your agent pays a counterparty ASP, ask the Oracle if it's safe."
show 2118 "✅ A proven provider you can trust"
show 3369 "⚠️  Live, but nobody has actually used it yet"
show 3820 "⛔ Looks listed — but its endpoint is actually down"
show 1771 "⛔ Not even a real service provider"
echo
echo "Every verdict is Ed25519-signed and time-bounded — verify it offline with /pubkey."