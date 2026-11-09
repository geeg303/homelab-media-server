# NTFS → ext4 rolling migration plan — v2, media-only (NEEDS APPROVAL)

v2 supersedes v1 entirely. Nothing has run. Every ⚠️ format waits for a separate, explicit per-disk OK from user.

## Content rule (user, Nov 5)
**Only TV and Movies migrate.** Show 55 and "Show 49" count as TV and are copied into `media/tv/` on the destination (sources on NTFS are never renamed or moved). Everything else — Recycle Bins, pc-backup folder, personal project folder, both Music folders, ROM archives, Android stubs — is **not migrated and is permanently erased when each source disk is formatted** (acknowledged by user). `/scratch/safekeep` is kept untouched. **Nov 8:** the Show 28 workout series (came from sdc's `TV Shows`, staged on sda in round 1) stays in `media/tv` (user).

## Measured inputs (exact, du -sb, TB = 10^12 bytes)
| Disk | Serial | Type | Media to migrate | Current NTFS free |
|---|---|---|---|---|
| sda | SERIAL-DISK2 | IronWolf CMR | TV: **5.287 TB** | 2.640 TB |
| sdb | SERIAL-SDB | IronWolf CMR | Movies: **7.472 TB** | 0.458 TB |
| sdc | SERIAL-DISK1 | BarraCuda SMR | TV Shows: **4.280 TB** | 3.690 TB |
| sdd | SERIAL-SDD | BarraCuda SMR | TV Shows + Show 55 + Show 49: **4.929 TB** | 2.694 TB |
| sde | SERIAL-SDE | BarraCuda SMR | TV Shows: **7.910 TB** | 0.047 TB |
| **total** | | | **29.878 TB (≈27.2 TiB)** | |

ext4 usable per disk (`-m 0 -T largefile`): ≈ **7.95 TB** (confirmed exactly after the first mkfs). 4 disks ≈ 31.8 TB.

**Bridge throughput (measured):** one disk 167–272 MB/s; two concurrent 101 MB/s each. Disk-to-disk copy estimates assume **75–100 MB/s**; the `-rc` verify re-reads both sides, so it takes about as long as the copy.

## Answer to the SnapRAID question
**No — 29.88 TB is NOT under the 27.2 TB (85%) target.** Dropping non-media saved only ~0.6 TB, because almost everything on these disks is TV/Movies.

**But parity right after the migration is still possible** at a higher fill: 29.88 TB fits on 4 data disks at **≈ 94% average**, leaving the 5th disk for parity. v2 is therefore ordered to end with **sdb (IronWolf SERIAL-SDB) empty**, becoming the SnapRAID parity disk immediately. Trade-offs:
- ~1.9 TB total free for new downloads at day one (mergerfs `minfreespace=100G` reserves 0.4 of that), growing as Tdarr shrinks the library.
- The no-parity alternative would leave ~9.9 TB free across 5 data disks, with parity only after Tdarr saves ~3 TB.
- sdb has 3 historical CRC (cable) errors, none new since monitoring began; attribute 199 stays watched.

## Rounds (v2) — ends with the IronWolf sdb empty for parity

> **Nov 8: rounds 3–5 changed.** A second enclosure with 5 × WD80EMAZ arrives Tue Nov 10; rounds 3–5 now copy sdd/sde/sdb straight onto new disks. See SWITCHOVER-PLAN.md, "v2 layout". Rules for every round below still apply unchanged.

disk1 = sdc, disk2 = sda, disk3 = sdd, disk4 = sde; **sdb → parity1**.
From round 2 on, copies go into the growing ext4 pool (mergerfs over finished disks, `mfs` balancing).

| Round | Source (emptied) | Media copied | Destination | Fits? | Copy ≈ | Verify ≈ | Then ⚠️ format as |
|---|---|---|---|---|---|---|---|
| 1 | sdc | 4.280 TB | **sda** `_from_sdc/` (6 shows, 1.997 TB) + **sdd** `_from_sdc/` (15 shows, 2.283 TB); both ntfs3 **rw**, sdc ro | sda free 2.64 / sdd free 2.69 ✔ | 12–16 h | 12–16 h | **disk1** (ext4) |
| 2 | sda | TV 5.287 + staged 1.997 = **7.284 TB** | disk1 | 7.95 ✔ (92%) | 20–27 h | 20–27 h | **disk2** |
| 3 | sdd | media 4.929 + staged 2.283 = **7.212 TB** | pool: disk1 free 0.67 + disk2 7.95 = 8.62 ✔ | ✔ | 20–27 h | 20–27 h | **disk3** |
| 4 | sde | **7.910 TB** | pool free 1.40 + disk3 7.95 = 9.35 ✔ | ✔ | 22–29 h | 22–29 h | **disk4** |
| 5 | sdb | **7.472 TB** | pool free 1.44 + disk4 7.95 = 9.39 ✔ | ✔ | 21–28 h | 21–28 h | **parity1** (separate OK) |

**Total ≈ 29.9 TB copied + checksum-verified ≈ 8–11 days**, plus ~1 h per round for SMART checks and formatting. End state: disks 1–4 at ≈ 94% (29.88 / 31.8 TB), sdb empty → SnapRAID parity; first `snapraid sync` adds ≈ 1–2 days.

## Rules for every round (user, Nov 5)
- **Copy only**: `rsync -rt` + excludes. Into fresh `_from_<disk>/` staging (round 1) or with `--ignore-existing` into the pool (rounds 2–5). **Never overwrite; name conflicts are reported, not resolved.** Expected: the 5 duplicate episodes (17.3 GB, identical checksums) in Show 36 / Show 57 / Show 109 / Show 55 / Show 110.
- Excludes: `$RECYCLE.BIN`, `System Volume Information`, `desktop.ini`, `Thumbs.db`; everything outside TV/Movies is simply never listed as a source.
- `chown -R 1000:1000` on each ext4 disk after its round.
- Verify = `rsync -rc --dry-run --itemize-changes` per show/movie folder: must be **0 differences**.
- SMART 5/187/197/198/199 re-checked between rounds; any change in 5/187/197/198 → stop. Baseline `/scratch/ntfsck/smart-baseline-pre-round1.txt` (all zeros; CRC 199: sdb=3, sde=1, historical).
- usb-watchdog pauses rsync (SIGSTOP) and sends a high-priority ntfy alert on any USB reset / I/O error.
- Chains stop at first failure. No ntfsfix, ever. **No format without a separate explicit OK naming that disk.**
- ~~Stacks core/plex/tdarr stay stopped until round 5 completes.~~ Changed by user Nov 8: core/plex/tdarr **running with NO /data mounts** (`compose.nodata.yaml` override wired in via `COMPOSE_FILE` in each stack's `.env`). `/data` is an empty `chattr +i` dir, so a stray bind mount fails instead of writing to `/`. After round 5 + mergerfs: delete the override files + `COMPOSE_FILE` lines, `docker compose up -d`.

## Round 1 — exact commands (run only after v2 approval)
```bash
# 1. SMART gate: scripted diff vs baseline; abort on any change in attrs 5/187/197/198
sudo smartctl -d sat -A /dev/sdX   # all five

# 2. Mounts: sdc stays ro; receivers rw + write test (abort if kernel fell back to ro)
sudo mount -t ntfs3 -o rw,noatime /dev/disk/by-uuid/DAC5EAE19F16E58C /mnt/mig/sda   # sda SERIAL-DISK2
sudo mount -t ntfs3 -o rw,noatime /dev/disk/by-uuid/F90BE72FDA7942A2 /mnt/mig/sdd   # sdd SERIAL-SDD
sudo touch /mnt/mig/sda/.rwtest && sudo rm /mnt/mig/sda/.rwtest    # same for sdd

# 3. Copy (tmux 'migrate', log /var/log/migrate/round1.log), one show at a time:
rsync -rt --info=progress2 --itemize-changes --ignore-existing \
  --exclude='$RECYCLE.BIN' --exclude='System Volume Information' \
  --exclude='desktop.ini' --exclude='Thumbs.db' \
  "/mnt/mig/sdc/TV Shows/<show>" "/mnt/mig/sda/_from_sdc/TV Shows/"   # 6 shows, 1.997 TB
  # ... remaining 15 shows → "/mnt/mig/sdd/_from_sdc/TV Shows/"        # 2.283 TB
# staging dirs are fresh → no overwrite possible in round 1

# 4. Verify per show; all output saved; required: differences=0
rsync -rc --dry-run --itemize-changes [same excludes] \
  "/mnt/mig/sdc/TV Shows/<show>/" "/mnt/mig/sda/_from_sdc/TV Shows/<show>/"

# 5. Report to user → wait for the explicit "format sdc" OK. Only then:
# ⚠️ wipefs / sgdisk / mkfs.ext4 on /dev/disk/by-id/<...SERIAL-DISK1>, selected by serial, never by sdX
```
Round 1 split, **as actually run** (from `round1-split.tsv` and `round1-verify.log`; the earlier list here was a stale draft):
- To **sda** (1.997 TB): Show 23, Show 57, Show 69, Show 76, Show 16, Show 28.
- The remaining 15 shows (2.283 TB) went to **sdd**: Show 98, Show 95, Show 46, Show 94, Show 30, Show 34, Show 106, Show 44, Show 04, Show 42, Show 29, Show 40, Show 93, Show 63, Show 24.

`pc-backup folder` was NOT copied (v2 content rule; verified absent from `_from_sdc`).

## Target layout on every ext4 disk
```
/mnt/diskN/media/tv/<Show>
/mnt/diskN/media/movies/<Movie>
```
Show 55 and Show 49 land in `media/tv/` during the sdd round. No `other/` tree exists in v2.

## Status of prior checks
- ntfsck v1.0.0 (upstream verified against Debian's source listing) `-C` + `-n`: **all five volumes clean, 0 errors** — logs `/scratch/ntfsck/<serial>.log`.
- safekeep: pc-backup folder, personal project folder, both Music folders live on `/scratch/safekeep`, checksum-verified (0 differences), kept until user says otherwise.
