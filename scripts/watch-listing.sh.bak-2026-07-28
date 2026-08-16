#!/bin/bash
# KYA listing watcher — polls ASP #5290's approval status and shouts on ANY change.
#
# Why this exists: OKX's documented 24h review SLA is not being honoured (#5290 has sat
# at "Listing under review" since Jul 13 10:47 UTC). The listing going live is a HARD
# eligibility gate for the OKX.AI Genesis hackathon (deadline Jul 17 23:59 UTC) — an
# unapproved listing makes the submission invalid. Nobody emails the wallet address we
# actually watch, so we poll the chain-of-record ourselves instead of trusting a notice.
#
# Install:  crontab -e  ->  */10 * * * * /Users/morkeeth/CODE/okx-agent-oracle/scripts/watch-listing.sh
# Manual:   bash scripts/watch-listing.sh --now   (prints current state, no alert)

set -uo pipefail

AGENT_ID="5290"
BIN="/Users/morkeeth/.local/bin/onchainos"
STATE="/Users/morkeeth/CODE/okx-agent-oracle/.listing-state"
FAILS="/Users/morkeeth/CODE/okx-agent-oracle/.listing-fails"
LOG="/Users/morkeeth/CODE/okx-agent-oracle/.listing-watch.log"
VAULT="/Users/morkeeth/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian LIFE/00 Dashboard/kya-listing.md"

ts() { date -u '+%Y-%m-%d %H:%M UTC'; }

# Capture stdout ONLY. Never merge stderr in: under cron there is no keychain access,
# so the CLI prints "Warning: OS keyring read failed … trying file fallback" to stderr
# and then succeeds. A 2>&1 here glues that warning to the front of the JSON, the parse
# dies, and the watcher reports a "transient" failure forever while being stone blind.
# That is exactly what happened on 2026-07-15 (27 silent failures, 4.5h). An interactive
# shell CAN read the keyring, so the bug is invisible from the terminal — the only way to
# catch it was to read what cron actually logged.
ERRF="$(mktemp)"
raw="$("$BIN" agent get-agents --agent-ids "$AGENT_ID" 2>"$ERRF")"
err="$(cat "$ERRF" 2>/dev/null)"; rm -f "$ERRF"

# Pull the CLI's own resolved labels; never hand-map the status integers.
read -r approval status <<<"$(printf '%s' "$raw" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    a = (d.get('data') or [{}])[0]
    print((a.get('approvalLabel') or 'UNKNOWN').replace(' ', '~'),
          (a.get('statusLabel') or 'UNKNOWN').replace(' ', '~'))
except Exception:
    print('CLI_ERROR CLI_ERROR')
" 2>/dev/null)"

approval="${approval//\~/ }"
status="${status//\~/ }"
now="$approval | $status"

if [ "${1:-}" = "--now" ]; then
    echo "[$(ts)] #$AGENT_ID -> $now"
    exit 0
fi

# A transient CLI/network blip must not fire a false "it changed!" alert.
# But a PERSISTENT failure is a dead watcher pretending to be a calm one: on
# 2026-07-15 this logged "transient?" 27 times in a row over 4.5h while the
# monitor was in fact completely broken. So: log the real error, and escalate
# to a loud alert once the failures stop being plausibly transient.
if [ "$approval" = "CLI_ERROR" ] || [ "$approval" = "UNKNOWN" ]; then
    echo "[$(ts)] poll FAILED. err: $(printf '%s' "$err" | tr '\n' ' ' | head -c 160) | raw: $(printf '%s' "$raw" | tr '\n' ' ' | head -c 160)" >>"$LOG"
    fails=$(( $(cat "$FAILS" 2>/dev/null || echo 0) + 1 ))
    echo "$fails" >"$FAILS"
    if [ "$fails" -eq 3 ] || [ $((fails % 18)) -eq 0 ]; then
        osascript -e "display notification \"$fails consecutive failed polls — the listing watcher is BLIND. Check .listing-watch.log\" with title \"KYA watcher DOWN\" sound name \"Basso\"" 2>/dev/null
    fi
    exit 0
fi
echo 0 >"$FAILS"

prev=""
[ -f "$STATE" ] && prev="$(cat "$STATE")"

if [ "$now" != "$prev" ]; then
    printf '%s' "$now" >"$STATE"
    echo "[$(ts)] CHANGED: '$prev' -> '$now'" >>"$LOG"

    case "$approval" in
        *"under review"*) headline="still under review (no change in kind)"; sound="Submarine" ;;
        *"rejected"*)     headline="🚨 REJECTED — read the remark, fix, re-activate"; sound="Basso" ;;
        *"Listed"*)       headline="✅ LIVE — you are ELIGIBLE. Post X + submit the form."; sound="Glass" ;;
        *)                headline="status moved: $approval"; sound="Glass" ;;
    esac

    osascript -e "display notification \"#$AGENT_ID: $now\" with title \"KYA listing: $headline\" sound name \"$sound\"" 2>/dev/null

    cat >"$VAULT" <<EOF
---
date: $(date -u '+%Y-%m-%d')
tags: [kya, okx, listing, live]
status: live
source: claude-code
---

# KYA listing #$AGENT_ID — live status

> Auto-written by \`scripts/watch-listing.sh\` (cron, every 10 min). Do not hand-edit.

**Approval:** $approval
**Status:** $status
**Last change seen:** $(ts)

**Deadline:** Jul 17, 23:59 UTC. An unapproved / non-live listing makes the submission
**invalid** (official rules Step 2). Registered Jul 13 10:47 UTC.

**Do NOT re-activate or edit the listing** — it is already submitted; re-activating an
under-review listing is a no-op and risks losing its place.

## Recent transitions
\`\`\`
$(tail -8 "$LOG" 2>/dev/null)
\`\`\`
EOF
else
    echo "[$(ts)] no change: $now" >>"$LOG"
fi
