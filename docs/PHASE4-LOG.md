# Phase 4 log — box (192.0.2.242)

## Done (non-destructive, approved)
- Temporary sudo file `/etc/sudoers.d/90-hermes-temp` is in place (created by user). **Remove it at the end of Phase 4.**
- Installed: smartmontools 7.5, iw 6.17, vainfo 2.22, intel-media-va-driver-non-free 26.1.2, iperf3 3.20, hdparm 9.65, zstd 1.5.7
- Root LV +200G: `/` is now 295G (12G used)
- Timezone set to Region/City
- sleep/suspend/hibernate/hybrid-sleep targets masked
- Wi-Fi power save off: `/etc/modprobe.d/iwlmvm-nopowersave.conf` (power_scheme=1) + `wifi-powersave-off.service` (enabled). `iw get power_save` reports **off**. initramfs rebuilt.
- Regulatory domain set to US at runtime (`iw reg set US`). Netplan persistence is still pending.

## Verified facts
- vainfo (iHD 26.1.2): H.264, HEVC Main/Main10/Main12/422/444 encode (EncSlice/EncSliceLP); VP9 encode (LP); **AV1Profile0 = VLD only (decode)**. Decision: hevc_qsv only.
- Wi-Fi: 5 GHz ch 40 (5200 MHz), 80 MHz, HE 2x2, RX 720.6 / TX 612.5 Mb/s PHY, signal −51 dBm (avg −49), 253 TX retries / 0 failed in 28 min. Reg domain was `00` (world) before the change.
- Scan: example-ssid-2g (ch 1, −46), **example-ssid (ch 40, −47)**, **example-ssid-6g (6135 MHz, −53)**, neighbor-ssid (ch 153, −86). The 5 GHz band is clean.
- NVMe safety: `/`, `/boot`, `/boot/efi` are all on nvme1n1 (…XXXX). The by-id link `nvme-CT500P3PSSD8_NVME-SERIAL-2 -> nvme0n1`. Both UEFI entries (Boot0006 Ubuntu, Boot0000) point at PARTUUID 3039aaa9… = nvme1n1p1. **No boot entry references nvme0n1** (PARTUUID f06a0655…). The old VG `ubuntu-vg` is active on nvme0n1p3.
- SMART: every drive PASSED. 0 reallocated / 0 pending / 0 offline-uncorrectable / 0 reported-uncorrect on all 5 HDDs; NVMe 0 media errors.
- ~~USB disks are in standby when idle~~ **Retracted:** `hdparm -C` always reads "standby" through the JMS567, so it can't detect spin-down. No USB resets in the kernel log this boot.
- NTFS contents: about 28 TiB used across the 5 disks (see chat report).

## Session 2 (user away; standing permission for non-destructive work)
- Docker CE 29.9.3 + Compose v5.7.0, log rotation (`local`, 10m×3), `docker.service` ordered after `data.mount`/`scratch.mount` (Wants, not Requires). `user` added to the docker group. Network `media` created.
- Tailscale 1.104.5 installed, `tailscaled` active. **Login pending** (URL given to user).
- Netplan consolidated into `/etc/netplan/01-media-server.yaml` (example-ssid, `regulatory-domain: US`, I219 optional). Old files are in `/root/netplan-backup/`. Applied with a 240 s auto-rollback, then the rollback was cancelled. Verified: country US, 5200 MHz, −51 dBm, power save off, 192.0.2.242.
- ⚠️ nvme0n1 (serial NVME-SERIAL-2) wiped → ext4 `scratch` (UUID cd1088ae-783d-4c9f-88bf-dc72fcd7b3c8) → `/scratch` in fstab (`nofail`). The underlying mountpoint is `chattr +i`. Folders: sabnzbd/incomplete, tdarr/{cache,output}, plex-transcode, backups/config/{daily,weekly}, safekeep. Boot entries untouched (they only ever pointed to nvme1n1).
- Compose stacks written to `/opt/media/stacks/{core,plex,tdarr,ops}` + `/opt/media/dockge`; every file passes `docker compose config`. All images pulled. Recyclarr is pinned to `:8` (no `latest` tag exists).
- **Running:** dockge (:5001), uptime-kuma (:3001), homepage (:3000, link-only services.yaml), socket-proxy (read-only), diun (watching via proxy, ntfy test sent).
- **Not started (need /data):** core, plex, tdarr stacks.
- ntfy topic: `box-media-dfd7f76dc5da4040` on ntfy.sh (subscribe in the ntfy app).
- Backup: `/usr/local/sbin/media-config-backup` + timer at 04:30 daily. Keeps 14 daily and 8 weekly (Sunday) copies in `/scratch/backups/config`, mirrored to `/data/backups/config` when the pool is mounted. Stops running stacks, then restarts them. Test run OK. Archives are mode 600.
- `usb-watchdog.service`: follows the kernel log; on a USB 2-4 reset/disconnect or disk I/O error it SIGSTOPs rsync and sends a high-priority ntfy alert.
- `mount-push.timer` (every 2 min) reads `/etc/media-server/kuma-push.conf` (empty until Uptime Kuma push monitors exist).
- `safekeep-copy` (tmux `safekeep`): NTFS mounted **read-only** → `/scratch/safekeep` (pc-backup folder, personal project folder, both Music folders), then an rsync -rc verify.
- `spin-test` (tmux `spintest`) → `/var/log/spin-test.log`. Correction: `hdparm -C` "standby" readings are **not reliable** through the JMS567 (no ATA output registers), so the test measures first-read latency after idle instead.
- Read-only duplicate scan: 5 show folders overlap across disks; 5 identical episode files (17.3 GB).
- Migration plan drafted: `MIGRATION-PLAN.md`.

## 2026-11-08 — Round 2 complete, sda formatted
- Round 2 verify: 41/41 shows, `ROUND2 VERIFY TOTAL differences=0`, 0 USB/disk errors in 26 h. Finished ~10:05 PM (much faster than the 20–27 h estimate).
- ⚠️ 22:11 user: "Format sda". sda (IronWolf SERIAL-DISK2) unmounted from /mnt/mig/sda (ro ntfs3), wiped, GPT + 1 partition, `mkfs.ext4 -m 0 -T largefile -L disk2` (UUID 658f115b-8c7e-41ec-874d-6188bf06a9a4), fstab nofail line, `chattr +i /mnt/disk2`, mounted + write test, `media/{tv,movies}` created (1000:1000). 7.998 TB usable, SMART PASSED. Log: /var/log/migrate/format-sda.log
- Uptime Kuma push monitor "Mount /mnt/disk2" (cloned from disk1, ntfy) UP; migration tile shows R2 ✅ and the next step.
