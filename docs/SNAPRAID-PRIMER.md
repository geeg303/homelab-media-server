# SnapRAID: a primer for your box

## What it is, in one paragraph
SnapRAID keeps **one extra disk of "parity"** that lets you rebuild **any one** data disk if it dies. It is not live RAID: it takes a **snapshot** whenever `sync` runs (on your box, nightly at 03:00). Files are still plain files on normal ext4 disks, and each disk can be read on its own in any Linux PC. mergerfs merges the disks into one folder (`/data`); SnapRAID protects them. The two tools work side by side.

## How parity works (the short version)
Picture the 4 data disks lined up side by side. For every position, SnapRAID computes a checksum-like value (XOR-style math) across the 4 disks and writes it to the parity disk. If one disk dies, the missing piece = parity combined with the 3 survivors, so the dead disk can be recomputed bit for bit onto a new disk.

**Parity is only as fresh as the last sync.** A file added after last night's sync isn't protected until tonight. A file changed since then may not be recoverable if a disk dies in between.

## Your layout
| | Disk | Why |
|---|---|---|
| Data | disk1–4 (3 BarraCudas + 1 IronWolf) | media, ~94% full |
| Parity | parity1 = IronWolf SERIAL-SDB (CMR) | parity gets big sequential writes; CMR handles them much better than SMR |
| Content files | on /, /scratch, disk1, disk2 | SnapRAID's index (every file + checksum). Several copies so losing one disk can't lose the index |

## What it protects against ✅
- **One disk dying completely:** rebuild it onto a replacement (`snapraid fix -d d3`). Takes about a day for an 8 TB disk on your USB bridge.
- **Accidental deletes / overwrites since the last sync:** restore the old version (`snapraid fix -f "media/movies/Name (2010)/"`).
- **Silent bit rot:** the weekly scrub re-reads 8% of the data and checks it against stored checksums. Errors get reported and can be fixed from parity.

## What it does NOT protect against ❌
- **Two disks failing at once:** that needs 2 parity disks. With 1 parity you lose the data on both failed disks (only those two; the other disks are fine and readable).
- **The whole enclosure / USB bridge dying, theft, fire, ransomware:** SnapRAID is **not a backup**. It's in the same box as your data.
- **Changes after the last sync:** see above.
- **Things you exclude:** `/usenet/` (downloads in flight) is excluded on purpose, because it changes constantly and is re-downloadable.

## The commands you'll actually see
| Command | What it does | Who runs it |
|---|---|---|
| `snapraid status` | health summary: how much is synced, last scrub age, any errors | you, anytime (read-only) |
| `snapraid diff` | what changed since last sync (added / removed / updated) | the nightly job |
| `snapraid sync` | update parity to match the disks now | the nightly job |
| `snapraid scrub -p 8 -o 10` | verify 8% of data older than 10 days | the nightly job, Sundays |
| `snapraid smart` | SMART health + a failure-probability estimate per disk | the nightly job |
| `snapraid fix -d d2` | rebuild a dead disk onto its replacement | you + me, only after a failure |
| `snapraid fix -f <path>` | restore a deleted or damaged file | you + me |

## The safety gate (important)
If a disk drops off USB, all its files look **deleted** to SnapRAID. Syncing at that point would update parity to "those files are gone", which **destroys your ability to recover them**. So the nightly job:
1. Checks that all 5 disks are mounted. If any is missing, it skips and alerts you.
2. Runs `diff` first. If **more than 100 files were removed** since the last sync, it **holds the sync** and alerts you on ntfy (high priority).
3. You look: a real cleanup (for example, you deleted a show) means you run the sync by hand. A missing disk means we fix the disk first.

## Timeline on your box
- **First sync after round 5:** about 2–2.5 days (everything goes through one USB bridge). **No protection until it finishes.** Tdarr stays off, and no big imports.
- **Nightly sync:** usually minutes, depending on what changed that day.
- **Weekly scrub (Sunday):** a few hours. A full pass over all data takes about 3 months.

## Tdarr + SnapRAID
When Tdarr later replaces a file with a smaller HEVC version, parity covering that area is stale until the next sync. That's normal: the nightly sync catches up. The deletion gate only counts **removed** files. Replacements show up as **updated**, so a big Tdarr night won't trigger a false hold. One caveat: if Tdarr changes the container (e.g. `.avi` → `.mp4`), the old name counts as "removed". The pilot keeps MKV as MKV, so this mostly won't happen.

## If a disk dies (what we'd do)
1. Don't run sync (the nightly job will already refuse, because the disk is missing).
2. Put a new 8 TB disk in the same bay, format it, and mount it at the dead disk's path (e.g. `/mnt/disk3`).
3. `snapraid fix -d d3 -l fix.log`, then `snapraid check -d d3`, then `snapraid sync`.
4. Everything stays readable from the other disks during the rebuild. Plex only misses what was on the dead disk.

## Further reading
- Official manual: https://www.snapraid.it/manual
- FAQ (good on "is it a backup?"): https://www.snapraid.it/faq
