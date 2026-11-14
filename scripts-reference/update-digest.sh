#!/usr/bin/env bash
# update-digest: once a day, one ntfy message listing the container images DIUN saw change (then clears the list).
set -uo pipefail
F=/opt/media/config/diun/pending-updates.txt; [ -s $F ] || exit 0
T=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
n=$(sort -u -k3 $F | wc -l); body=$(awk '{print $3}' $F | sort -u | sed 's/^/• /' | head -30)
curl -fsS -m 10 -H "Title: box: $n container update(s) available" -H "Priority: low" -H "Tags: package" \
  -d "$body
Apply with docker-update-all (ask Hermes) or wait for the next planned update." "https://ntfy.sh/$T" >/dev/null && : > $F
