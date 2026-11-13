#!/usr/bin/env bash
# Nightly backup of /opt/media/config + stacks. Daily x14, weekly (Sunday) x8.
set -euo pipefail
umask 077
SRC=/opt/media/config; ROOT=/scratch/backups/config; POOL=/data/backups/config
STACKS=(core plex tdarr ops); STAMP=$(date +%F); DOW=$(date +%u)
NTFY_TOPIC=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
notify(){ curl -fsS -m 10 -H "Title: box backup" -d "$1" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null || true; }
trap 'notify "Config backup FAILED on $(hostname) at $(date)"' ERR
mountpoint -q /scratch || { notify "Backup skipped: /scratch not mounted"; exit 1; }
mkdir -p "$ROOT/daily" "$ROOT/weekly"
running=()
for s in "${STACKS[@]}"; do f=/opt/media/stacks/$s/compose.yaml
  if [ -n "$(docker compose -f "$f" ps -q 2>/dev/null)" ]; then running+=("$s"); docker compose -f "$f" stop -t 60 >/dev/null; fi
done
restart(){ for s in "${running[@]}"; do docker compose -f /opt/media/stacks/$s/compose.yaml start >/dev/null; done; }
trap 'restart; notify "Config backup FAILED on $(hostname) at $(date)"' ERR
OUT="$ROOT/daily/config-$STAMP.tar.zst"
tar --zstd -cf "$OUT.tmp" -C /opt/media \
  --exclude='config/plex/Library/Application Support/Plex Media Server/Cache' \
  --exclude='config/plex/Library/Application Support/Plex Media Server/Crash Reports' \
  --exclude='config/plex/Library/Application Support/Plex Media Server/Logs' \
  --exclude='config/recyclarr/resources' \
  config stacks dockge
mv "$OUT.tmp" "$OUT"
restart; trap 'notify "Config backup post-step FAILED on $(hostname)"' ERR
zstd -tq "$OUT"
[ "$DOW" = 7 ] && cp -a "$OUT" "$ROOT/weekly/"
find "$ROOT/daily"  -name 'config-*.tar.zst' -mtime +13 -delete
find "$ROOT/weekly" -name 'config-*.tar.zst' -mtime +55 -delete
if mountpoint -q /data; then mkdir -p "$POOL"; rsync -a --delete "$ROOT/" "$POOL/"; fi
PUSH=$(cat /etc/media-server/kuma-push-backup 2>/dev/null || true)
# Kuma is in the ops stack this script just restarted: wait for it (up to ~3 min) before pushing (Nov 13 fix; pushes had failed since Nov 8)
if [ -n "$PUSH" ]; then for i in $(seq 1 18); do curl -fsS -m 10 "$PUSH?status=up&msg=$(basename "$OUT")" >/dev/null 2>&1 && break; sleep 10; done; fi
echo "backup ok: $OUT ($(du -h "$OUT" | cut -f1))"
