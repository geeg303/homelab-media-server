#!/usr/bin/env bash
# tdarr-swap: replace library originals with verified Tdarr encodes. Originals are DELETED after verification
# (user, Nov 9: no holding copy). Every replaced path is recorded in $DONE_LIST and never replaced twice.
# Usage: tdarr-swap <encode-dir> [--dry-run]     e.g. tdarr-swap /scratch/tdarr/output-4k
# Nov 16: works for the whole /data pool (user: "Point it the whole pool").
#   - Pool library encodes keep their path relative to /data/media (tv/<show>/..., movies/<movie>/...): original = /data/media/<rel>.
#   - Older disk1 per-show libraries (legacy): original found by file name under /mnt/disk1/media/tv.
#   The rename happens on the REAL disk (mergerfs user.mergerfs.fullpath), next to the original, so it stays atomic.
# Per encode: verify (same duration ±2 s, video frame count within ±0.1% (min 2), same audio track count, HDR10 kept if the original is
# PQ/HDR10), copy encode next to the original as a temp file, check sha256, rename over the original, delete the encode.
set -euo pipefail
SRC_DIR=${1:?encode dir}; DRY=${2:-}
POOL=/data/media
LEGACY=/mnt/disk1/media/tv
DONE_LIST=/var/lib/media-server/tdarr-swapped.list
LOG=/var/log/media-server/tdarr-swap.log
LOCK=/run/tdarr-swap.lock
mkdir -p /var/log/media-server /var/lib/media-server
exec 9>"$LOCK"; flock -n 9 || { echo "already running"; exit 0; }
log(){ echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
if ! mountpoint -q /data; then log "ABORT: /data not mounted"; exit 1; fi
probe(){ docker exec tdarr-node /usr/local/bin/ffprobe -v error "$@"; }
# tdarr-node sees disk1 TV at /media/disk1/tv (legacy) and the pool's media at /media/pool; /scratch/tdarr at the same path
inpath(){ case "$1" in "$POOL"/*) echo "/media/pool/${1#$POOL/}";; "$LEGACY"/*) echo "/media/disk1/tv/${1#$LEGACY/}";; *) echo "$1";; esac; }
realpath_of(){ python3 -c 'import os,sys; print(os.getxattr(sys.argv[1], "user.mergerfs.fullpath").decode())' "$1" 2>/dev/null || echo "$1"; }
ok=0; bad=0
while IFS= read -r -d '' enc; do
  # skip files Tdarr may still be writing
  [ $(( $(date +%s) - $(stat -c %Y "$enc") )) -ge 120 ] || continue
  b=$(basename "$enc"); erel=${enc#$SRC_DIR/}
  case "$erel" in
    tv/*|movies/*)
      orig="$POOL/$erel"
      if [ ! -f "$orig" ]; then log "SKIP no original at $orig"; bad=$((bad+1)); continue; fi
      case "$erel" in tv/*) key=${erel#tv/};; *) key=$erel;; esac ;;
    *)
      orig=$(find "$LEGACY" -mindepth 2 -maxdepth 4 -type f -name "$b" -print -quit)
      if [ -z "$orig" ]; then log "SKIP no original on disk1: $b"; bad=$((bad+1)); continue; fi
      key=${orig#$LEGACY/} ;;
  esac
  if grep -qxF "$key" "$DONE_LIST" 2>/dev/null; then log "SKIP already replaced once: $key"; bad=$((bad+1)); continue; fi
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
  dd=$(( ${da:-0} > ${de:-0} ? ${da:-0} - ${de:-0} : ${de:-0} - ${da:-0} ))
  # frame tolerance = the flow's own frame check: +-0.1% of the original, at least 2 frames (user Nov 21: "That sounds good")
  # VC-1 remuxes and HDTV captures come out 1-6 frames off out of ~135k; a decoder hang loses thousands, so it still fails.
  fd=$(( ${fa:-0} > ${fe:-0} ? ${fa:-0} - ${fe:-0} : ${fe:-0} - ${fa:-0} )); ft=$(( ${fa:-0} / 1000 )); [ "$ft" -lt 2 ] && ft=2
  if [ -z "$da" ] || [ -z "$fa" ] || [ -z "$fe" ] || [ "$dd" -gt 2 ] || [ "$fd" -gt "$ft" ] || [ "$aa" != "$ae" ] || [ "$hdr_ok" != yes ]; then
    log "FAIL verify (left untouched): $key | dur $da/$de frames $fa/$fe audio $aa/$ae hdr10 $hdr_ok"; bad=$((bad+1)); continue
  fi
  real=$(realpath_of "$orig")       # /mnt/diskN/... for pool paths
  if [ ! -f "$real" ]; then log "FAIL no real path for $orig"; bad=$((bad+1)); continue; fi
  sa=$(stat -c %s "$real"); se=$(stat -c %s "$enc")
  if [ "$DRY" = "--dry-run" ]; then log "DRY ok: $key ($real) | $sa -> $se"; ok=$((ok+1)); continue; fi
  tmp="$(dirname "$real")/.tdarr-swap.$b"
  cp --no-preserve=mode,ownership "$enc" "$tmp"
  if [ "$(sha256sum < "$enc")" != "$(sha256sum < "$tmp")" ]; then rm -f "$tmp"; log "FAIL copy checksum: $key"; bad=$((bad+1)); continue; fi
  chown 1000:1000 "$tmp"; chmod 664 "$tmp"; touch -r "$real" "$tmp"
  mv "$tmp" "$real"            # atomic rename over the original on its own disk: the original is DELETED (user, Nov 9)
  rm -f "$enc"
  echo "$key" >> "$DONE_LIST"
  log "SWAPPED $key | $sa -> $se bytes ($(( 100 - se * 100 / sa ))% smaller) | original deleted | ${real%%/media/*}"
  ok=$((ok+1))
done < <(find "$SRC_DIR" -type f \( -name "*.mkv" -o -name "*.mp4" \) -print0 | sort -z)
find "$SRC_DIR" -mindepth 1 -type d -empty -delete 2>/dev/null || true
log "run done: $ok swapped/ok, $bad failed/skipped ($SRC_DIR)"
