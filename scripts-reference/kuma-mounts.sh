#!/usr/bin/env bash
# kuma-mounts: (re)create "Mount <mp>" Kuma push monitors for the given mountpoints with fresh tokens, rewrite kuma-push.conf,
# refresh the status page. Usage: kuma-mounts /scratch /mnt/disk1 ...   (always pass the FULL list; the conf is rewritten)
set -euo pipefail
[ $# -gt 0 ] || { echo "usage: kuma-mounts <mountpoint>..."; exit 1; }
SH=/usr/local/share/media-server
docker cp $SH/kuma_mounts.js uptime-kuma:/app/kuma_mounts.js
docker exec -e MOUNTS="$*" -w /app uptime-kuma node kuma_mounts.js
docker exec uptime-kuma rm -f /app/kuma_mounts.js
umask 077
cp -a /etc/media-server/kuma-push.conf /etc/media-server/kuma-push.conf.bak-$(date +%Y%m%d-%H%M)
docker exec uptime-kuma cat /app/data/.mountpush > /etc/media-server/kuma-push.conf.new
docker exec uptime-kuma rm -f /app/data/.mountpush
if [ "$(grep -c api/push /etc/media-server/kuma-push.conf.new)" -ne $# ]; then echo "ABORT: push conf incomplete, old conf kept"; rm -f /etc/media-server/kuma-push.conf.new; exit 1; fi
mv /etc/media-server/kuma-push.conf.new /etc/media-server/kuma-push.conf; chmod 600 /etc/media-server/kuma-push.conf
find /etc/media-server -maxdepth 1 -name 'kuma-push.conf.bak-*' -mmin +5 -delete    # old backups hold stale tokens
docker cp $SH/kuma_statuspage.js uptime-kuma:/app/kuma_statuspage.js
docker exec -w /app uptime-kuma node kuma_statuspage.js
docker exec uptime-kuma rm -f /app/kuma_statuspage.js
systemctl start mount-push.service
echo "kuma-mounts: $# mount monitors, conf rewritten"
