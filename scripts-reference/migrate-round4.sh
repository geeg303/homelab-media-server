#!/usr/bin/env bash
# migrate-round4: sdb (SERIAL-SDB IronWolf, ntfs3 ro at /mnt/mig/sdb) -> disk4 (WD 7SJ8JDXW). Movies first (user Nov 13: swap rounds so movies arrive sooner).
# Copy-only + per-folder checksum verify, same rules as round 3. Formatting sdb afterwards needs her separate OK.
set -uo pipefail
LOG=/var/log/migrate/round4.log
V=/var/log/migrate/round4-verify.log
DEST=/mnt/disk4/media/movies
REVIEW=/mnt/disk4/review/sdb      # user Nov 11: keep non-media folders for her manual review
MEDIA_DIRS='^(Movies|System Volume Information|\$RECYCLE\.BIN)$'
T=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
alert(){ curl -fsS -m 10 -H "Title: box migration R4" ${2:+-H "Priority: high"} -d "$1" "https://ntfy.sh/$T" >/dev/null || true; }
die(){ echo "$(date -Is) ABORT: $1" >> $LOG; alert "ROUND 4 ABORTED: $1" high; exit 1; }
mkdir -p /var/log/migrate; : > $LOG; : > $V
echo "===== ROUND 4 start $(date -Is)" >> $LOG

# SMART gate (by serial)
for s in SERIAL-SDB 7SJ8JDXW; do
  d=$(ls /dev/disk/by-id/ata-*_"$s" 2>/dev/null | grep -v -- -part | head -1); [ -n "$d" ] || die "disk $s not found"
  for a in 5 187 197 198; do
    v=$(smartctl -d sat -A "$d" | awk -v a=$a '$1==a{print $10}')
    [ "${v:-0}" = "0" ] || die "SMART attr $a on $s is $v"
  done
done
echo "SMART gate passed" >> $LOG

# mounts: sdb ro source (by serial check); disk4 ext4 dest
mountpoint -q /mnt/mig/sdb || die "/mnt/mig/sdb not mounted"
src_dev=$(findmnt -rno SOURCE /mnt/mig/sdb); [ "$(lsblk -dno SERIAL "/dev/$(lsblk -no PKNAME "$src_dev")")" = SERIAL-SDB ] || die "/mnt/mig/sdb is not SERIAL-SDB"
findmnt -rno OPTIONS /mnt/mig/sdb | grep -qE '(^|,)ro(,|$)' || die "/mnt/mig/sdb is not read-only"
mountpoint -q /mnt/disk4 || die "disk4 not mounted"
[ "$(lsblk -dno SERIAL "/dev/$(lsblk -no PKNAME "$(findmnt -rno SOURCE /mnt/disk4)")")" = 7SJ8JDXW ] || die "/mnt/disk4 is not 7SJ8JDXW"
touch /mnt/disk4/.rwtest 2>/dev/null && rm -f /mnt/disk4/.rwtest || die "disk4 not writable"
mkdir -p "$DEST" "$REVIEW" || die "mkdir $DEST $REVIEW"
pgrep -x rsync >/dev/null && die "another rsync is running"

EX=(--exclude='$RECYCLE.BIN' --exclude='System Volume Information' --exclude='desktop.ini' --exclude='Thumbs.db')
alert "Round 4 copy started: 6.9 TB sdb -> disk4 (media/movies + review/sdb), Tdarr paused"

copy_one(){ # $1 = a folder, $2 = destination parent (default $DEST)
  local show="$1" to="${2:-$DEST}" name; name=$(basename "$show")
  echo "=== $(date -Is) COPY $name" >> $LOG
  out=$(rsync -rt --info=progress2 --itemize-changes --ignore-existing "${EX[@]}" "$show" "$to/" 2>&1) || { printf '%s\n' "$out" | tail -5 >> $LOG; echo "RSYNCFAIL $name" >> $LOG; return 1; }
  printf '%s\n' "$out" | grep -E '^[<>ch.*][fdLDS]' >> $LOG || true
}
copy_tree(){ # $1 = dir whose CHILDREN are show folders
  find "$1" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z | while IFS= read -r -d '' show; do copy_one "$show" || return 1; done
}
copy_tree "/mnt/mig/sdb/Movies" || die "copy failed in sdb/Movies"
extras(){ find /mnt/mig/sdb -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | grep -vE "$MEDIA_DIRS" | sort; }
while IFS= read -r x; do copy_one "/mnt/mig/sdb/$x" "$REVIEW" || die "copy failed: review/$x"; done < <(extras)
find /mnt/mig/sdb -mindepth 1 -maxdepth 1 -type f ! -iname desktop.ini ! -iname Thumbs.db -exec rsync -t --ignore-existing {} "$REVIEW/" \; || die "copy failed: top-level files"
echo "=== $(date -Is) COPY PHASE DONE" >> $LOG
alert "Round 4 copy done, starting checksum verify"

verify_one(){ # $1 folder, $2 tag, $3 destination parent (default $DEST)
  local show="$1" tag="$2" to="${3:-$DEST}" name n; name=$(basename "$show")
  out=$(rsync -rc --dry-run --itemize-changes --ignore-existing "${EX[@]}" "$show/" "$to/$name/" 2>&1)
  n=$(printf '%s' "$out" | grep -c . || true)
  echo "VERIFY [$tag] $name: differences=$n" >> $V
  if [ "$n" -gt 0 ]; then printf '%s\n' "$out" | head -20 >> $V; alert "ROUND 4: unexpected difference in '$name' ($n lines). See round4-verify.log" high; echo "UNEXPECTED CONFLICT $name" >> $V; fi
}
verify_tree(){ find "$1" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z | while IFS= read -r -d '' show; do verify_one "$show" "$2"; done; }
verify_tree "/mnt/mig/sdb/Movies" sdbMovies
while IFS= read -r x; do verify_one "/mnt/mig/sdb/$x" review "$REVIEW"; done < <(extras)
total=$(awk -F'differences=' '/^VERIFY/{s+=$2} END{print s+0}' $V)
folders=$(grep -c '^VERIFY' $V)
echo "ROUND4 VERIFY TOTAL differences=$total folders=$folders" >> $V
cat $V >> $LOG
chown -R 1000:1000 /mnt/disk4
echo "===== ROUND 4 finished $(date -Is); NO FORMAT of sdb until user's explicit OK" >> $LOG
alert "Round 4 finished. Verify: $folders folders, total differences=$total (expected 0). sdb stays untouched until user OKs its format."
