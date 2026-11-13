#!/usr/bin/env bash
# docker-update-all: update every Docker stack (user Nov 12: "update all docker containers while the copy job runs").
# Copy-safe: no container mounts /data, the NTFS sources or disk3, so restarts don't touch round 3.
set -uo pipefail
TS=$(date +%Y%m%d-%H%M); RB=/var/lib/media-server/image-rollback-$TS.txt; LOG=/var/log/media-server/docker-update-$TS.log
exec > >(tee -a "$LOG") 2>&1
echo "=== $(date -Is) docker update"
systemctl is-active --quiet migrate-round3 || { echo "ABORT: round 3 runner not active (unexpected)"; exit 1; }
w=$(curl -s -m 5 "http://127.0.0.1:8181/api/v2?apikey=$(sed -n 's/^api_key *= *//p' /opt/media/config/tautulli/config.ini | head -1)&cmd=get_activity" | python3 -c "import json,sys; print(json.load(sys.stdin)['response']['data'].get('stream_count','?'))" 2>/dev/null || echo "?")
echo "Plex streams now: $w"
# 1. rollback record: container -> image ref + image id + repo digest
for c in $(docker ps --format '{{.Names}}'); do
  img=$(docker inspect -f '{{.Config.Image}}' "$c"); id=$(docker inspect -f '{{.Image}}' "$c")
  dg=$(docker image inspect -f '{{join .RepoDigests ","}}' "$id" 2>/dev/null)
  echo "$c $img $id $dg"
done > "$RB"
echo "rollback record: $RB ($(wc -l < "$RB") containers)"
# 2. fresh config backup (stops/starts core plex tdarr ops itself)
/usr/local/sbin/media-config-backup || { echo "ABORT: config backup failed"; exit 1; }
# 3. pull + recreate, one stack at a time
for st in ops core plex tdarr livetv glances; do
  dir=/opt/media/stacks/$st; echo "--- $st"
  ( cd "$dir" && docker compose pull -q && docker compose up -d --remove-orphans 2>&1 | grep -vE "^\s*$" ) || echo "WARN: $st update failed"
  sleep 5
done
echo "--- dockge"; ( cd /opt/media/dockge && docker compose pull -q && docker compose up -d 2>&1 ) || echo "WARN: dockge update failed"
# Kuma caches container DNS: after the others got new IPs its checks hit the old ones (ECONNREFUSED). Restart it last.
sleep 10; docker restart uptime-kuma >/dev/null && echo "uptime-kuma restarted (DNS cache)"
# 4. Tdarr stays paused during the migration rounds
sleep 30; /usr/local/sbin/tdarr-workers set 0 0 || echo "WARN: could not re-pause Tdarr"
# 5. what changed
echo "--- changed images"
while read -r c img oldid _; do
  new=$(docker inspect -f '{{.Image}}' "$c" 2>/dev/null || echo missing)
  [ "$new" != "$oldid" ] && echo "UPDATED $c ($img)" 
done < "$RB"
echo "--- status"; sleep 30
docker ps -a --format '{{.Names}}|{{.Status}}' | sort
systemctl is-active migrate-round3 && echo "round 3 still running"
echo "=== done $(date -Is)"
