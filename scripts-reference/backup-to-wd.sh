#!/usr/bin/env bash
# backup-to-wd (user Nov 13: spare WD 7HK2YR2H = backup drive, option 1).
# Daily: /data/review (irreplaceable phone backups, photos, recordings, music) and the config-backup tarballs -> /mnt/backup.
# Files deleted from review/ are kept 30 days under /mnt/backup/review-deleted/<date>/.
set -euo pipefail
LOG=/var/log/media-server/backup-to-wd.log; mkdir -p /var/log/media-server; exec >> "$LOG" 2>&1
T=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
PUSH=$(cat /etc/media-server/kuma-push-wdbackup 2>/dev/null || true)
fail(){ echo "$(date -Is) FAIL: $1"; curl -fsS -m 10 -H "Title: box backup" -H "Priority: high" -d "WD backup FAILED: $1" "https://ntfy.sh/$T" >/dev/null || true
        [ -n "$PUSH" ] && curl -fsS -m 10 "$PUSH?status=down&msg=$(printf %s "$1" | tr ' ' '+')" >/dev/null || true; exit 1; }
trap 'fail "line $LINENO"' ERR
echo "=== $(date -Is) backup-to-wd"
mountpoint -q /mnt/backup || fail "/mnt/backup not mounted"
[ "$(lsblk -dno SERIAL "/dev/$(lsblk -no PKNAME "$(findmnt -rno SOURCE /mnt/backup)")")" = 7HK2YR2H ] || fail "/mnt/backup is not WD 7HK2YR2H"
mountpoint -q /data || fail "/data not mounted"
D=$(date +%F)
mkdir -p /mnt/backup/review /mnt/backup/config /mnt/backup/review-deleted
if [ -d /data/review ]; then
  rsync -a --delete --backup --backup-dir="/mnt/backup/review-deleted/$D" /data/review/ /mnt/backup/review/
fi
rsync -a --delete /scratch/backups/config/ /mnt/backup/config/
find /mnt/backup/review-deleted -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec rm -rf {} +
sz=$(du -sh /mnt/backup/review 2>/dev/null | cut -f1); cf=$(find /mnt/backup/config -type f | wc -l)
echo "$(date -Is) ok: review $sz, $cf config tarballs, free $(df -h --output=avail /mnt/backup | tail -1 | tr -d ' ')"
[ -n "$PUSH" ] && curl -fsS -m 10 "$PUSH?status=up&msg=review+$sz,+$cf+config+tarballs" >/dev/null || true
