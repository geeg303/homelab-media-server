#!/usr/bin/env bash
# migrate-round3: sdd (SERIAL-SDD, ntfs3 ro at /mnt/mig/sdd) → disk3 (WD SERIAL-WD1). Copy-only + per-show checksum verify.
# user Nov 11 22:00: "Once the format is complete proceed with round 3". Formatting sdd afterwards needs her separate OK.
set -uo pipefail
LOG=/var/log/migrate/round3.log
V=/var/log/migrate/round3-verify.log
DEST=/mnt/disk3/media/tv
T=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
alert(){ curl -fsS -m 10 -H "Title: box migration R3" ${2:+-H "Priority: high"} -d "$1" "https://ntfy.sh/$T" >/dev/null || true; }
die(){ echo "$(date -Is) ABORT: $1" >> $LOG; alert "ROUND 3 ABORTED: $1" high; exit 1; }
mkdir -p /var/log/migrate; : > $LOG; : > $V
echo "===== ROUND 3 start $(date -Is)" >> $LOG

# SMART gate (by serial)
for s in SERIAL-SDD SERIAL-WD1; do
  d=$(ls /dev/disk/by-id/ata-*_"$s" 2>/dev/null | grep -v -- -part | head -1); [ -n "$d" ] || die "disk $s not found"
  for a in 5 187 197 198; do
    v=$(smartctl -d sat -A "$d" | awk -v a=$a '$1==a{print $10}')
    [ "${v:-0}" = "0" ] || die "SMART attr $a on $s is $v"
  done
done
echo "SMART gate passed" >> $LOG

# mounts: sdd ro source (by serial check); disk3 ext4 dest
mountpoint -q /mnt/mig/sdd || die "/mnt/mig/sdd not mounted"
src_dev=$(findmnt -rno SOURCE /mnt/mig/sdd); [ "$(lsblk -dno SERIAL "/dev/$(lsblk -no PKNAME "$src_dev")")" = SERIAL-SDD ] || die "/mnt/mig/sdd is not SERIAL-SDD"
findmnt -rno OPTIONS /mnt/mig/sdd | grep -qE '(^|,)ro(,|$)' || die "/mnt/mig/sdd is not read-only"
mountpoint -q /mnt/disk3 || die "disk3 not mounted"
[ "$(lsblk -dno SERIAL "/dev/$(lsblk -no PKNAME "$(findmnt -rno SOURCE /mnt/disk3)")")" = SERIAL-WD1 ] || die "/mnt/disk3 is not SERIAL-WD1"
touch /mnt/disk3/.rwtest 2>/dev/null && rm -f /mnt/disk3/.rwtest || die "disk3 not writable"
mkdir -p "$DEST" || die "mkdir $DEST"
pgrep -x rsync >/dev/null && die "another rsync is running"

EX=(--exclude='$RECYCLE.BIN' --exclude='System Volume Information' --exclude='desktop.ini' --exclude='Thumbs.db')
alert "Round 3 copy started: 7.21 TB sdd -> disk3 media/tv (Tdarr paused)"

copy_one(){ # $1 = a show folder
  local show="$1" name; name=$(basename "$show")
  echo "=== $(date -Is) COPY $name" >> $LOG
  out=$(rsync -rt --info=progress2 --itemize-changes --ignore-existing "${EX[@]}" "$show" "$DEST/" 2>&1) || { printf '%s\n' "$out" | tail -5 >> $LOG; echo "RSYNCFAIL $name" >> $LOG; return 1; }
  printf '%s\n' "$out" | grep -E '^[<>ch.*][fdLDS]' >> $LOG || true
}
copy_tree(){ # $1 = dir whose CHILDREN are show folders
  find "$1" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z | while IFS= read -r -d '' show; do copy_one "$show" || return 1; done
}
copy_tree "/mnt/mig/sdd/TV Shows" || die "copy failed in sdd/TV Shows"
copy_tree "/mnt/mig/sdd/_from_sdc/TV Shows" || die "copy failed in staged _from_sdc"
copy_one "/mnt/mig/sdd/Show 55" || die "copy failed: Show 55"
copy_one "/mnt/mig/sdd/Show 49" || die "copy failed: Show 49"
echo "=== $(date -Is) COPY PHASE DONE" >> $LOG
alert "Round 3 copy done, starting checksum verify"

verify_one(){
  local show="$1" tag="$2" name n; name=$(basename "$show")
  out=$(rsync -rc --dry-run --itemize-changes --ignore-existing "${EX[@]}" "$show/" "$DEST/$name/" 2>&1)
  n=$(printf '%s' "$out" | grep -c . || true)
  echo "VERIFY [$tag] $name: differences=$n" >> $V
  if [ "$n" -gt 0 ]; then printf '%s\n' "$out" | head -20 >> $V; alert "ROUND 3: unexpected difference in '$name' ($n lines). See round3-verify.log" high; echo "UNEXPECTED CONFLICT $name" >> $V; fi
}
verify_tree(){ find "$1" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z | while IFS= read -r -d '' show; do verify_one "$show" "$2"; done; }
verify_tree "/mnt/mig/sdd/TV Shows" sddTV
verify_tree "/mnt/mig/sdd/_from_sdc/TV Shows" staged
verify_one "/mnt/mig/sdd/Show 55" sdd
verify_one "/mnt/mig/sdd/Show 49" sdd
total=$(awk -F'differences=' '/^VERIFY/{s+=$2} END{print s+0}' $V)
folders=$(grep -c '^VERIFY' $V)
echo "ROUND3 VERIFY TOTAL differences=$total folders=$folders" >> $V
cat $V >> $LOG
chown -R 1000:1000 /mnt/disk3
echo "===== ROUND 3 finished $(date -Is); NO FORMAT of sdd until user's explicit OK" >> $LOG
alert "Round 3 finished. Verify: $folders folders, total differences=$total (expected 0). sdd stays untouched until user OKs its format."
