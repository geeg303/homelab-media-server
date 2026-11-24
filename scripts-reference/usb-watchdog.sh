#!/usr/bin/env bash
# usb-watchdog -- follows the kernel log; on USB resets/disconnects or disk I/O errors sends one plain-language ntfy alert
# naming the disk (diskN / mount, model, serial). Nov 24: rsync pausing removed (it was for the migration copies and would
# freeze the nightly WD backup). Watches both drive enclosures (USB 2-4, 2-3). Not 2-8 = HA Wi-Fi adapter.
NTFY_TOPIC=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
PAT='usb 2-[34]: (reset|USB disconnect)|I/O error, dev sd[a-z]|\[sd[a-z]\] .*(tag#[0-9]+ )?(FAILED|timing out|abort)|uas_eh|device offline'
name(){ local dev=$1 mp ser model
  mp=$(lsblk -no MOUNTPOINT "/dev/$dev" 2>/dev/null | grep -m1 .); ser=$(lsblk -dno SERIAL "/dev/$dev" 2>/dev/null)
  model=$(lsblk -dno MODEL "/dev/$dev" 2>/dev/null | sed 's/ *$//')
  echo "${mp:-/dev/$dev} (${model:-?}, serial ${ser:-?})"; }
journalctl -k -f -n 0 -o short-iso | while read -r line; do
  echo "$line" | grep -Eq "$PAT" || continue
  echo "$(date -Is) $line" >> /var/log/usb-watchdog.log
  dev=$(echo "$line" | grep -oE '\[sd[a-z]+\]|dev sd[a-z]+' | head -1 | grep -oE 'sd[a-z]+')
  if [ -n "$dev" ]; then what="Disk error on $(name "$dev")"; else what="USB event on a drive enclosure"; fi
  case "$line" in
    *"CRC error"*|*FAILED*) hint="Usually a USB/cable hiccup, not disk damage. One is normal; if it repeats, reseat the cable/enclosure.";;
    *"USB disconnect"*|*"device offline"*) hint="A drive dropped off. Check that the enclosure is powered and connected.";;
    *) hint="Check the dashboard; repeats mean a cable/enclosure problem.";;
  esac
  sleep 5   # let the related kernel lines arrive, then one alert per burst
  detail=$(journalctl -k --since "-10s" --no-pager -o cat | grep -E "Sense|CRC|I/O error|reset" | tail -3)
  curl -fsS -m 10 -H "Title: box: $what" -H "Priority: high" \
    -d "$hint
$(date '+%a %H:%M:%S')
${detail:-$line}" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null || true
  sleep 30
done
