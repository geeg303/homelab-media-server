#!/usr/bin/env bash
# docker-update-all -- update every Docker stack: rollback record, config backup, pull + recreate per stack, report.
# v2 (Nov 21): migration gates removed; Tdarr worker count is restored by the caller, not forced to 0 here.
set -uo pipefail
TS=$(date +%Y%m%d-%H%M); RB=/var/lib/media-server/image-rollback-$TS.txt; LOG=/var/log/media-server/docker-update-$TS.log
exec > >(tee -a "$LOG") 2>&1
echo "=== $(date -Is) docker update"
w=$(curl -s -m 5 "http://127.0.0.1:8181/api/v2?apikey=$(sed -n 's/^api_key *= *//p' /opt/media/config/tautulli/config.ini | head -1)&cmd=get_activity" | python3 -c "import json,sys; print(json.load(sys.stdin)['response']['data'].get('stream_count','?'))" 2>/dev/null || echo "?")
echo "Plex streams now: $w"
/usr/local/sbin/kuma-maint on 45m >/dev/null || echo "WARN: kuma-maint on failed"
# 1. rollback record: container -> image ref + image id + repo digest
for c in $(docker ps --format '{{.Names}}'); do
  img=$(docker inspect -f '{{.Config.Image}}' "$c"); id=$(docker inspect -f '{{.Image}}' "$c")
  dg=$(docker image inspect -f '{{join .RepoDigests ","}}' "$id" 2>/dev/null)
  echo "$c $img $id $dg"
done > "$RB"
echo "rollback record: $RB ($(wc -l < "$RB") containers)"
# 2. fresh config backup (stops/starts the stacks itself)
/usr/local/sbin/media-config-backup || { echo "ABORT: config backup failed"; exit 1; }
# 3. pull + recreate, one stack at a time (each dir's .env COMPOSE_FILE picks the active override files)
for st in ops core plex tdarr glances; do
  dir=/opt/media/stacks/$st; echo "--- $st"
  ( cd "$dir" && docker compose pull -q && docker compose up -d --remove-orphans 2>&1 | grep -vE "^\s*$" ) || echo "WARN: $st update failed"
  sleep 5
done
echo "--- crypto (locally built: refresh the python base image, rebuild, recreate)"
( cd /opt/media/stacks/crypto && docker compose build --pull -q && docker compose up -d 2>&1 | grep -vE "^\s*$" ) || echo "WARN: crypto update failed"
echo "--- dockge"; ( cd /opt/media/dockge && docker compose pull -q && docker compose up -d 2>&1 ) || echo "WARN: dockge update failed"
# Kuma caches container DNS: after the others got new IPs its checks hit the old ones (ECONNREFUSED). Restart it last.
sleep 10; docker restart uptime-kuma >/dev/null && echo "uptime-kuma restarted (DNS cache)"
# 4. what changed
echo "--- changed images"
while read -r c img oldid _; do
  new=$(docker inspect -f '{{.Image}}' "$c" 2>/dev/null || echo missing)
  [ "$new" != "$oldid" ] && echo "UPDATED $c ($img)"
done < "$RB"
echo "--- status"; sleep 30
docker ps -a --format '{{.Names}}|{{.Status}}' | sort
docker image prune -f >/dev/null && echo "old images pruned"
echo "=== done $(date -Is)"
