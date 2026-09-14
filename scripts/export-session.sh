#!/bin/sh
# Export the LOCAL onchainos wallet session for the KYA container. Human runs this.
#
# Writes ONE file, mode 0600, in the current directory: onchainos-session.b64. Paste its
# contents into the Railway variable ONCHAINOS_SESSION_TGZ_B64 through the dashboard
# (project kya, service kya, Variables). Not through a shell argument: a value in argv is
# visible in process listings and shell history. Delete the file afterwards.
#
# The archive holds only what a read needs: session.json, keyring.enc, machine-identity,
# wallets.json, cache.json. No audit log, no chain cache. Expiry: see sessionKeyExpireAt in
# session.json; when it lapses, log in locally again and re-export.
set -e
SRC="${ONCHAINOS_HOME:-$HOME/.onchainos}"
for f in session.json keyring.enc machine-identity wallets.json; do
  [ -f "$SRC/$f" ] || { echo "missing $SRC/$f; run: onchainos wallet login" >&2; exit 1; }
done
umask 077
tar -czf - -C "$SRC" session.json keyring.enc machine-identity wallets.json $( [ -f "$SRC/cache.json" ] && echo cache.json ) | base64 | tr -d '\n' > onchainos-session.b64
echo "wrote ./onchainos-session.b64 ($(wc -c < onchainos-session.b64) bytes, mode 0600)."
echo "next: Railway dashboard -> project kya -> Variables -> ONCHAINOS_SESSION_TGZ_B64 = (paste), then Redeploy. Then: rm onchainos-session.b64"
python3 - "$SRC/session.json" <<'PY' 2>/dev/null || true
import json,sys,datetime
d=json.load(open(sys.argv[1])); e=d.get("sessionKeyExpireAt")
try:
    e=int(e); e=e/1000 if e>1e12 else e
    print("session key expires:", datetime.datetime.fromtimestamp(e).isoformat())
except Exception: pass
PY
