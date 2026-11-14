#!/usr/bin/env bash
# set-vnc-password -- changes the PrismCast noVNC password (the browser at :6080). Run: ssh -t mss sudo set-vnc-password
# The password is typed at a hidden prompt, never on a command line, and only stored in livetv.env (root 600).
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
E=/opt/media/stacks/livetv/livetv.env
read -rsp "New noVNC password (6-8 characters; VNC only uses the first 8): " p1; echo
read -rsp "Type it again: " p2; echo
[ "$p1" = "$p2" ] || { echo "Passwords don't match, nothing changed."; exit 1; }
[ ${#p1} -ge 6 ] || { echo "Too short (min 6), nothing changed."; exit 1; }
case "$p1" in *[[:space:]]*|*=*|*\"*|*\'*|*\\*) echo "Please avoid spaces, = and quote characters, nothing changed."; exit 1;; esac
[ ${#p1} -le 8 ] || echo "Note: VNC only uses the first 8 characters."
cp -a "$E" "$E.bak-$(date +%Y%m%d-%H%M)"
( umask 077; grep -v '^NOVNC_PASSWORD=' "$E" > "$E.new" || true; printf 'NOVNC_PASSWORD=%s\n' "$p1" >> "$E.new" )
chmod 600 "$E.new"; mv "$E.new" "$E"
cd /opt/media/stacks/livetv && docker compose up -d prismcast >/dev/null 2>&1
for i in $(seq 1 30); do curl -fs -o /dev/null http://127.0.0.1:6080/vnc.html && break; sleep 2; done
curl -fs -o /dev/null http://127.0.0.1:6080/vnc.html && echo "Saved. PrismCast restarted; use the new password at http://192.0.2.242:6080/vnc.html" || echo "Saved, but noVNC isn't answering yet; check: docker logs prismcast"
find /opt/media/stacks/livetv -maxdepth 1 -name 'livetv.env.bak-*' -mmin +10 -delete
