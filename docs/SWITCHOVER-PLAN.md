# Switch-over plan: from migration to the live pool (DRAFT, NEEDS APPROVAL)

Written Nov 8. Nothing in this file has been run. Every ⚠️ step needs its own explicit OK from user; formats need an OK **naming the disk**. Command chains stop at the first failure (`set -e` / `&&`). Disks are always selected by **serial / by-id**, never by `sdX`.

## ⭐ v2 layout: second enclosure + 5 × WD80EMAZ (user, Nov 8). Supersedes the 5-disk map and the old rounds 3–5

**Why:** 5 more 8 TB drives (WD80EMAZ white label, HGST-based, **CMR**, helium, mfd 10/2018, existing contents not needed) in a second identical enclosure (JMicron JMS567) arriving **Tue Nov 10**. Rounds 3–5 copy straight from the old NTFS disks onto empty new ext4 disks, one enclosure to the other, instead of rolling through a nearly full pool. Result: **8 data + 2 parity, ~64 TB data, ~34 TB free**, survives any 2 disk failures.

### Final disk map (10 disks)
| Role | Disk | Gets | Enclosure |
|---|---|---|---|
| disk1 | SERIAL-DISK1 BarraCuda (was sdc) | round 1+2 TV ✅ | A |
| disk2 | SERIAL-DISK2 IronWolf (sda) | empty → new downloads | A |
| disk3 | WD #1 (SERIAL-WD1) | **round 3: sdd's data** (7.21 TB) | B |
| disk4 | WD #2 | **round 4: sde's data** (7.91 TB, ~90 GB headroom, tight but fits) | B |
| disk5 | WD #3 | **round 5: sdb's data** (7.47 TB) | B |
| disk6 | WD #4 | empty | B |
| disk7 | SERIAL-SDD BarraCuda (sdd) | empty after round 3 | A |
| disk8 | SERIAL-SDE BarraCuda (sde) | empty after round 4 | A |
| parity1 | SERIAL-SDB IronWolf (sdb) | parity, after round 5 | A |
| parity2 | WD #5 | parity | B |

Two parity disks on different enclosures, CMR only. Serials of WD #2–#5 get filled in on Tuesday (the drive numbers user wrote on the labels ↔ serial).

### Steps
1. **Mon (after round 2 verify):** report the result. On "format sda": A2 → disk2, fstab line, Kuma push monitor. mergerfs/`/data` are **not** needed yet (rounds now write to single disks); they move to Part B.
2. **Tue: connect enclosure B** to a different rear USB 3 port, direct, no hub, while nothing is copying. Read-only only: `lsusb -t`, by-id serials, `smartctl -d sat -x` (hours, reallocated/pending), `blkid`/`lsblk -f` (what's on them). Map label numbers ↔ serials. If a WD isn't detected: 3.3 V power-disable pin (Kapton tape over pins 1–3), drive is fine. Add enclosure B to `usb-watchdog`.
3. **Tue night:** `smartctl -t long` on all 5 WDs in parallel (runs inside each drive, ~14–16 h, no USB bandwidth). Any failure or marginal attributes → that drive is left out and the map adjusted.
4. **Wed: ⚠️ format the WDs that passed** (one OK naming them; A2 block per disk, labels disk3–6/parity2), fstab + `chattr +i` mountpoints, Kuma monitors.
5. **Rounds 3, 4, 5 (sequential, same runner/rules as rounds 1–2):** sdd → disk3, sde → disk4, sdb → disk5, each with the per-show `rsync -rc` verify and differences=0, then **⚠️ format the old disk** after its own OK (sdd → disk7, sde → disk8, sdb → parity1). Expected: faster than the old ~2 days per round because reads (A) and writes (B) are on separate USB links; real rate gets measured in round 3.
6. **Then Part B** with these changes: mergerfs over `/mnt/disk*` (disk1–8), SnapRAID with `parity` + `2-parity` lines, `data d1..d8`, content files on 4 disks; first sync estimate gets re-measured (two bridges now).

## Original 5-disk map (superseded by v2 above, kept for reference)

| Role | Serial | Model | Today | Mount |
|---|---|---|---|---|
| disk1 | SERIAL-DISK1 | BarraCuda SMR (was sdc) | ext4 ✅ (round 1) | /mnt/disk1 |
| disk2 | SERIAL-DISK2 | IronWolf CMR (sda) | NTFS, emptied by round 2 | /mnt/disk2 |
| disk3 | SERIAL-SDD | BarraCuda SMR (sdd) | NTFS, emptied by round 3 | /mnt/disk3 |
| disk4 | SERIAL-SDE | BarraCuda SMR (sde) | NTFS, emptied by round 4 | /mnt/disk4 |
| parity1 | SERIAL-SDB | IronWolf CMR (sdb) | NTFS, emptied by round 5 | /mnt/parity1 |

Content decision (Nov 8): **Show 28 stays in TV Shows** (`media/tv/Show 28`).

---

## Part A: (v1; in v2 only A1 and A2 for sda apply before the new rounds, the pool moves to Part B)

Rounds 3–5 copy into "the pool", which means mergerfs is needed as soon as sda becomes disk2. The apps don't see `/data` yet (the temporary no-`/data` overrides are still in place), so mounting the pool early is safe.

### A1. 🔧 Install mergerfs (+ snapraid, which is used later)
```bash
sudo apt-get update && sudo apt-get install -y mergerfs snapraid   # Ubuntu: mergerfs 2.40.2, snapraid 13.0
```

### A2. ⚠️ DESTRUCTIVE (format, separate OK "format sda") — after the round 2 verify shows 0 differences
```bash
set -euo pipefail
D=/dev/disk/by-id/ata-ST8000VN004-3CP101_SERIAL-DISK2
findmnt -S /dev/disk/by-uuid/DAC5EAE19F16E58C && sudo umount /mnt/mig/sda    # old NTFS mount
if findmnt -rno SOURCE | grep -q "$(readlink -f $D)"; then echo "ABORT: a partition on this disk is still mounted"; exit 1; fi
sudo wipefs -a "$D" && sudo sgdisk -Z "$D" && sudo sgdisk -n1:0:0 -t1:8300 "$D"
sudo partprobe "$D" && sleep 2
sudo mkfs.ext4 -m 0 -T largefile -L disk2 "${D}-part1"
sudo blkid -s UUID -o value "${D}-part1"      # → <disk2-uuid> for fstab
```
The same block repeats for disk3 (SERIAL-SDD), disk4 (SERIAL-SDE) and parity1 (SERIAL-SDB, label `parity1`), each after its round verifies and with its own OK.

### A3. ⚠️ DESTRUCTIVE (fstab edit): add disk2 + the pool
```bash
set -euo pipefail
sudo cp /etc/fstab /etc/fstab.bak.$(date +%F-%H%M)
sudo mkdir -p /mnt/disk2 && sudo chattr +i /mnt/disk2        # empty mountpoint is immutable: a missing disk can't fill /
```
Append:
```fstab
UUID=<disk2-uuid>  /mnt/disk2  ext4  defaults,noatime,nofail,x-systemd.device-timeout=30s  0 2
/mnt/disk*  /data  fuse.mergerfs  cache.files=off,category.create=mfs,func.getattr=newest,dropcacheonclose=true,moveonenospc=true,minfreespace=100G,inodecalc=path-hash,fsname=mergerfs,nofail,x-systemd.requires-mounts-for=/mnt/disk1  0 0
```
```bash
sudo systemctl daemon-reload && sudo mount /mnt/disk2 && sudo touch /mnt/disk2/.rw && sudo rm /mnt/disk2/.rw
sudo mount /data && findmnt /data && df -h /data /mnt/disk1 /mnt/disk2
```
- `/mnt/disk*` is a glob, so disk3 and disk4 join the pool automatically after their fstab lines are added and `/data` is remounted (`sudo umount /data && sudo mount /data`, with no copy running at that moment).
- **`/mnt/parity1` must never match `/mnt/disk*`.** It doesn't, which is why parity has its own name.
- `category.create=mfs` puts each new file on the disk with the most free space. `minfreespace=100G` stops writing to a disk with less than 100 GB free. A non-path-preserving policy keeps Sonarr/Radarr moves atomic (rename instead of copy).

### A4. 🔧 Monitoring for each new disk
Add `/mnt/disk2 <push-url>` (later disk3, disk4, parity1, and `/data`) to `/etc/media-server/kuma-push.conf`, plus matching Push monitors in Uptime Kuma's "Storage & jobs" group.

---

## Part B: after round 5 (all media on disk1–4, sdb empty)

### B1. ⚠️ Format sdb → parity1 (separate OK "format sdb"), A2 block with label `parity1`
fstab:
```fstab
UUID=<parity1-uuid>  /mnt/parity1  ext4  defaults,noatime,nofail,x-systemd.device-timeout=30s  0 2
```

### B2. 🔧 SnapRAID config: `/etc/snapraid.conf`
```conf
# Parity on the CMR IronWolf (sdb, SERIAL-SDB)
parity /mnt/parity1/snapraid.parity

# Content files = SnapRAID's index of every file + checksum. Keep several copies on different disks.
content /var/snapraid/snapraid.content
content /scratch/snapraid/snapraid.content
content /mnt/disk1/snapraid.content
content /mnt/disk2/snapraid.content

data d1 /mnt/disk1/
data d2 /mnt/disk2/
data d3 /mnt/disk3/
data d4 /mnt/disk4/

# Not protected: downloads in progress/churn and junk
exclude /usenet/
exclude /lost+found/
exclude /tmp/
exclude .Trash-*/
exclude *.unrecoverable
exclude *.part
exclude *.!sync

autosave 500        # save progress every 500 GB during long syncs (a crash doesn't restart from zero)
```
```bash
sudo mkdir -p /var/snapraid /scratch/snapraid
sudo snapraid -c /etc/snapraid.conf status    # sanity check, reads only
```

### B3. 🔧 First sync (≈ 2–2.5 days, bridge-limited)
Run it in `tmux snapraid` with a log, ntfy when done:
```bash
sudo snapraid sync -l /var/log/snapraid/first-sync.log
```
- Estimate: parity ≈ 7.9 TB. Every parity byte means reading 4 data disks and writing 1 parity, all through the single USB bridge (about 200–250 MB/s combined, measured). That works out to about 45–55 h. The old 1–2 day estimate was too optimistic.
- Until the first sync finishes there is **no protection**. Avoid big changes during it (no Tdarr replacements, no mass imports).

### B4. 🔧 Nightly job: `/usr/local/sbin/snapraid-nightly` + timer at 03:00
```bash
#!/usr/bin/env bash
# diff -> safety gate -> sync -> (Sunday) scrub 8% -> smart. Alerts via ntfy, heartbeat to Uptime Kuma.
set -euo pipefail
CONF=/etc/snapraid.conf; DEL_LIMIT=100; LOG=/var/log/snapraid/nightly-$(date +%F).log
NTFY_TOPIC=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
notify(){ curl -fsS -m 10 -H "Title: snapraid" -H "Priority: ${2:-default}" -d "$1" "https://ntfy.sh/$NTFY_TOPIC" >/dev/null || true; }
trap 'notify "SnapRAID nightly FAILED on $(hostname), see $LOG" high' ERR
mkdir -p /var/log/snapraid
for m in /mnt/disk1 /mnt/disk2 /mnt/disk3 /mnt/disk4 /mnt/parity1; do
  mountpoint -q "$m" || { notify "SnapRAID skipped: $m not mounted" high; exit 1; }
done
set +e; snapraid -c $CONF diff > "$LOG.diff" 2>&1; rc=$?; set -e      # rc 0 = no changes, 2 = changes
[ $rc -eq 0 ] || [ $rc -eq 2 ] || { notify "snapraid diff error rc=$rc" high; exit 1; }
removed=$(awk '$2=="removed"{print $1}' "$LOG.diff"); removed=${removed:-0}
if [ "$removed" -gt "$DEL_LIMIT" ]; then
  notify "SnapRAID sync HELD: $removed files deleted since last sync (limit $DEL_LIMIT). Check before syncing." high; exit 1
fi
[ $rc -eq 2 ] && snapraid -c $CONF sync -l "$LOG"
[ "$(date +%u)" = 7 ] && snapraid -c $CONF scrub -p 8 -o 10 -l "$LOG.scrub"
snapraid -c $CONF smart >> "$LOG.smart" 2>&1 || true
PUSH=$(cat /etc/media-server/kuma-push-snapraid 2>/dev/null || true)
[ -n "$PUSH" ] && curl -fsS -m 10 "$PUSH?status=up&msg=removed=$removed" >/dev/null || true
```
- **Deletion gate:** if a disk drops or something mass-deletes, more than 100 removed files holds the sync. Syncing would bake the loss into parity. You check, then run the sync by hand.
- **Scrub:** every Sunday, re-reads 8% of the oldest-checked data and verifies checksums (bit-rot check). A full pass takes about 3 months.
- **Timing:** 03:00 finishes before the 04:30 config backup. A Kuma Push monitor "SnapRAID nightly" (interval 26 h) alerts if the job stops running.

### B5. 🔧 App switch-over (the apps get `/data`)
```bash
set -euo pipefail
findmnt /data >/dev/null                                            # pool must be mounted
sudo mkdir -p /data/usenet/complete/{tv,movies} /data/media/movies /data/backups/config
sudo chown -R 1000:1000 /data/usenet /data/media /data/backups && sudo chmod -R 2775 /data/usenet /data/media
for s in core plex tdarr; do
  cd /opt/media/stacks/$s
  sed -i '/^COMPOSE_FILE=compose.yaml:compose.nodata.yaml$/d' .env
  mv compose.nodata.yaml /opt/media/compose.nodata.$s.retired
  docker compose config -q && docker compose up -d
done
docker inspect -f '{{.Name}} {{range .Mounts}}{{.Source}} {{end}}' sonarr radarr sabnzbd plex tdarr tdarr-node bazarr
```
Then, app by app (each one verified before the next):
1. **SABnzbd:** Completed folder `/data/usenet/complete`, temporary folder `/scratch/sabnzbd/incomplete`. The categories `tv`/`movies` land in `complete/tv` and `complete/movies`. This clears Radarr's "/config/Downloads" health warning.
2. **Sonarr / Radarr:** root folders `/data/media/tv` and `/data/media/movies`. **Library Import** of the existing shows and movies with profile WEB-1080p / HD Bluray + WEB (see decision 1). Check that "Use Hardlinks instead of Copy" is on (the default).
3. **Plex:** libraries **Movies** → `/data/media/movies` and **TV Shows** → `/data/media/tv`. The first scan reads metadata for ~30 TB over USB and will take hours. Empty-trash and media-deletion stay off (already set).
4. **Bazarr:** paths are the same in all containers (`/data/...`), so nothing to map. Let it sync series and movies.
5. **Kometa:** `mv config.yml.pending config.yml`. First run on the Movies library only, check the collections and overlays, then TV. The exact run-once command gets checked against the LSIO image at that point.
6. **Seerr:** (public access is prepared: Tailscale Funnel enabled for the tailnet; Seerr already has applicationUrl `https://box.tailnet-example.ts.net`, local login off, trust proxy on. **Funnel stays OFF until the Seerr setup wizard is finished**, see below.) Add Sonarr (`http://sonarr:8989`, root `/data/media/tv`, WEB-1080p) and Radarr (`http://radarr:7878`, root `/data/media/movies`, HD Bluray + WEB), then sync Plex libraries.
   - After Seerr's setup is finished (`public.initialized: true` in settings.json): `sudo tailscale funnel --bg 5055`, test `https://box.tailnet-example.ts.net` from outside (must show the Plex sign-in, not /setup), add an Uptime Kuma HTTP monitor on the public URL.
7. **Tdarr:**
   - Libraries TV (`/data/media/tv`) and Movies (`/data/media/movies`) with flow `pilotHevcQsv`, cache `/scratch/tdarr/cache`.
   - Health check: CPU.
   - **Pilot only:** 5–10 files, node workers 2 GPU transcode + 1 CPU health check. user reviews the output in `/scratch/tdarr/output`. Only after her OK does the move step become "replace original + notify Sonarr/Radarr".
   - **Tdarr decisions (user, Nov 9, after the pilot):** quality **22** for 1080p H.264 → HEVC (pilot: 84% smaller, no visible loss); **re-encode existing HEVC** too, but only when video > 10 Mbps (pilot: ~35% smaller); **4K HDR10** gets its own flow (Main10, quality 20, HDR10 metadata kept, Dolby Vision skipped) — **approved by user Nov 9** after the HDR pilot (Show 76 67% / Show 16 76% smaller, frames identical by eye, HDR10 metadata verified). All flows now also check the output length matches the original (99.5–100.5%) and use a 5–95% size gate. Production flows = pilot flows with the final step changed from "move to /scratch/tdarr/output" to "replace original + notify Sonarr/Radarr", only after her OK.
8. **Maintainerr:** rules flag only; every action "do nothing".
9. **Homepage:** the Plex tile starts working once libraries exist (no change needed).
10. **Backups:** the 04:30 job starts mirroring to `/data/backups/config` by itself once `/data` is mounted.
11. **FileBrowser (user, Nov 8: read-write right away after the migration):** in the ops compose, replace `- /mnt/disk1:/storage/disk1:ro` with `- /data:/storage` (rw). In `/opt/media/config/filebrowser/config.yaml`, change the source to `path: "/storage"`, `name: "Pool (/data)"`. Then `docker compose up -d filebrowser`. ⚠️ Deletes there are immediate (no recycle bin) and bypass Plex/Sonarr; only SnapRAID (after the first sync) can bring files back.

### B6. Wrap-up
1. ⚠️ Remove the temporary sudo (user's PowerShell session or mine, then prove it's gone):
   `sudo rm /etc/sudoers.d/90-hermes-temp && sudo -k && ! sudo -n true` (the last part must **fail**)
2. Remove the empty migration mountpoints `/mnt/mig/*`, `/mnt/ro`, `/mnt/ntfscheck` (only after `findmnt` shows nothing mounted there).
3. `/scratch/safekeep` (personal folders) **stays** until user says otherwise.
4. Notion: tick the rows; PHASE4-LOG gets the final state.

---

## Decisions for user
1. **Sonarr/Radarr on import:** monitor the existing library? Options:
   - "Missing episodes only": fills gaps, may download a lot.
   - "None": just track what's there.
   - "Future episodes" (recommended to start): new episodes only, no backfill storm.
2. **Order of the heavy jobs after round 5** (they all compete for the one USB bridge). Recommended:
   - Plex scan first, so you can watch.
   - SnapRAID first sync next (about 2 days, Tdarr off).
   - Tdarr pilot after that.
3. **SnapRAID schedule:** nightly sync at 03:00 and weekly 8% scrub on Sundays. OK?
4. **Deletion gate:** hold the sync when more than **100** files were deleted since the last sync. OK, or another number?
5. **Pool fill:** disks end at about 94%, with `minfreespace=100G` per disk. New downloads have about 1.9 TB until Tdarr frees space. OK?
