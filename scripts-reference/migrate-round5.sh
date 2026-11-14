#!/usr/bin/env bash
# migrate-round5: sde (SERIAL-SDE, ntfs3 ro at /mnt/mig/sde) -> disk5 (WD 7HJY59ZF) TV, non-media -> disk6/review/sde. Started by round5-start after round 4 verifies clean (user Nov 14: "2. Yes").
# Copy-only + per-folder checksum verify, same rules as round 3. Formatting sde afterwards needs her separate OK.
set -uo pipefail
LOG=/var/log/migrate/round5.log
V=/var/log/migrate/round5-verify.log
DEST=/mnt/disk5/media/tv
REVIEW=/mnt/disk6/review/sde      # on disk6: sde's TV (7.91 TB) nearly fills disk5 (8.0 TB)
MEDIA_DIRS='^(TV Shows|System Volume Information|\$RECYCLE\.BIN)$'
T=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
alert(){ curl -fsS -m 10 -H "Title: box migration R5" ${2:+-H "Priority: high"} -d "$1" "https://ntfy.sh/$T" >/dev/null || true; }
die(){ echo "$(date -Is) ABORT: $1" >> $LOG; alert "ROUND 5 ABORTED: $1" high; exit 1; }
mkdir -p /var/log/migrate; : > $LOG; : > $V
echo "===== ROUND 5 start $(date -Is)" >> $LOG

# SMART gate (by serial)
for s in SERIAL-SDE 7HJY59ZF; do
  d=$(ls /dev/disk/by-id/ata-*_"$s" 2>/dev/null | grep -v -- -part | head -1); [ -n "$d" ] || die "disk $s not found"
  for a in 5 187 197 198; do
    v=$(smartctl -d sat -A "$d" | awk -v a=$a '$1==a{print $10}')
    [ "${v:-0}" = "0" ] || die "SMART attr $a on $s is $v"
  done
done
echo "SMART gate passed" >> $LOG

# mounts: sde ro source (by serial check); disk5 ext4 dest
mountpoint -q /mnt/mig/sde || die "/mnt/mig/sde not mounted"
src_dev=$(findmnt -rno SOURCE /mnt/mig/sde); [ "$(lsblk -dno SERIAL "/dev/$(lsblk -no PKNAME "$src_dev")")" = SERIAL-SDE ] || die "/mnt/mig/sde is not SERIAL-SDE"
findmnt -rno OPTIONS /mnt/mig/sde | grep -qE '(^|,)ro(,|$)' || die "/mnt/mig/sde is not read-only"
mountpoint -q /mnt/disk5 || die "disk5 not mounted"
[ "$(lsblk -dno SERIAL "/dev/$(lsblk -no PKNAME "$(findmnt -rno SOURCE /mnt/disk5)")")" = 7HJY59ZF ] || die "/mnt/disk5 is not 7HJY59ZF"
touch /mnt/disk5/.rwtest 2>/dev/null && rm -f /mnt/disk5/.rwtest || die "disk5 not writable"
mountpoint -q /mnt/disk6 || die "disk6 (review destination) not mounted"
[ "$(lsblk -dno SERIAL "/dev/$(lsblk -no PKNAME "$(findmnt -rno SOURCE /mnt/disk6)")")" = 7HJY82BF ] || die "/mnt/disk6 is not 7HJY82BF"
need=7954219167744; have=$(( $(df -B1 --output=avail /mnt/disk5 | tail -1) + $(df -B1 --output=avail /mnt/disk6 | tail -1) )); [ $have -gt $need ] || die "not enough space on disk5+disk6"
mkdir -p "$DEST" "$REVIEW" || die "mkdir $DEST $REVIEW"
pgrep -x rsync >/dev/null && die "another rsync is running"

EX=(--exclude='$RECYCLE.BIN' --exclude='System Volume Information' --exclude='desktop.ini' --exclude='Thumbs.db')
alert "Round 5 copy started: 7.95 TB sde -> disk5 (media/tv) + disk6 (review/sde), Tdarr paused"

copy_one(){ # $1 = a folder, $2 = destination parent (default $DEST)
  local show="$1" to="${2:-$DEST}" name; name=$(basename "$show")
  echo "=== $(date -Is) COPY $name" >> $LOG
  out=$(rsync -rt --info=progress2 --itemize-changes --ignore-existing "${EX[@]}" "$show" "$to/" 2>&1) || { printf '%s\n' "$out" | tail -5 >> $LOG; echo "RSYNCFAIL $name" >> $LOG; return 1; }
  printf '%s\n' "$out" | grep -E '^[<>ch.*][fdLDS]' >> $LOG || true
}
copy_tree(){ # $1 = dir whose CHILDREN are show folders
  find "$1" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z | while IFS= read -r -d '' show; do copy_one "$show" || return 1; done
}
copy_tree "/mnt/mig/sde/TV Shows" || die "copy failed in sde/TV Shows"
extras(){ find /mnt/mig/sde -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | grep -vE "$MEDIA_DIRS" | sort; }
while IFS= read -r x; do copy_one "/mnt/mig/sde/$x" "$REVIEW" || die "copy failed: review/$x"; done < <(extras)
find /mnt/mig/sde -mindepth 1 -maxdepth 1 -type f ! -iname desktop.ini ! -iname Thumbs.db -exec rsync -t --ignore-existing {} "$REVIEW/" \; || die "copy failed: top-level files"
echo "=== $(date -Is) COPY PHASE DONE" >> $LOG
alert "Round 5 copy done, starting checksum verify"

verify_one(){ # $1 folder, $2 tag, $3 destination parent (default $DEST)
  local show="$1" tag="$2" to="${3:-$DEST}" name n; name=$(basename "$show")
  out=$(rsync -rc --dry-run --itemize-changes --ignore-existing "${EX[@]}" "$show/" "$to/$name/" 2>&1)
  n=$(printf '%s' "$out" | grep -c . || true)
  echo "VERIFY [$tag] $name: differences=$n" >> $V
  if [ "$n" -gt 0 ]; then printf '%s\n' "$out" | head -20 >> $V; alert "ROUND 5: unexpected difference in '$name' ($n lines). See round5-verify.log" high; echo "UNEXPECTED CONFLICT $name" >> $V; fi
}
verify_tree(){ find "$1" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z | while IFS= read -r -d '' show; do verify_one "$show" "$2"; done; }
verify_tree "/mnt/mig/sde/TV Shows" sdeTV
while IFS= read -r x; do verify_one "/mnt/mig/sde/$x" review "$REVIEW"; done < <(extras)
total=$(awk -F'differences=' '/^VERIFY/{s+=$2} END{print s+0}' $V)
folders=$(grep -c '^VERIFY' $V)
echo "ROUND5 VERIFY TOTAL differences=$total folders=$folders" >> $V
cat $V >> $LOG
chown -R 1000:1000 /mnt/disk5 /mnt/disk6/review
echo "===== ROUND 5 finished $(date -Is); NO FORMAT of sde until user's explicit OK" >> $LOG
alert "Round 5 finished. Verify: $folders folders, total differences=$total (expected 0). sde stays untouched until user OKs its format."
