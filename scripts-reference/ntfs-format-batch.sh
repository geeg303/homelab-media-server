#!/usr/bin/env bash
# ntfs-format-batch: ⚠️ DESTRUCTIVE. Formats the 3 old NTFS source drives as ext4 and adds them to the /data pool.
# Approved by user Nov 16 06:1x, naming each drive: "format SERIAL-SDD SERIAL-SDB SERIAL-SDE" (after "2. B" = format + add to pool).
# Each drive is gated on its round's verify log (TOTAL differences=0 with the expected folder count), serial match, SMART health.
set -euo pipefail
exec > >(tee -a /var/log/migrate/format-ntfs.log) 2>&1
echo "=== $(date -Is) ntfs-format-batch start"
# serial:label:round:expected_folders:old_mount
MAP="SERIAL-SDD:disk7:3:71:/mnt/mig/sdd SERIAL-SDB:disk8:4:234:/mnt/mig/sdb SERIAL-SDE:disk9:5:33:/mnt/mig/sde"
NTFY_TOPIC=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
ntfy(){ curl -fsS -m 10 -H "Title: box: $1" -H "Priority: ${3:-default}" -d "$2" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null || true; }
fail(){ echo "ABORT: $*"; ntfy "Old-drive format ABORTED" "$* (nothing further formatted). Log: /var/log/migrate/format-ntfs.log" urgent; exit 1; }
dev_of(){ local l; l=$(ls /dev/disk/by-id/ata-*_"$1" 2>/dev/null | grep -v -- -part || true); if [ -n "$l" ]; then readlink -f "$l"; fi; }

# ---------- global gates (before any write)
if pgrep -x rsync >/dev/null; then fail "an rsync is running"; fi
for u in migrate-round3 migrate-round4 migrate-round5; do if systemctl is-active --quiet "$u"; then fail "$u still running"; fi; done
MEMBERS=""; for l in disk1 disk2 disk3 disk4 disk5 disk6 backup scratch; do MEMBERS="$MEMBERS $(readlink -f /dev/disk/by-label/$l)"; done
for pair in $MAP; do
  IFS=: read -r s lab r want old <<<"$pair"; d=$(dev_of "$s")
  if [ -z "$d" ]; then fail "$s not present"; fi
  if [ "$(lsblk -dno SERIAL "$d")" != "$s" ]; then fail "$d serial mismatch for $s"; fi
  case "$MEMBERS " in *" ${d}"[0-9]*|*" $d "*) fail "$s resolves to an existing ext4 member ($d)";; esac
  if ! grep -q "^ROUND${r} VERIFY TOTAL differences=0 folders=${want}$" /var/log/migrate/round${r}-verify.log; then fail "$s: round $r verify line missing or not 0/$want"; fi
  # smartctl's exit code is a bitmask (32 = some attribute was below threshold IN THE PAST, e.g. a hot day); judge the text
  H=$(smartctl -d sat -H "$d" || true); if ! grep -q "self-assessment test result: PASSED" <<<"$H"; then fail "$s SMART health not PASSED"; fi
  A=$(smartctl -d sat -A "$d" || true); for id in 5 197 198; do v=$(echo "$A" | awk -v i=$id '$1==i{print $10}'); if [ "${v:-x}" != 0 ]; then fail "$s attribute $id = ${v:-missing}"; fi; done
  if [ -e /dev/disk/by-label/$lab ]; then fail "label $lab already exists"; fi
  if grep -q " /mnt/$lab " /etc/fstab; then fail "/mnt/$lab already in fstab"; fi
  # the only thing allowed to be mounted from it is its own read-only NTFS migration mount
  m=$(findmnt -rno TARGET,OPTIONS -S "${d}2" || true)
  if [ -n "$m" ]; then case "$m" in "$old ro,"*) ;; *) fail "$s: unexpected mount: $m";; esac; fi
  if findmnt -rno SOURCE | grep -v "^${d}2$" | grep -q "^${d}"; then fail "$s ($d) has another partition mounted"; fi
  echo "gate ok: $s → $lab ($d) · round $r verified 0/$want · SMART PASSED"
done
ntfy "Old-drive format starting" "user's OK: format SERIAL-SDD SERIAL-SDB SERIAL-SDE. All gates passed (rounds 3/4/5 verified 0 differences). Formatting as disk7/8/9 (~5 min)." high

# ---------- per disk
cp -a /etc/fstab /etc/fstab.bak-$(date +%Y%m%d-%H%M)-ntfsfmt
DONE=""
for pair in $MAP; do
  IFS=: read -r s lab r want old <<<"$pair"; d=$(dev_of "$s")
  if [ "$(lsblk -dno SERIAL "$d")" != "$s" ]; then fail "$d serial mismatch for $s (re-check)"; fi
  echo "--- $s → $lab on $d"
  if mountpoint -q "$old"; then umount "$old"; fi
  if findmnt -rno SOURCE | grep -q "^${d}"; then fail "$s still mounted after umount"; fi
  wipefs -a "$d"; sgdisk -Z "$d"
  sgdisk -n1:0:0 -t1:8300 -c1:"$lab" "$d"; partprobe "$d"; udevadm settle
  p=${d}1; if [ ! -b "$p" ]; then fail "$p missing after partitioning"; fi
  mkfs.ext4 -q -F -m 0 -T largefile -L "$lab" "$p"
  uuid=$(blkid -s UUID -o value "$p"); if [ -z "$uuid" ]; then fail "$s no UUID"; fi
  mp=/mnt/$lab
  if [ ! -d "$mp" ]; then mkdir "$mp"; fi
  if mountpoint -q "$mp"; then fail "$mp already a mountpoint"; fi
  if [ -n "$(ls -A "$mp")" ]; then fail "$mp not empty"; fi
  chattr +i "$mp"
  echo "UUID=$uuid  $mp  ext4  defaults,noatime,nofail,x-systemd.device-timeout=30s  0 2" >> /etc/fstab
  systemctl daemon-reload
  if findmnt --verify --tab-file /etc/fstab 2>&1 | grep -qE "^\s*\[E\]"; then fail "fstab verify error after $lab"; fi
  mount "$mp"; if ! mountpoint -q "$mp"; then fail "$mp did not mount"; fi
  if ! { touch "$mp/.rw-test" && rm "$mp/.rw-test"; }; then fail "$mp not writable"; fi
  mkdir -p "$mp/media/tv" "$mp/media/movies" "$mp/media/music"
  chown -R 1000:1000 "$mp"
  echo "ok: $lab $(df -h --output=size,avail "$mp" | tail -1) reserved=$(tune2fs -l "$p" | awk -F: '/Reserved block count/{gsub(/ /,"",$2);print $2}')"
  rmdir "$old" 2>/dev/null || true
  DONE="$DONE $lab"
done

# ---------- pool: add disk7-9 (runtime + fstab)
B=$(python3 -c "import os; print(os.getxattr('/data/.mergerfs','user.mergerfs.branches').decode())")
NEWB="/mnt/disk1:/mnt/disk2:/mnt/disk3:/mnt/disk4:/mnt/disk5:/mnt/disk6:/mnt/disk7:/mnt/disk8:/mnt/disk9"
python3 -c "import os,sys; os.setxattr('/data/.mergerfs','user.mergerfs.branches',sys.argv[1].encode())" "$NEWB"
echo "pool branches: $(python3 -c "import os; print(os.getxattr('/data/.mergerfs','user.mergerfs.branches').decode())")"
python3 - <<'PY'
p = "/etc/fstab"; s = open(p).read()
old = "/mnt/disk1:/mnt/disk2:/mnt/disk3:/mnt/disk4:/mnt/disk5:/mnt/disk6  /data"
assert s.count(old) == 1, "pool line not found"
s = s.replace(old, "/mnt/disk1:/mnt/disk2:/mnt/disk3:/mnt/disk4:/mnt/disk5:/mnt/disk6:/mnt/disk7:/mnt/disk8:/mnt/disk9  /data")
s = s.replace("x-systemd.requires-mounts-for=/mnt/disk6  0 0", "x-systemd.requires-mounts-for=/mnt/disk6,x-systemd.requires-mounts-for=/mnt/disk7,x-systemd.requires-mounts-for=/mnt/disk8,x-systemd.requires-mounts-for=/mnt/disk9  0 0")
s = s.replace("# mergerfs pool over disk1-6 (migration finished Nov 16;", "# mergerfs pool over disk1-9 (migration finished Nov 16; disk7-9 = ex-NTFS SERIAL-SDD/SERIAL-SDB/SERIAL-SDE;")
open(p, "w").write(s)
PY
systemctl daemon-reload
if findmnt --verify --tab-file /etc/fstab 2>&1 | grep -qE "^\s*\[E\]"; then fail "fstab verify error after pool edit"; fi
grep -c "disk9" /etc/fstab
df -h --output=size,used,avail /data | tail -1

# ---------- monitoring (Kuma "Mount /mnt/…" push monitors; rotates all mount tokens; full list)
/usr/local/sbin/kuma-mounts /scratch /mnt/disk1 /mnt/disk2 /mnt/disk3 /mnt/disk4 /mnt/disk5 /mnt/disk6 /mnt/disk7 /mnt/disk8 /mnt/disk9 /mnt/backup /data || echo "WARN: kuma-mounts failed (formats are fine)"
lsblk -o NAME,SIZE,LABEL,MOUNTPOINT,SERIAL | grep -E "disk[7-9]|NAME"
echo "=== $(date -Is) ntfs-format-batch done:$DONE"
ntfy "Old drives formatted + in the pool" "Formatted, mounted and added to /data:$DONE (SERIAL-SDD/SERIAL-SDB/SERIAL-SDE). Pool now $(df -h --output=size /data | tail -1 | tr -d ' ')." high
