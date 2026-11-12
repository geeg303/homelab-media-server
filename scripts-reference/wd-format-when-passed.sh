#!/usr/bin/env bash
# wd-format-when-passed: every 10 min until done. Waits for all 5 WD long tests to finish; if every one passed, runs wd-format-batch once.
# Then starts round 3 (round3-start). Any failure → ntfy and stop WITHOUT formatting (user's approval covered "all once they pass").
set -uo pipefail
DONE=/var/lib/media-server/wd-format.done; [ -e "$DONE" ] && { systemctl disable --now wd-format-when-passed.timer; exit 0; }
exec 9>/run/wd-format.lock; flock -n 9 || exit 0
NTFY_TOPIC=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
running=0; failed=""
for s in SERIAL-WD1 7SJ8JDXW 7HJY59ZF 7HJY82BF 7HK2YR2H; do
  d=/dev/disk/by-id/ata-WDC_WD80EMAZ-00WJTA0_$s
  if [ ! -e "$d" ]; then failed="$failed $s(missing)"; continue; fi
  if smartctl -d sat -c "$d" | grep -q "Self-test routine in progress"; then running=$((running+1)); continue; fi
  first=$(smartctl -d sat -l selftest "$d" | grep -E '^# ?1 ')
  echo "$first" | grep -q "Extended offline" && echo "$first" | grep -q "Completed without error" || failed="$failed $s"
done
[ "$running" -gt 0 ] && [ -z "$failed" ] && exit 0          # still testing
if [ -n "$failed" ]; then
  echo "$(date -Is) not formatting: failed/missing:$failed" >> /var/log/migrate/format-wd.log
  curl -fsS -m 10 -H "Title: box: WD self-test problem" -H "Priority: high" -d "Long test failed or drive missing:$failed. NOTHING was formatted; waiting for user." "https://ntfy.sh/$NTFY_TOPIC" >/dev/null || true
  touch "$DONE.blocked"; systemctl disable --now wd-format-when-passed.timer; exit 0
fi
if /usr/local/sbin/wd-format-batch; then
  # user Nov 11 22:00: "Once the format is complete proceed with round 3"
  systemd-run --unit=round3-start --collect /usr/local/sbin/round3-start || true
fi
systemctl disable --now wd-format-when-passed.timer
