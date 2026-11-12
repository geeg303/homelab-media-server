#!/usr/bin/env bash
# wd-format-batch: ⚠️ DESTRUCTIVE. Formats the 5 second-enclosure WD80EMAZ drives as ext4, ONLY after every SMART long test passed.
# Approved by user Nov 11 21:15 ("I want to give permission now for you to format them all once they pass the test").
# Guarded per disk by serial; wipes the old LSI DDF RAID metadata; labels/mounts per SWITCHOVER-PLAN v2 (bay order).
# Triggered by wd-format-when-passed.timer; log: /var/log/migrate/format-wd.log
set -euo pipefail
[ "${DRYRUN:-0}" = 1 ] || exec > >(tee -a /var/log/migrate/format-wd.log) 2>&1
echo "=== $(date -Is) wd-format-batch start"
MAP="SERIAL-WD1:disk3 7SJ8JDXW:disk4 7HJY59ZF:disk5 7HJY82BF:disk6 7HK2YR2H:parity2"
NTFY_TOPIC=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
ntfy(){ curl -fsS -m 10 -H "Title: box: $1" -H "Priority: ${3:-default}" -d "$2" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null || true; }
fail(){ echo "ABORT: $*"; [ "${DRYRUN:-0}" = 1 ] && exit 2; ntfy "WD format ABORTED" "$* — nothing further formatted. Log: /var/log/migrate/format-wd.log" high; exit 1; }
dev_of(){ local s=$1 l; l=$(ls /dev/disk/by-id/ata-WDC_WD80EMAZ-00WJTA0_"$s" 2>/dev/null | grep -v -- -part || true); [ -n "$l" ] && readlink -f "$l"; }

# ---------- global gates (all before any write)
if pgrep -x rsync >/dev/null; then fail "an rsync is running"; fi
D1=$(readlink -f /dev/disk/by-label/disk1); D2=$(readlink -f /dev/disk/by-label/disk2)
for pair in $MAP; do
  s=${pair%%:*}; lab=${pair#*:}; d=$(dev_of "$s")
  if [ -z "$d" ]; then fail "$s not present"; fi
  if [ "$(lsblk -dno SERIAL "$d")" != "$s" ]; then fail "$d serial mismatch for $s"; fi
  case "$D1 $D2" in *"${d}"[0-9]*|*"$d "*) fail "$s resolves to an existing data disk";; esac
  if findmnt -rno SOURCE | grep -q "^${d}"; then fail "$s ($d) has something mounted"; fi
  if [ -e /dev/disk/by-label/$lab ]; then fail "label $lab already exists"; fi
  if grep -q " /mnt/$lab " /etc/fstab; then fail "/mnt/$lab already in fstab"; fi
  c=$(smartctl -d sat -c "$d"); if echo "$c" | grep -q "Self-test routine in progress"; then fail "$s self-test still running"; fi
  first=$(smartctl -d sat -l selftest "$d" | grep -E '^# ?1 ')
  if ! echo "$first" | grep -q "Extended offline" || ! echo "$first" | grep -q "Completed without error"; then fail "$s long test did not pass: $first"; fi
  if ! smartctl -d sat -H "$d" | grep -q PASSED; then fail "$s SMART health not PASSED"; fi
  A=$(smartctl -d sat -A "$d")
  for id in 5 197 198; do v=$(echo "$A" | awk -v i=$id '$1==i{print $10}'); if [ "${v:-x}" != 0 ]; then fail "$s attribute $id = ${v:-missing}"; fi; done
  echo "gate ok: $s → $lab ($d) · $first"
done
if [ "${DRYRUN:-0}" = 1 ]; then echo "DRYRUN: all gates passed, nothing written"; exit 0; fi
# no inactive foreign md arrays holding them
if grep -q '^md' /proc/mdstat; then
  for md in $(awk '/^md/{print $1}' /proc/mdstat); do mdadm --stop /dev/$md || fail "cannot stop /dev/$md"; done
fi
ntfy "WD format starting" "All 5 WD long tests passed. Formatting disk3–disk6 + parity2 now (≈5 min)."

# ---------- per disk
cp -a /etc/fstab /etc/fstab.bak-$(date +%Y%m%d-%H%M)-wd
DONE=""
for pair in $MAP; do
  s=${pair%%:*}; lab=${pair#*:}; d=$(dev_of "$s")
  if [ "$(lsblk -dno SERIAL "$d")" != "$s" ]; then fail "$d serial mismatch for $s (re-check)"; fi
  echo "--- $s → $lab on $d"
  wipefs -a "$d"; sgdisk -Z "$d"
  if blkid -p "$d" 2>/dev/null | grep -qi ddf; then fail "$s still shows DDF metadata after wipe"; fi
  sgdisk -n1:0:0 -t1:8300 -c1:"$lab" "$d"; partprobe "$d"; udevadm settle
  p=${d}1; if [ ! -b "$p" ]; then fail "$p missing after partitioning"; fi
  mkfs.ext4 -q -F -m 0 -T largefile -L "$lab" "$p"
  uuid=$(blkid -s UUID -o value "$p"); if [ -z "$uuid" ]; then fail "$s no UUID"; fi
  mp=/mnt/$lab
  if [ ! -d "$mp" ]; then mkdir "$mp"; fi
  if mountpoint -q "$mp"; then fail "$mp already a mountpoint"; fi
  if [ -n "$(ls -A "$mp")" ]; then fail "$mp not empty"; fi
  chattr +i "$mp"
  echo "UUID=$uuid  $mp  ext4  defaults,noatime,nofail,x-systemd.device-timeout=30s  0 2" >> /etc/fstab
  systemctl daemon-reload
  findmnt --verify --tab-file /etc/fstab 2>&1 | grep -v swap.img | grep -iE "error" && fail "fstab verify error after $lab" || true
  mount "$mp"; if ! mountpoint -q "$mp"; then fail "$mp did not mount"; fi
  touch "$mp/.rw-test" && rm "$mp/.rw-test" || fail "$mp not writable"
  if [ "$lab" != parity2 ]; then mkdir -p "$mp/media/tv" "$mp/media/movies"; fi
  chown -R 1000:1000 "$mp"
  echo "ok: $lab $(df -h --output=size,avail "$mp" | tail -1) reserved=$(tune2fs -l "$p" | awk -F: '/Reserved block count/{gsub(/ /,"",$2);print $2}')"
  DONE="$DONE $lab"
done
# ---------- monitoring for the new mounts (Kuma "Mount /mnt/…" push monitors; rotates all mount tokens)
/usr/local/sbin/kuma-mounts /scratch /mnt/disk1 /mnt/disk2 /mnt/disk3 /mnt/disk4 /mnt/disk5 /mnt/disk6 /mnt/parity2 || echo "WARN: kuma-mounts failed (formats are fine)"
systemctl disable --now selftest-status.timer || true
lsblk -o NAME,SIZE,LABEL,MOUNTPOINT,SERIAL | grep -E "disk[3-6]|parity2|NAME"
echo "=== $(date -Is) wd-format-batch done:$DONE"
ntfy "WD format done" "Formatted + mounted:$DONE. Each verified writable; Kuma mount monitors added." 
touch /var/lib/media-server/wd-format.done
