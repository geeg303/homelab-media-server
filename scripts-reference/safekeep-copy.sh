#!/usr/bin/env bash
# Second copy of likely-irreplaceable personal folders onto NVMe /scratch/safekeep (NTFS mounted READ-ONLY).
set -uo pipefail
mkdir -p /mnt/ro/sdc /mnt/ro/sdd /mnt/ro/sde
mount -t ntfs3 -o ro /dev/disk/by-uuid/DBF105B5037AE18C /mnt/ro/sdc
mount -t ntfs3 -o ro /dev/disk/by-uuid/F90BE72FDA7942A2 /mnt/ro/sdd
mount -t ntfs3 -o ro /dev/disk/by-uuid/FDE7457EF6BF31A5 /mnt/ro/sde
D=/scratch/safekeep
rsync -aHAX --info=progress2 "/mnt/ro/sdc/pc-backup folder" "$D/sdc/"
rsync -aHAX --info=progress2 "/mnt/ro/sde/personal project folder" "/mnt/ro/sde/Music" "$D/sde/"
rsync -aHAX --info=progress2 "/mnt/ro/sdd/Music" "$D/sdd/"
echo "== verify (checksum, dry-run) =="
for p in "sdc/pc-backup folder" "sde/personal project folder" "sde/Music" "sdd/Music"; do
  disk=${p%%/*}; name=${p#*/}
  n=$(rsync -rc --dry-run --itemize-changes "/mnt/ro/$disk/$name/" "$D/$disk/$name/" | wc -l)
  echo "$p: differences=$n"
done
chown -R 1000:1000 "$D"
umount /mnt/ro/sdc /mnt/ro/sdd /mnt/ro/sde
echo "SAFEKEEP DONE $(date -Is)"
