#!/usr/bin/env bash
# Follows the kernel log; on USB reset/disconnect or disk I/O errors: pause rsync, alert via ntfy, log.
NTFY_TOPIC=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
PAT='usb 2-4: (reset|USB disconnect)|I/O error, dev sd[a-z]|\[sd[a-z]\] .*(tag#[0-9]+ )?(FAILED|timing out|abort)|uas_eh|device offline'
journalctl -k -f -n 0 -o short-iso | while read -r line; do
  if echo "$line" | grep -Eq "$PAT"; then
    echo "$(date -Is) $line" >> /var/log/usb-watchdog.log
    if pkill -STOP -x rsync; then act="rsync PAUSED (resume: sudo pkill -CONT -x rsync)"; else act="no rsync running"; fi
    curl -fsS -m 10 -H "Title: box USB/disk alert" -H "Priority: high" -d "$line — $act" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null || true
    sleep 30
  fi
done
