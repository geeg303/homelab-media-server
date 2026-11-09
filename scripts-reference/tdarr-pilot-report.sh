#!/usr/bin/env bash
# Tdarr HDR pilot report helper (read-only on media; writes only to /scratch/tdarr/compare). Run as root on the box.
# Prints per-file results (size, duration, audio tracks, HDR metadata) and makes same-frame tonemapped crops
# (no seeking: both files decoded from the start, frame #N), in a throwaway container capped at 6 GB RAM.
set -euo pipefail
N=${N:-40000}
IMG=$(docker inspect -f '{{.Config.Image}}' tdarr-node)
cat > /scratch/tdarr/.report.sh <<'EOS'
#!/bin/sh
FF="/usr/local/bin/ffmpeg -nostdin"; FP=/usr/local/bin/ffprobe; N=$1
TM="zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
CROP="crop=1280:720:1280:444"
lab() { echo "drawtext=text='$1':x=20:y=20:fontsize=40:fontcolor=white:box=1:boxcolor=black@0.6"; }
find /t/pilot-input/hdr -type f -name "*.mkv" | sort > /tmp/list
while IFS= read -r i; do
  b=$(basename "$i"); o=$(find /t/output -type f -name "$b" | head -1); short=$(echo "$b" | cut -c1-45)
  if [ -z "$o" ]; then echo "RESULT $short | $(stat -c %s "$i") -> none"; continue; fi
  da=$($FP -v error -show_entries format=duration -of csv=p=0 "$i" | cut -d. -f1); dn=$($FP -v error -show_entries format=duration -of csv=p=0 "$o" | cut -d. -f1)
  aa=$($FP -v error -select_streams a -show_entries stream=index -of csv=p=0 "$i" | wc -l); an=$($FP -v error -select_streams a -show_entries stream=index -of csv=p=0 "$o" | wc -l)
  col=$($FP -v error -select_streams v:0 -show_entries stream=profile,pix_fmt,color_transfer,color_primaries -of csv=p=0 "$o")
  sd=$($FP -v error -select_streams v:0 -read_intervals "%+#2" -show_frames -show_entries frame_side_data=side_data_type -of csv=p=0 "$o" | tr ',' '\n' | grep -E "Mastering|Content light" | sort -u | tr '\n' '+')
  fa=$($FP -v error -select_streams v:0 -count_packets -show_entries stream=nb_read_packets -of csv=p=0 "$i" | tr -d ,); fn=$($FP -v error -select_streams v:0 -count_packets -show_entries stream=nb_read_packets -of csv=p=0 "$o" | tr -d ,)
  echo "RESULT $short | $(stat -c %s "$i") -> $(stat -c %s "$o") | dur $da/$dn | frames $fa/$fn | audio $aa/$an | out $col | hdr10-meta [$sd]"
  tag=$(echo "$b" | cut -d' ' -f1-2 | tr -cd 'A-Za-z0-9')
  $FF -v error -y -i "$i" -map 0:v:0 -vf "select=eq(n\,$N),$TM,$CROP" -frames:v 1 /t/compare/$tag-orig.png
  $FF -v error -y -i "$o" -map 0:v:0 -vf "select=eq(n\,$N),$TM,$CROP" -frames:v 1 /t/compare/$tag-new.png
  p=$($FF -i /t/compare/$tag-orig.png -i /t/compare/$tag-new.png -lavfi psnr -f null - 2>&1 | grep -oE 'average:[0-9.inf]+')   # before labels
  $FF -v error -y -i /t/compare/$tag-orig.png -i /t/compare/$tag-new.png -filter_complex "[0:v]$(lab ORIGINAL)[a];[1:v]$(lab 'HEVC q20')[b];[a][b]hstack" \
    /t/compare/$tag-hdr-compare.png && echo "COMPARE $tag-hdr-compare.png psnr $p"
  rm -f /t/compare/$tag-orig.png /t/compare/$tag-new.png
done < /tmp/list
EOS
docker run --rm --memory 6g --memory-swap 6g --entrypoint sh -v /scratch/tdarr:/t "$IMG" /t/.report.sh "$N" < /dev/null 2>&1 | grep -v '^libva'
rm -f /scratch/tdarr/.report.sh
