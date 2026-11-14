#!/usr/bin/env bash
# kuma-maint: silence Uptime Kuma alerts around PLANNED work. `kuma-maint on 30m` (always with an expiry), `kuma-maint off`.
# kuma-maint-check.timer turns it off when the expiry passes (survives reboots: expiry kept in a file).
set -uo pipefail
U=/var/lib/media-server/kuma-maint-until; SH=/usr/local/share/media-server
run(){ for i in $(seq 1 20); do curl -fs -o /dev/null -m 3 http://127.0.0.1:3001/ && break; sleep 6; done
       docker cp $SH/kuma_planned.js uptime-kuma:/app/kuma_planned.js >/dev/null && docker exec -e ACTION="$1" -w /app uptime-kuma node kuma_planned.js; local rc=$?
       docker exec uptime-kuma rm -f /app/kuma_planned.js; return $rc; }
case "${1:-status}" in
  on)  d=${2:-30m}; d=${d/m/ min}; d=${d/h/ hour}; until=$(date -d "now + $d" +%s 2>/dev/null || date -d "now + 30 min" +%s); echo "$until" > $U; run on && echo "until $(date -d @$until '+%a %H:%M')";;
  off) rm -f $U; run off;;
  check) [ -f $U ] || exit 0; [ "$(date +%s)" -ge "$(cat $U)" ] && { rm -f $U; run off; };;
  setup|status) run "$1";;
  *) echo "usage: kuma-maint on [30m|2h] | off | status"; exit 1;;
esac
