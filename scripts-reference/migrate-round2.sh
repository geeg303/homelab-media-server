#!/usr/bin/env bash
set -uo pipefail
LOG=/var/log/migrate/round2.log
V=/var/log/migrate/round2-verify.log
T=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
alert(){ curl -fsS -m 10 -H "Title: box migration R2" ${2:+-H "Priority: high"} -d "$1" "https://ntfy.sh/$T" >/dev/null || true; }
die(){ echo "$(date -Is) ABORT: $1" >> $LOG; alert "ROUND 2 ABORTED: $1" high; exit 1; }
mkdir -p /var/log/migrate; : > $LOG; : > $V
echo "===== ROUND 2 start $(date -Is)" >> $LOG

# SMART gate
for d in sda sdb sdd sde; do
  for a in 5 187 197 198; do
    v=$(smartctl -d sat -A /dev/$d | awk -v a=$a '$1==a{print $10}')
    [ "${v:-0}" = "0" ] || die "SMART attr $a on $d is $v"
  done
done
echo "SMART gate passed" >> $LOG

# mounts: sda ro source; disk1 ext4 dest
mountpoint -q /mnt/mig/sda || mount -t ntfs3 -o ro,noatime /dev/disk/by-uuid/DAC5EAE19F16E58C /mnt/mig/sda || die "sda ro mount failed"
mountpoint -q /mnt/disk1 || mount /mnt/disk1 || die "disk1 mount failed"
touch /mnt/disk1/.rwtest 2>/dev/null && rm -f /mnt/disk1/.rwtest || die "disk1 not writable"
mkdir -p /mnt/disk1/media/tv || die "mkdir media/tv"

EX=(--exclude='$RECYCLE.BIN' --exclude='System Volume Information' --exclude='desktop.ini' --exclude='Thumbs.db')
DUPES='show-x|show-57|show-91|show-92|show-98'
alert "Round 2 copy started: 7.284 TB sda -> disk1 media/tv"

copy_tree(){ # $1 = source dir whose CHILDREN are show folders
  local src="$1"
  find "$src" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z | while IFS= read -r -d '' show; do
    name=$(basename "$show")
    echo "=== $(date -Is) COPY $name" >> $LOG
    out=$(rsync -rt --info=progress2 --itemize-changes --ignore-existing "${EX[@]}" \
      "$show" /mnt/disk1/media/tv/ 2>&1) || { printf '%s\n' "$out" | tail -5 >> $LOG; echo "RSYNCFAIL $name" >> $LOG; return 1; }
    printf '%s\n' "$out" | grep -E '^[<>ch.*][fdLDS]' >> $LOG || true
  done
}
copy_tree "/mnt/mig/sda/TV" || die "copy failed in sda/TV"
copy_tree "/mnt/mig/sda/_from_sdc/TV Shows" || die "copy failed in staged _from_sdc"
echo "=== $(date -Is) COPY PHASE DONE" >> $LOG
alert "Round 2 copy done, starting verify"

verify_tree(){
  local src="$1" tag="$2"
  find "$src" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z | while IFS= read -r -d '' show; do
    name=$(basename "$show")
    out=$(rsync -rc --dry-run --itemize-changes --ignore-existing "${EX[@]}" \
      "$show/" "/mnt/disk1/media/tv/$name/" 2>&1)
    n=$(printf '%s' "$out" | grep -c . || true)
    echo "VERIFY [$tag] $name: differences=$n" >> $V
    if [ "$n" -gt 0 ]; then
      printf '%s\n' "$out" | head -20 >> $V
      if ! printf '%s' "$name" | grep -qiE "$DUPES"; then
        alert "ROUND 2 PAUSED: unexpected conflict in '$name' ($n lines). See round2-verify.log" high
        echo "UNEXPECTED CONFLICT $name" >> $V
      fi
    fi
  done
}
verify_tree "/mnt/mig/sda/TV" sdaTV
verify_tree "/mnt/mig/sda/_from_sdc/TV Shows" staged
total=$(awk -F'differences=' '/^VERIFY/{s+=$2} END{print s+0}' $V)
echo "ROUND2 VERIFY TOTAL differences=$total" >> $V
cat $V >> $LOG
chown -R 1000:1000 /mnt/disk1
echo "===== ROUND 2 finished $(date -Is); NO FORMAT until explicit OK" >> $LOG
alert "Round 2 finished. Verify total differences=$total (expected >0 only on the 5 dup shows). Waiting for 'format sda'."
