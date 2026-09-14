#!/bin/sh
# Restore an onchainos wallet session from the ONCHAINOS_SESSION_TGZ_B64 variable.
#
# Why (2026-09-14): onchainos 4.6 reads OKX.AI only with a logged-in wallet session, and
# the only login it offers is a browser social login (Google / Apple / Email). A container
# cannot do that. The session directory is portable (verified: a copy of ~/.onchainos in a
# fresh HOME answers `agent service-list`), so a human logs in once on their machine,
# exports the session with scripts/export-session.sh, and pastes the value into the host's
# variables. This script only unpacks it. It never prints the value.
set -e
[ -n "${ONCHAINOS_SESSION_TGZ_B64:-}" ] || { echo "[kya] no session variable; upstream reads will fail until one is set" >&2; exit 0; }
mkdir -p "$HOME/.onchainos"
echo "$ONCHAINOS_SESSION_TGZ_B64" | base64 -d | tar -xzf - -C "$HOME/.onchainos" 2>/dev/null \
  && echo "[kya] session restored into $HOME/.onchainos" >&2 \
  || echo "[kya] session variable present but could not be unpacked" >&2
chmod 700 "$HOME/.onchainos" 2>/dev/null || true
