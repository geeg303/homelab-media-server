#!/usr/bin/env bash
# pcbackup-scratch-delete (user Nov 23 "Yes do that", item 2): after the nightly WD backup, delete the scratch copy of
# "pc-backup folder" ONLY if the WD copy is complete and byte-identical to /data/review/sdc/pc-backup folder.
set -uo pipefail
L=/var/log/media-server/scratch-cleanup-20261123.log; exec >>$L 2>&1
S="/scratch/safekeep/sdc/pc-backup folder"; R="/data/review/sdc/pc-backup folder"; W="/mnt/backup/review/sdc/pc-backup folder"
NT=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
say(){ echo "$(date -Is) $1"; curl -fsS -m 10 -H "Title: box scratch cleanup" -d "$1" "https://ntfy.sh/$NT" >/dev/null || true; }
[ -d "$S" ] || { say "pc-backup folder scratch copy already gone"; exit 0; }
n_s=$(find "$S" -type f | wc -l); n_w=$(find "$W" -type f 2>/dev/null | wc -l)
diffs=$(rsync -a -n -c --itemize-changes "$S/" "$W/" 2>&1 | grep -v '^\.d' | wc -l)
if [ "$n_s" -gt 0 ] && [ "$n_s" = "$n_w" ] && [ "$diffs" = 0 ]; then
  rm -rf "/scratch/safekeep/sdc" && rmdir /scratch/safekeep 2>/dev/null
  say "Deleted the scratch copy of pc-backup folder ($n_s files): it is on the pool (review/sdc) and the WD drive. Scratch now $(df -h --output=used /scratch | tail -1 | tr -d ' ') used."
else
  say "KEPT the scratch copy of pc-backup folder: WD check failed (scratch $n_s files, WD $n_w files, $diffs differences)"
fi
