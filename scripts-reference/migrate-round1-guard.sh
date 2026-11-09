#!/usr/bin/env bash
set -uo pipefail
T=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
alert(){ curl -fsS -m 10 -H "Title: box migration" -H "Priority: high" -d "$1" "https://ntfy.sh/$T" >/dev/null || true; }
# wait up to 3h for safekeep to release the ro mounts
for i in $(seq 1 180); do
  tmux has-session -t safekeep 2>/dev/null || break
  findmnt -no TARGET /mnt/ro/sdd >/dev/null 2>&1 || break
  sleep 60
done
if findmnt -no TARGET /mnt/ro/sdd >/dev/null 2>&1; then
  if ! tmux has-session -t safekeep 2>/dev/null; then umount /mnt/ro/sdc /mnt/ro/sdd /mnt/ro/sde 2>/dev/null; fi
fi
findmnt -no TARGET /mnt/ro/sdd >/dev/null 2>&1 && { alert "Round 1 NOT started: sdd still held read-only by safekeep after 3h"; exit 1; }
# mount set: sdc ro, sda rw, sdd rw
mkdir -p /mnt/mig/{sdc,sda,sdd}
mountpoint -q /mnt/mig/sdc || mount -t ntfs3 -o ro,noatime /dev/disk/by-uuid/DBF105B5037AE18C /mnt/mig/sdc || { alert "R1 abort: sdc mount failed"; exit 1; }
mountpoint -q /mnt/mig/sda || mount -t ntfs3 -o rw,noatime /dev/disk/by-uuid/DAC5EAE19F16E58C /mnt/mig/sda || { alert "R1 abort: sda mount failed"; exit 1; }
chattr -i /mnt/mig/sdd 2>/dev/null
mountpoint -q /mnt/mig/sdd || mount -t ntfs3 -o rw,noatime /dev/disk/by-uuid/F90BE72FDA7942A2 /mnt/mig/sdd || { alert "R1 abort: sdd mount failed"; exit 1; }
for m in sda sdd; do
  mountpoint -q /mnt/mig/$m || { alert "R1 abort: /mnt/mig/$m not a mountpoint"; exit 1; }
  touch /mnt/mig/$m/.rwtest 2>/dev/null && rm -f /mnt/mig/$m/.rwtest || { alert "R1 abort: /mnt/mig/$m not writable (ro fallback?)"; exit 1; }
done
mkdir -p "/mnt/mig/sda/_from_sdc/TV Shows" "/mnt/mig/sdd/_from_sdc/TV Shows"
alert "Round 1 started: copying 4.31 TB from sdc to sda+sdd"
exec /usr/local/sbin/migrate-round1
