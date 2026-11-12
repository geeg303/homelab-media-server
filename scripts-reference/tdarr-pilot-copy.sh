#!/usr/bin/env bash
# Copy the pilot episodes from disk1 to /scratch (read-only use of disk1; originals untouched). Runs in tmux 'pilotcopy'.
set -euo pipefail
SRC=/mnt/disk1/media/tv
DST=/scratch/tdarr/pilot-input
LOG=/var/log/migrate/tdarr-pilot-copy.log
mkdir -p "$DST/h264" "$DST/hevc"
copy() {  # $1 = library subdir, $2 = path under media/tv
  mkdir -p "$DST/$1/$(dirname "$2")"
  ionice -c3 cp --preserve=timestamps "$SRC/$2" "$DST/$1/$2"
  echo "$(date +%T) copied [$1] $2 ($(stat -c %s "$DST/$1/$2") bytes)" >> "$LOG"
}
echo "=== $(date -Is) pilot copy start" >> "$LOG"
copy h264 "Show 23/Season 1/Show 23 - S01E07 - Episode Bluray-1080p Remux.mkv"
copy h264 "Show 47/Season 3/Show 47 - S03E16 - Episode Bluray-1080p Remux.mkv"
copy h264 "Show 20/Season 3/Show 20 - S03E08 - Episode WEBDL-1080p.mkv"
copy h264 "Show 108/Season 4/Show 108 - S04E06 - Episode Bluray-1080p Remux.mkv"
copy h264 "Show 20/Season 3/Show 20 - S03E07 - Episode WEBDL-1080p.mkv"
copy hevc "Show 09/Season 2/Show 09 - S02E09 - Episode Bluray-1080p Remux.mkv"
copy hevc "Show 09/Season 2/Show 09 - S02E13 - Episode Bluray-1080p Remux.mkv"
copy hevc "Show 76/Season 1/Show 76 - S01E05 - Episode Bluray-2160p.mkv"
chown -R 1000:1000 "$DST"
mkdir -p /scratch/tdarr/output /scratch/tdarr/cache && chown 1000:1000 /scratch/tdarr/output /scratch/tdarr/cache
echo "=== $(date -Is) pilot copy done: $(find "$DST" -type f | wc -l) files, $(du -sb "$DST" | cut -f1) bytes" >> "$LOG"
