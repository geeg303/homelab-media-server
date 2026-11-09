#!/usr/bin/env bash
set -uo pipefail
LOG=/var/log/migrate/round1.log
T=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
alert(){ curl -fsS -m 10 -H "Title: box migration R1" ${2:+-H "Priority: high"} -d "$1" "https://ntfy.sh/$T" >/dev/null || true; }
die(){ echo "$(date -Is) ABORT: $1" >> $LOG; alert "ROUND 1 ABORTED: $1" high; exit 1; }
mkdir -p /var/log/migrate
echo "===== ROUND 1 v2 start $(date -Is)" >> $LOG

# 1. SMART gate
for d in sda sdb sdc sdd sde; do
  for a in 5 187 197 198; do
    v=$(smartctl -d sat -A /dev/$d | awk -v a=$a '$1==a{print $10}')
    [ "${v:-0}" = "0" ] || die "SMART attr $a on $d is $v (was 0)"
  done
done
echo "SMART gate passed $(date -Is)" >> $LOG

# 2. mounts: sdc ro, sda+sdd rw with write test
mountpoint -q /mnt/mig/sdc || mount -t ntfs3 -o ro,noatime /dev/disk/by-uuid/DBF105B5037AE18C /mnt/mig/sdc || die "sdc ro mount failed"
for pair in "sda DAC5EAE19F16E58C" "sdd F90BE72FDA7942A2"; do
  set -- $pair
  mountpoint -q /mnt/mig/$1 && umount /mnt/mig/$1
  mount -t ntfs3 -o rw,noatime /dev/disk/by-uuid/$2 /mnt/mig/$1 || die "$1 rw mount failed"
  touch /mnt/mig/$1/.rwtest 2>/dev/null && rm -f /mnt/mig/$1/.rwtest || die "$1 mounted but not writable (ro fallback)"
done
mkdir -p "/mnt/mig/sda/_from_sdc/TV Shows" "/mnt/mig/sdd/_from_sdc/TV Shows" || die "mkdir staging"
echo "mounts ok $(date -Is)" >> $LOG
alert "Round 1 copy started: 4.28 TB, sdc -> sda+sdd staging"

EX=(--exclude='$RECYCLE.BIN' --exclude='System Volume Information' --exclude='desktop.ini' --exclude='Thumbs.db')
# 3. copy per show (stop at first failure; --ignore-existing, conflicts detected in verify)
while IFS=$'\t' read -r dst name size; do
  [ "$name" = "pc-backup folder" ] && continue
  echo "=== $(date -Is) COPY [$dst] $name" >> $LOG
  rsync -rt --info=progress2 --itemize-changes --ignore-existing "${EX[@]}" \
    "/mnt/mig/sdc/TV Shows/$name" "/mnt/mig/$dst/_from_sdc/TV Shows/" >> $LOG 2>&1 \
    || die "rsync failed on '$name' (see $LOG)"
done < /tmp/round1-split.tsv
echo "=== $(date -Is) COPY PHASE DONE" >> $LOG
alert "Round 1 copy phase done, starting checksum verify"

# 4. verify per show
V=/var/log/migrate/round1-verify.log; : > $V
total=0
while IFS=$'\t' read -r dst name size; do
  [ "$name" = "pc-backup folder" ] && continue
  out=$(rsync -rc --dry-run --itemize-changes "${EX[@]}" \
    "/mnt/mig/sdc/TV Shows/$name/" "/mnt/mig/$dst/_from_sdc/TV Shows/$name/" 2>&1)
  n=$(printf '%s' "$out" | grep -c . || true)
  echo "VERIFY [$dst] $name: differences=$n" >> $V
  [ "$n" -gt 0 ] && printf '%s\n' "$out" | head -20 >> $V
  total=$((total+n))
done < /tmp/round1-split.tsv
echo "ROUND1 VERIFY TOTAL differences=$total" >> $V
cat $V >> $LOG
echo "===== ROUND 1 copy+verify finished $(date -Is); NO FORMAT until explicit OK" >> $LOG
alert "Round 1 finished. Verify total differences=$total. Logs: round1.log / round1-verify.log. Waiting for user's 'format sdc' OK."
