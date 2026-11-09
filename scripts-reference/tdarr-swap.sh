#!/usr/bin/env bash
# tdarr-swap: replace library originals on disk1 with verified Tdarr encodes. Originals are DELETED after verification
# (user, Nov 9: no holding copy). Every replaced path is recorded in $DONE_LIST and never replaced twice.
# Usage: tdarr-swap <encode-dir> [--dry-run]     e.g. tdarr-swap /scratch/tdarr/output-4k
# Per encode: find the original on disk1 by file name, verify (same duration ±2 s, same video frame count, same audio
# track count, HDR10 kept if the original is PQ/HDR10), copy encode next to the original as a temp file, check sha256,
# rename the temp file over the original, delete the encode. Anything that fails verification is left untouched and logged.
set -euo pipefail
SRC_DIR=${1:?encode dir}; DRY=${2:-}
LIB=/mnt/disk1/media/tv
DONE_LIST=/var/lib/media-server/tdarr-swapped.list
LOG=/var/log/media-server/tdarr-swap.log
LOCK=/run/tdarr-swap.lock
mkdir -p /var/log/media-server /var/lib/media-server
exec 9>"$LOCK"; flock -n 9 || { echo "already running"; exit 0; }
log(){ echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
for m in /mnt/disk1; do mountpoint -q "$m" || { log "ABORT: $m not mounted"; exit 1; }; done
probe(){ docker exec tdarr-node /usr/local/bin/ffprobe -v error "$@"; }
# tdarr-node sees disk1 at /media/disk1/tv (ro) and /scratch/tdarr at the same path
inpath(){ case "$1" in "$LIB"/*) echo "/media/disk1/tv/${1#$LIB/}";; *) echo "$1";; esac; }
ok=0; bad=0
while IFS= read -r -d '' enc; do
  # skip files Tdarr may still be writing
  [ $(( $(date +%s) - $(stat -c %Y "$enc") )) -ge 120 ] || continue
  b=$(basename "$enc")
  orig=$(find "$LIB" -mindepth 2 -maxdepth 4 -type f -name "$b" -print -quit)
  if [ -z "$orig" ]; then log "SKIP no original on disk1: $b"; bad=$((bad+1)); continue; fi
  rel=${orig#$LIB/}
  if grep -qxF "$rel" "$DONE_LIST" 2>/dev/null; then log "SKIP already replaced once: $rel"; bad=$((bad+1)); continue; fi
  io=$(inpath "$orig"); ie=$(inpath "$enc")
  da=$(probe -show_entries format=duration -of csv=p=0 "$io" | cut -d. -f1)
  de=$(probe -show_entries format=duration -of csv=p=0 "$ie" | cut -d. -f1)
  fa=$(probe -select_streams v:0 -count_packets -show_entries stream=nb_read_packets -of csv=p=0 "$io" | tr -d ,)
  fe=$(probe -select_streams v:0 -count_packets -show_entries stream=nb_read_packets -of csv=p=0 "$ie" | tr -d ,)
  aa=$(probe -select_streams a -show_entries stream=index -of csv=p=0 "$io" | wc -l)
  ae=$(probe -select_streams a -show_entries stream=index -of csv=p=0 "$ie" | wc -l)
  ta=$(probe -select_streams v:0 -show_entries stream=color_transfer -of csv=p=0 "$io" | tr -d ,)
  hdr_ok=yes
  if [ "$ta" = "smpte2084" ]; then
    te=$(probe -select_streams v:0 -show_entries stream=color_transfer,profile -of csv=p=0 "$ie")
    md=$(probe -select_streams v:0 -read_intervals "%+#2" -show_frames -show_entries frame_side_data=side_data_type -of csv=p=0 "$ie" | grep -c "Mastering display" || true)
    case "$te" in *"Main 10"*smpte2084*) [ "$md" -ge 1 ] || hdr_ok=no;; *) hdr_ok=no;; esac
  fi
  dd=$(( da > de ? da - de : de - da ))
  if [ -z "$da" ] || [ "$dd" -gt 2 ] || [ "$fa" != "$fe" ] || [ "$aa" != "$ae" ] || [ "$hdr_ok" != yes ]; then
    log "FAIL verify (left untouched): $rel | dur $da/$de frames $fa/$fe audio $aa/$ae hdr10 $hdr_ok"; bad=$((bad+1)); continue
  fi
  sa=$(stat -c %s "$orig"); se=$(stat -c %s "$enc")
  if [ "$DRY" = "--dry-run" ]; then log "DRY ok: $rel | $sa -> $se"; ok=$((ok+1)); continue; fi
  tmp="$(dirname "$orig")/.tdarr-swap.$b"
  cp --no-preserve=mode,ownership "$enc" "$tmp"
  if [ "$(sha256sum < "$enc")" != "$(sha256sum < "$tmp")" ]; then rm -f "$tmp"; log "FAIL copy checksum: $rel"; bad=$((bad+1)); continue; fi
  chown 1000:1000 "$tmp"; chmod 664 "$tmp"; touch -r "$orig" "$tmp"
  mv "$tmp" "$orig"            # atomic rename over the original: the original is DELETED (user, Nov 9)
  rm -f "$enc"
  echo "$rel" >> "$DONE_LIST"
  log "SWAPPED $rel | $sa -> $se bytes ($(( 100 - se * 100 / sa ))% smaller) | original deleted"
  ok=$((ok+1))
done < <(find "$SRC_DIR" -type f \( -name "*.mkv" -o -name "*.mp4" \) -print0 | sort -z)
find "$SRC_DIR" -mindepth 1 -type d -empty -delete 2>/dev/null || true
log "run done: $ok swapped/ok, $bad failed/skipped ($SRC_DIR)"
