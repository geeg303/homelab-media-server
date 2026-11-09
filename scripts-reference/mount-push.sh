#!/usr/bin/env bash
# /etc/media-server/kuma-push.conf: "<mountpoint> <push-url>" per line
CONF=/etc/media-server/kuma-push.conf; [ -f "$CONF" ] || exit 0
while read -r m url; do [ -z "$m" ] || [ "${m:0:1}" = "#" ] && continue
  mountpoint -q "$m" && curl -fsS -m 5 "$url?status=up&msg=mounted" >/dev/null || true
done < "$CONF"
