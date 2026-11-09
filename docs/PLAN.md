# Media Server Stack — Phase 1–3 Report (box / 192.0.2.242)

Status: **read-only analysis complete. Nothing has been installed, modified, formatted, or deleted.**
Every command below is a *proposal* for Phase 4 and runs only after approval.

Legend: ⚠️ **DESTRUCTIVE** = formats, partitions, wipes, or edits fstab. 🔧 = modifies the system but is not destructive.

---

## 1. Findings (Phase 1)

All findings come from commands run on 192.0.2.242 over SSH as `user`. Sudo needs a password, so I couldn't read the root-only items. The ⛔ rows say what is still missing.

| Area | Finding |
|---|---|
| System | Dell **OptiPlex Micro Plus 7020**, BIOS 1.3.1 (`dmidecode` needs root; I read the same value from `/sys/class/dmi/id`) |
| OS / kernel | **Ubuntu 26.04.1 LTS (resolute)**, kernel **7.0.0-30-generic**, host TZ = **Etc/UTC** |
| CPU | **Intel Core i5-14500**: 14 cores (6P + 8E), 20 threads, up to 5.0 GHz |
| GPU | iGPU only: **Intel UHD Graphics 770** (PCI 8086:4680, Gen12 Xe-LP), driver **i915**. GuC 70.49.4 / **HuC 7.9.3 authenticated** (required for low-power HEVC encode). No discrete GPU. |
| /dev/dri | `card1` (group video, 44) and **`renderD128` exists** (group render, **GID 991**) |
| vainfo | ⛔ **Not installed**, so codec support is unverified. Intel's published specs for UHD 770: **H.264 decode+encode, HEVC 8/10-bit decode+encode (EncSlice + EncSliceLP), AV1 decode only (no AV1 encode)**. I'll confirm with `vainfo` in Phase 4. |
| Wi-Fi adapter | **Intel AX211 CNVi** (Wi-Fi 6E, 2×2), driver **iwlwifi / iwlmvm** |
| Wi-Fi link | SSID **example-ssid** via a UniFi AP (BSSID 02:00:00:00:00:01). Signal **−51 dBm**, quality 59/70 (good). Band is probably 5 GHz (from the SSID). ⛔ `iw` isn't installed, so I couldn't read link rate, band, or channel. |
| Wi-Fi power save | `iwlwifi power_save=N`, but **`iwlmvm power_scheme=2` (balanced)**, so firmware power saving is **on**. Not persistently disabled. |
| Wired NIC | **Intel I219-LM Ethernet (enp0s31f6) is present but unplugged** (no carrier) |
| Netplan | `/etc/netplan/00-installer-config.yaml` and `50-cloud-init.yaml` exist, both root-only (⛔ contents unread). The generated networkd config is DHCP on both enp0s31f6 and wlp0s20f3. The link dropped and re-associated at 02:05 (likely a `netplan apply`). Renderer: systemd-networkd + wpa_supplicant; no NetworkManager. |
| IP | **192.0.2.242/24 via DHCP** (dynamic lease), gateway/DNS 192.0.2.1. IPv6 ULA also present. |
| NVMe (OS) | **nvme1n1** Crucial P3 500 GB, serial **…XXXX**: EFI `2759-FA08` → /boot/efi, /boot ext4, LVM VG **ubuntu-vg-1**. Root LV is **only 100 G of a 462.7 G PV (~360 G unallocated)**. |
| NVMe 2 | **nvme0n1** Crucial P3 500 GB, serial **…XXXX**: holds a **second, unmounted Ubuntu install** (EFI `C909-FE09`, /boot, VG **ubuntu-vg** with a 100 G LV). Probably from an earlier install attempt. |
| NVMe naming | The fstab comments say /boot was on `nvme0n1p2`, but the UUIDs now resolve to nvme1n1. **Kernel NVMe numbering isn't stable across boots**, so use UUID / by-id only. |
| USB storage | **5 × 8 TB Seagate** in **one enclosure on one JMicron JMS567 bridge** (USB 3.0, 5 Gb/s, `usb-storage` BOT, UAS disabled by kernel quirk, LUNs 0–4 on one SCSI host): |
| | sda ST8000VN004 (IronWolf, CMR), serial SERIAL-DISK2, **NTFS** |
| | sdb ST8000VN004 (IronWolf, CMR), serial SERIAL-SDB, **NTFS** |
| | sdc ST8000DM004 (BarraCuda, **SMR**), serial SERIAL-DISK1, **NTFS** "extra" |
| | sdd ST8000DM004 (BarraCuda, **SMR**), serial SERIAL-SDD, **NTFS** "New Volume" |
| | sde ST8000DM004 (BarraCuda, **SMR**), serial SERIAL-SDE, **NTFS** "New Volume" |
| | 🚩 **All 5 USB drives are NTFS, not ext4.** All are unmounted; whether they hold data is unknown (checking needs a sudo mount). USB autosuspend is off for the enclosure (`power/control=on`). |
| Swap / RAM | 30 GiB usable RAM, 8 GiB swap file |
| Docker | **Not installed** (no docker, no compose plugin, no snap docker). Available: Docker CE repo for `resolute` ✅ (HTTP 200), Ubuntu `docker.io 29.1.3` + `docker-compose-v2 2.40.3` |
| Tailscale | Not installed. Official repo for `resolute` ✅ |
| Packages available | mergerfs 2.40.2, snapraid 13.0, intel-media-va-driver-non-free 26.1.2, vainfo, iw, smartmontools, intel-gpu-tools |
| Port conflicts | **None.** 32400, 8989, 7878, 6767, 8080, 8265, 8266, 9696, 5055, 8181, 5001, 3001, 3000 are all free. Only 22 (ssh) and 53 (resolved, loopback) are listening. Maintainerr will also need **6246** (free). |
| Firewall | UFW installed but `ENABLED=no`. AppArmor active. |
| User | **user UID 1000 / GID 1000**. Groups: adm, sudo, lxd, … (**not** in `render`/`video`/`docker`). Sudo requires a password. |
| Sleep | Suspend targets inactive (good; still mask them, see Phase 4) |

---

## 2. Recommendation (Phase 2)

**Confirmed: Docker Compose, with linuxserver.io images where they exist and official images otherwise.** Reasons, based on Phase 1:

- **iGPU passthrough is simple.** One i915 iGPU with `renderD128` means `devices: /dev/dri` is all Plex and Tdarr need. The LSIO Plex image ships its own Intel iHD driver, so host driver versions don't matter on a kernel this new (7.0).
- **Consistent PUID/PGID/UMASK** across the arrs makes hardlink/atomic-move permissions on the pool predictable.
- Ubuntu 26.04 is supported by **Docker's official apt repo** (verified), so I'd use `docker-ce` instead of the **snap** (snap confinement breaks bind mounts like `/data` and `/scratch`) or Ubuntu's `docker.io` (it lags).
- Keeping apps off the host means the OS can be rebuilt from `/opt/media/config` + compose files.

Image choices:

| App | Image | Why |
|---|---|---|
| Plex, Sonarr, Radarr, Bazarr, SABnzbd, Prowlarr, Tautulli, Kometa | `lscr.io/linuxserver/<app>` | LSIO image exists |
| Seerr | `ghcr.io/seerr-team/seerr` | official (merged Overseerr/Jellyseerr). Runs as UID 1000, needs `init: true` |
| Tdarr server / node | `ghcr.io/haveagitgat/tdarr`, `ghcr.io/haveagitgat/tdarr_node` | official, bundled ffmpeg with QSV |
| Recyclarr | `ghcr.io/recyclarr/recyclarr` | official (v8 config format) |
| Maintainerr | `ghcr.io/maintainerr/maintainerr` | official, data at `/opt/data`, port 6246 |
| Dockge | `louislam/dockge:1` | official |
| Uptime Kuma | `louislam/uptime-kuma:2` | official |
| Homepage | `ghcr.io/gethomepage/homepage` | official (needs `HOMEPAGE_ALLOWED_HOSTS`) |
| DIUN | `crazymax/diun` | official; notify-only. **No Watchtower.** |
| Docker socket proxy | `lscr.io/linuxserver/socket-proxy` | read-only socket for Homepage and DIUN, so they don't get root-equivalent access |

**Tailscale: install it on the host, not as a container.** It then covers every service, including host-networked Plex, Dockge, and SSH, with one node. It also keeps working when Docker is stopped or broken, which is when you most need remote access. A sidecar container only makes sense if you want individual services to appear as separate tailnet nodes.

---

## 3. Plan (Phase 3)

### 3.0 Prerequisite: sudo for Phase 4
I can't answer sudo password prompts. Pick one (Decision 6):
- (a) **Temporary passwordless sudo**, removed at the end of Phase 4. You run:
  `echo 'user ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/90-hermes-temp && sudo chmod 440 /etc/sudoers.d/90-hermes-temp`
  To remove it: `sudo rm /etc/sudoers.d/90-hermes-temp`
- (b) I give you each sudo block and you paste it into `ssh media-server-stack`.

### 3.1 Base OS 🔧

```bash
sudo timedatectl set-timezone Region/City
sudo apt-get update
sudo apt-get install -y iw vainfo intel-media-va-driver-non-free intel-gpu-tools \
  smartmontools mergerfs snapraid zstd rsync iperf3 jq
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target

# Verify the iGPU before anything else
vainfo --display drm --device /dev/dri/renderD128 | grep -E 'VAProfile(H264|HEVC|AV1)'
#  -> look for VAEntrypointEncSlice / EncSliceLP on HEVC Main / Main10 (encode)
#  -> AV1Profile0 should show VLD only (decode). If AV1 shows EncSlice, revisit Tdarr.

# Disk health (needs smartctl passthrough via the JMicron bridge)
for d in sda sdb sdc sdd sde; do sudo smartctl -d sat -H -A /dev/$d | grep -E 'result|Reallocated|Pending|Uncorrect|Power_On'; done
sudo smartctl -H -A /dev/nvme0n1; sudo smartctl -H -A /dev/nvme1n1
```

🔧 Grow the root LV (online, non-destructive; uses the ~360 G of free space in the VG). Docker images plus Plex metadata and thumbnails can easily exceed 100 G:
```bash
sudo lvextend -r -L +200G /dev/ubuntu-vg-1/ubuntu-lv     # -r grows ext4 too
```

### 3.2 Network

**Strong recommendation: plug in Ethernet** (I219-LM is idle). Keep Wi-Fi configured as a fallback; networkd gives Ethernet the lower route metric automatically.

**DHCP reservation, not a static IP.** On the UniFi controller, reserve `192.0.2.242` → Wi-Fi MAC **02:00:00:00:00:02**. If you go wired, reserve an address for the I219 MAC too (`ip link show enp0s31f6`), because a wired connection uses a different MAC and gets a different IP. I see no reason for a static IP; the router stays the single source of truth.

🔧 Netplan: consolidate into one file. First `sudo cat` both existing files so we keep the SSID and password, then:
```yaml
# /etc/netplan/01-media-server.yaml   (chmod 600; then move 00-installer-config.yaml and 50-cloud-init.yaml to /root/netplan-backup/)
network:
  version: 2
  renderer: networkd
  ethernets:
    enp0s31f6:
      dhcp4: true
      dhcp-identifier: mac
      optional: true            # don't block boot if unplugged
  wifis:
    wlp0s20f3:
      dhcp4: true
      dhcp-identifier: mac      # so the router's MAC reservation always matches
      regulatory-domain: "US"
      access-points:
        "example-ssid":
          password: "<from existing file>"
```
```bash
sudo netplan generate && sudo netplan try --timeout 120   # auto-reverts if SSH is lost
```

🔧 Disable Wi-Fi power save persistently, at both the driver and the interface level:
```bash
echo 'options iwlmvm power_scheme=1' | sudo tee /etc/modprobe.d/iwlmvm-nopowersave.conf   # 1 = always active (CAM)
sudo tee /etc/systemd/system/wifi-powersave-off.service >/dev/null <<'EOF'
[Unit]
Description=Disable Wi-Fi power save on wlp0s20f3
After=sys-subsystem-net-devices-wlp0s20f3.device netplan-wpa-wlp0s20f3.service
Wants=netplan-wpa-wlp0s20f3.service
[Service]
Type=oneshot
ExecStart=/usr/sbin/iw dev wlp0s20f3 set power_save off
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload && sudo systemctl enable --now wifi-powersave-off.service
sudo update-initramfs -u      # so the modprobe option applies at early boot
# after reboot: iw dev wlp0s20f3 get power_save  -> "Power save: off"
#               cat /sys/module/iwlmvm/parameters/power_scheme -> 1
```

**Bandwidth concerns (Wi-Fi):**
- At −51 dBm the AX211 should get several hundred Mb/s, but I couldn't read the PHY rate. I'll measure with `iw dev wlp0s20f3 link` and `iperf3` against a wired PC in Phase 4.
- **4K remux** runs 40–80 Mb/s average with peaks above 100 Mb/s. One stream is fine; two or three at once plus active downloads will contend for airtime. If the *client* is also on Wi-Fi via the same AP, each stream uses airtime twice.
- **Downloads**: SAB writes to NVMe, so Wi-Fi throughput caps download speed directly. Gigabit internet will not be reached over Wi-Fi.
- Tdarr and SnapRAID traffic stays local (USB/NVMe), so it doesn't touch the network.
- Wi-Fi blips make Plex sessions buffer and drop Tailscale peers briefly; containers keep running.

### 3.3 Storage

#### Target layout
| Device | Use | Mount |
|---|---|---|
| nvme1n1 (…XXXX, current OS) | OS, `/var/lib/docker`, **/opt/media/config/<app>**, **/opt/media/stacks** | `/` |
| nvme0n1 (…XXXX) | **/scratch**: SAB incomplete, Tdarr cache, Plex transcode, local backups | `/scratch` |
| USB disks | ext4 branches | `/mnt/disk1..4` (+ `/mnt/parity1` if SnapRAID) |
| mergerfs pool | TRaSH layout | `/data` |

```
/data
├── usenet/complete/{tv,movies}     # SAB "complete" + categories
└── media/{tv,movies}               # Sonarr / Radarr root folders, Plex libraries
/scratch
├── sabnzbd/incomplete
├── tdarr/{cache,output}
├── plex-transcode
└── backups/config
```
Usenet has no seeding, so the arrs **move** completed downloads. Because `usenet/complete` and `media` are on the same mergerfs pool and use a non-path-preserving create policy (`mfs`), mergerfs clones the path onto the same branch and the rename is **atomic, with no copy**. Hardlinks work the same way.

#### Step A: check the NTFS drives before anything else (read-only)
```bash
sudo mkdir -p /mnt/ntfscheck
for d in sda2 sdb2 sdc2 sdd2 sde2; do
  sudo mount -t ntfs3 -o ro /dev/$d /mnt/ntfscheck && df -h /mnt/ntfscheck | tail -1 && sudo ls /mnt/ntfscheck | head; sudo umount /mnt/ntfscheck
done
```
- **Empty / disposable** → format all of them (Step C).
- **Holds media you want** → rolling migration: format the emptiest disk as ext4, copy from the NTFS disks with `rsync -aHAX --info=progress2` plus a checksum verify (`rsync -c --dry-run`), then format the next one, and repeat. This needs at least one disk's worth of free space overall. We'd plan the exact order after seeing usage.

#### Step B: ⚠️ DESTRUCTIVE: wipe nvme0n1 (old Ubuntu install) → /scratch
```bash
# Safety checks first (read-only)
findmnt /  /boot  /boot/efi                         # must all be nvme1n1 / ubuntu-vg-1
sudo efibootmgr -v                                  # note entries pointing at the C909-FE09 ESP
SCRATCH=/dev/disk/by-id/nvme-CT500P3PSSD8_NVME-SERIAL-2   # by serial, NOT /dev/nvme0n1
ls -l "$SCRATCH"                                    # confirm it resolves to the non-root disk

# ⚠️ DESTRUCTIVE
sudo vgchange -an ubuntu-vg                         # deactivate the OLD VG (not ubuntu-vg-1!)
sudo wipefs -a "${SCRATCH}-part3" "${SCRATCH}-part2" "${SCRATCH}-part1"
sudo sgdisk --zap-all "$SCRATCH"
sudo sgdisk -n1:0:0 -t1:8300 -c1:scratch "$SCRATCH"
sudo mkfs.ext4 -L scratch "${SCRATCH}-part1"
sudo efibootmgr -b <bootnum-of-old-entry> -B       # remove the stale boot entry, if any
```

#### Step C: ⚠️ DESTRUCTIVE: USB drives → ext4 (selected by serial)
```bash
dev(){ echo /dev/$(lsblk -dno NAME,SERIAL | awk -v s="$1" '$2==s{print $1}'); }
# Proposed mapping (IronWolf = parity if SnapRAID is chosen; CMR is better for parity writes)
declare -A MAP=( [disk1]=SERIAL-SDB [disk2]=SERIAL-DISK1 [disk3]=SERIAL-SDD [disk4]=SERIAL-SDE [parity1]=SERIAL-DISK2 )
for name in "${!MAP[@]}"; do
  D=$(dev "${MAP[$name]}"); echo "$name -> $D"; lsblk "$D"     # eyeball before continuing
done
# ⚠️ DESTRUCTIVE: one disk at a time, after confirming the line above
for name in "${!MAP[@]}"; do
  D=$(dev "${MAP[$name]}")
  sudo wipefs -a "$D"; sudo sgdisk --zap-all "$D"
  sudo sgdisk -n1:0:0 -t1:8300 -c1:"$name" "$D"
  sudo mkfs.ext4 -m 0 -T largefile -L "$name" "${D}1"
done
sudo blkid | grep -E 'disk[1-4]|parity1|scratch'      # collect UUIDs for fstab
```
(Without SnapRAID: `disk5=SERIAL-DISK2` instead of `parity1`.)

#### Step D: ⚠️ DESTRUCTIVE (fstab edit): mounts
```bash
sudo cp /etc/fstab /etc/fstab.bak.$(date +%F)
sudo mkdir -p /mnt/disk{1..4} /mnt/parity1 /data /scratch
sudo chattr +i /mnt/disk{1..4} /mnt/parity1 /data /scratch   # empty mountpoints become immutable:
                                                             # if a disk is missing, writes FAIL instead of filling /
```
Append to `/etc/fstab`:
```fstab
# --- media server ---
UUID=<scratch-uuid>  /scratch     ext4  defaults,noatime,nofail,x-systemd.device-timeout=15s  0 2
UUID=<disk1-uuid>    /mnt/disk1   ext4  defaults,noatime,nofail,x-systemd.device-timeout=30s  0 2
UUID=<disk2-uuid>    /mnt/disk2   ext4  defaults,noatime,nofail,x-systemd.device-timeout=30s  0 2
UUID=<disk3-uuid>    /mnt/disk3   ext4  defaults,noatime,nofail,x-systemd.device-timeout=30s  0 2
UUID=<disk4-uuid>    /mnt/disk4   ext4  defaults,noatime,nofail,x-systemd.device-timeout=30s  0 2
UUID=<parity1-uuid>  /mnt/parity1 ext4  defaults,noatime,nofail,x-systemd.device-timeout=30s  0 2
/mnt/disk*  /data  fuse.mergerfs  cache.files=off,category.create=mfs,func.getattr=newest,dropcacheonclose=true,moveonenospc=true,minfreespace=100G,inodecalc=path-hash,fsname=mergerfs,nofail,x-systemd.requires-mounts-for=/mnt/disk1  0 0
```
```bash
sudo systemctl daemon-reload && sudo mount -a && findmnt -t ext4,fuse.mergerfs
sudo mkdir -p /data/usenet/complete/{tv,movies} /data/media/{tv,movies} \
  /scratch/{sabnzbd/incomplete,tdarr/cache,tdarr/output,plex-transcode,backups/config}
sudo chown -R 1000:1000 /data /scratch && sudo chmod -R 2775 /data /scratch
sudo mkdir -p /opt/media/{config,stacks} && sudo chown -R 1000:1000 /opt/media
```
🔧 Make Docker start after the mounts (ordering only; Docker still starts if a disk is missing):
```ini
# /etc/systemd/system/docker.service.d/10-mounts.conf
[Unit]
After=data.mount scratch.mount
Wants=data.mount scratch.mount
```

#### Optional: SnapRAID (Decision 3)
mergerfs is **not** redundancy: one dead disk = that disk's media is gone. SnapRAID with the IronWolf as parity gives single-disk recovery at the cost of 8 TB (~29 TiB usable vs ~36 TiB).
```ini
# /etc/snapraid.conf
parity  /mnt/parity1/snapraid.parity
content /var/snapraid/snapraid.content
content /mnt/disk1/.snapraid.content
content /mnt/disk2/.snapraid.content
data d1 /mnt/disk1
data d2 /mnt/disk2
data d3 /mnt/disk3
data d4 /mnt/disk4
exclude /usenet/
exclude *.partial
exclude /lost+found/
```
Nightly `snapraid diff && snapraid sync` (02:30) plus a weekly `snapraid scrub -p 8 -o 14`, both as systemd timers. If `diff` reports more than N deletions, the sync is skipped and an alert is sent, so a disconnect can't sync away parity.

### 3.4 Docker 🔧
```bash
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<'EOF'
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: resolute
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo tee /etc/docker/daemon.json >/dev/null <<'EOF'
{ "log-driver": "local", "log-opts": { "max-size": "10m", "max-file": "3" } }
EOF
sudo systemctl enable --now docker
sudo usermod -aG docker user          # docker group = root-equivalent; log out/in afterwards
docker network create media             # shared network for all stacks (except host-net Plex)
```

### 3.5 Tailscale (host) 🔧
```bash
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/resolute.noarmor.gpg | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/resolute.tailscale-keyring.list | sudo tee /etc/apt/sources.list.d/tailscale.list
sudo apt-get update && sudo apt-get install -y tailscale
sudo tailscale up            # prints a login URL. In the admin console: disable key expiry for "box", enable MagicDNS
```
- **No router port forwards** for any admin UI. Everything is reached at `http://box:<port>` over the tailnet or the LAN.
- In Plex → Settings → Network → **LAN Networks**: add `192.0.2.0/24,100.64.0.0/10` so your Tailscale devices count as local. Otherwise Plex treats them as remote streaming, which needs Plex Pass / Remote Watch Pass and gets remote-quality limits.

### 3.6 Compose stacks (Dockge-managed)

Layout: `/opt/media/stacks/{core,plex,tdarr,ops}/compose.yaml`. Dockge itself lives outside the stacks dir at `/opt/media/dockge`, so it doesn't manage itself.

`/opt/media/stacks/<stack>/.env` (same in each stack):
```dotenv
PUID=1000
PGID=1000
TZ=Region/City
RENDER_GID=991
```

**Dockge**: `/opt/media/dockge/compose.yaml`
```yaml
services:
  dockge:
    image: louislam/dockge:1
    container_name: dockge
    restart: unless-stopped
    ports: ["5001:5001"]
    environment:
      - DOCKGE_STACKS_DIR=/opt/media/stacks
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /opt/media/config/dockge:/app/data
      - /opt/media/stacks:/opt/media/stacks      # must be the identical path
```

**core**: `/opt/media/stacks/core/compose.yaml`
```yaml
x-lsio: &lsio
  restart: unless-stopped
  networks: [media]
  environment: &env
    PUID: ${PUID}
    PGID: ${PGID}
    TZ: ${TZ}
    UMASK: "002"

services:
  sabnzbd:
    <<: *lsio
    image: lscr.io/linuxserver/sabnzbd:latest
    container_name: sabnzbd
    ports: ["8080:8080"]
    volumes:
      - /opt/media/config/sabnzbd:/config
      - /data/usenet:/data/usenet
      - /scratch/sabnzbd:/scratch/sabnzbd

  prowlarr:
    <<: *lsio
    image: lscr.io/linuxserver/prowlarr:latest
    container_name: prowlarr
    ports: ["9696:9696"]
    volumes:
      - /opt/media/config/prowlarr:/config

  sonarr:
    <<: *lsio
    image: lscr.io/linuxserver/sonarr:latest
    container_name: sonarr
    ports: ["8989:8989"]
    volumes:
      - /opt/media/config/sonarr:/config
      - /data:/data                 # usenet + media on one mount -> atomic moves / hardlinks

  radarr:
    <<: *lsio
    image: lscr.io/linuxserver/radarr:latest
    container_name: radarr
    ports: ["7878:7878"]
    volumes:
      - /opt/media/config/radarr:/config
      - /data:/data

  bazarr:
    <<: *lsio
    image: lscr.io/linuxserver/bazarr:latest
    container_name: bazarr
    ports: ["6767:6767"]
    volumes:
      - /opt/media/config/bazarr:/config
      - /data/media:/data/media

  recyclarr:
    image: ghcr.io/recyclarr/recyclarr:latest
    container_name: recyclarr
    restart: unless-stopped
    networks: [media]
    user: "${PUID}:${PGID}"
    environment:
      TZ: ${TZ}
      CRON_SCHEDULE: "0 4 * * *"     # daily sync at 04:00
    volumes:
      - /opt/media/config/recyclarr:/config

networks:
  media: { external: true }
```

**plex**: `/opt/media/stacks/plex/compose.yaml`
```yaml
services:
  plex:
    image: lscr.io/linuxserver/plex:latest
    container_name: plex
    network_mode: host                      # 32400 + GDM/DLNA discovery
    restart: unless-stopped
    environment:
      PUID: ${PUID}
      PGID: ${PGID}
      TZ: ${TZ}
      VERSION: docker
      PLEX_CLAIM: ${PLEX_CLAIM}             # https://plex.tv/claim, valid 4 min, first start only
    devices: ["/dev/dri:/dev/dri"]
    volumes:
      - /opt/media/config/plex:/config
      - /data/media:/data/media
      - /scratch/plex-transcode:/transcode

  tautulli:
    image: lscr.io/linuxserver/tautulli:latest
    container_name: tautulli
    restart: unless-stopped
    networks: [media]
    ports: ["8181:8181"]
    environment: { PUID: "${PUID}", PGID: "${PGID}", TZ: "${TZ}" }
    volumes: ["/opt/media/config/tautulli:/config"]

  seerr:
    image: ghcr.io/seerr-team/seerr:latest
    container_name: seerr
    init: true
    restart: unless-stopped
    networks: [media]
    ports: ["5055:5055"]
    environment: { TZ: "${TZ}", LOG_LEVEL: info }
    volumes: ["/opt/media/config/seerr:/app/config"]   # chown 1000:1000 (image runs as node/1000)
    security_opt: ["no-new-privileges:true"]
    cap_drop: [ALL]

  kometa:
    image: lscr.io/linuxserver/kometa:latest
    container_name: kometa
    restart: unless-stopped
    networks: [media]
    environment:
      PUID: ${PUID}
      PGID: ${PGID}
      TZ: ${TZ}
      KOMETA_CONFIG: /config/config.yml
      KOMETA_TIME: "05:00"
    volumes: ["/opt/media/config/kometa:/config"]

  maintainerr:
    image: ghcr.io/maintainerr/maintainerr:latest
    container_name: maintainerr
    restart: unless-stopped
    networks: [media]
    user: "${PUID}:${PGID}"
    ports: ["6246:6246"]
    environment: { TZ: "${TZ}" }
    volumes: ["/opt/media/config/maintainerr:/opt/data"]   # NO /data mount: it cannot touch files

networks:
  media: { external: true }
```

**tdarr**: `/opt/media/stacks/tdarr/compose.yaml`
```yaml
x-tdarr-env: &tenv
  PUID: ${PUID}
  PGID: ${PGID}
  TZ: ${TZ}
  UMASK_SET: "002"
  inContainer: "true"
  ffmpegVersion: "7"

services:
  tdarr:
    image: ghcr.io/haveagitgat/tdarr:latest
    container_name: tdarr
    restart: unless-stopped
    networks: [media]
    ports: ["8265:8265", "8266:8266"]
    environment:
      <<: *tenv
      serverIP: 0.0.0.0
      serverPort: "8266"
      webUIPort: "8265"
      internalNode: "false"               # separate node container below
    volumes:
      - /opt/media/config/tdarr/server:/app/server
      - /opt/media/config/tdarr/configs:/app/configs
      - /opt/media/config/tdarr/logs:/app/logs
      - /data/media:/data/media
      - /scratch/tdarr:/scratch/tdarr

  tdarr-node:
    image: ghcr.io/haveagitgat/tdarr_node:latest
    container_name: tdarr-node
    restart: unless-stopped
    networks: [media]
    environment:
      <<: *tenv
      nodeName: box-qsv
      serverIP: tdarr
      serverPort: "8266"
    devices: ["/dev/dri:/dev/dri"]
    group_add: ["${RENDER_GID}"]
    volumes:
      - /opt/media/config/tdarr/node-configs:/app/configs
      - /opt/media/config/tdarr/node-logs:/app/logs
      - /data/media:/data/media            # identical paths to the server
      - /scratch/tdarr:/scratch/tdarr

networks:
  media: { external: true }
```

**ops**: `/opt/media/stacks/ops/compose.yaml`
```yaml
services:
  socket-proxy:
    image: lscr.io/linuxserver/socket-proxy:latest
    container_name: socket-proxy
    restart: unless-stopped
    networks: [media]
    read_only: true
    tmpfs: ["/run"]
    environment:
      CONTAINERS: 1
      IMAGES: 1
      INFO: 1
      POST: 0                             # read-only
    volumes: ["/var/run/docker.sock:/var/run/docker.sock:ro"]

  uptime-kuma:
    image: louislam/uptime-kuma:2
    container_name: uptime-kuma
    restart: unless-stopped
    networks: [media]
    ports: ["3001:3001"]
    volumes: ["/opt/media/config/uptime-kuma:/app/data"]

  homepage:
    image: ghcr.io/gethomepage/homepage:latest
    container_name: homepage
    restart: unless-stopped
    networks: [media]
    ports: ["3000:3000"]
    environment:
      PUID: ${PUID}
      PGID: ${PGID}
      HOMEPAGE_ALLOWED_HOSTS: 192.0.2.242:3000,box:3000,box.<tailnet>.ts.net:3000
    env_file: [homepage.env]              # HOMEPAGE_VAR_SONARR_KEY=... etc.
    volumes:
      - /opt/media/config/homepage:/app/config

  diun:
    image: crazymax/diun:latest
    container_name: diun
    restart: unless-stopped
    networks: [media]
    command: serve
    environment:
      TZ: ${TZ}
      DIUN_WATCH_SCHEDULE: "0 */6 * * *"
      DIUN_WATCH_FIRSTCHECKNOTIF: "false"
      DIUN_PROVIDERS_DOCKER: "true"
      DIUN_PROVIDERS_DOCKER_ENDPOINT: tcp://socket-proxy:2375
      DIUN_PROVIDERS_DOCKER_WATCHBYDEFAULT: "true"
      # notifier set per Decision 11, e.g. DIUN_NOTIF_NTFY_ENDPOINT / _TOPIC
    volumes: ["/opt/media/config/diun:/data"]

networks:
  media: { external: true }
```
Homepage's Docker integration (`docker.yaml`) points at `socket-proxy:2375`, not the raw socket. Updates are always manual: DIUN notifies, then you click *Update* in Dockge or run `docker compose pull && docker compose up -d`.

### 3.7 Setup order (exact settings)

In-container hostnames work because everything except Plex shares the `media` network. Plex is reached at `192.0.2.242:32400`.

1. **SABnzbd** (`:8080`)
   - Wizard: add your Usenet provider (SSL, port 563, connections ≤ provider limit).
   - Config → Folders: **Temporary Download Folder** `/scratch/sabnzbd/incomplete`, **Completed Download Folder** `/data/usenet/complete`.
   - Config → Categories: `tv` → folder `tv`; `movies` → folder `movies`.
   - Config → General → **host_whitelist**: add `sabnzbd, box, 192.0.2.242, box.<tailnet>.ts.net`. Without this, the arrs get "access denied".
   - Config → Switches: Direct Unpack on; leave "Post-Process Only Verified Jobs" on.
2. **Prowlarr** (`:9696`)
   - Add your Usenet indexers.
   - Settings → Apps → **+ Sonarr**: Prowlarr Server `http://prowlarr:9696`, Sonarr Server `http://sonarr:8989`, API key, Sync Level **Full Sync**.
   - Same for **Radarr** (`http://radarr:7878`).
3. **Sonarr / Radarr**
   - Settings → Media Management: **Use Hardlinks instead of Copy = on**, Rename on.
   - Root folder **`/data/media/tv`** (Sonarr) / **`/data/media/movies`** (Radarr).
   - Download Clients → **SABnzbd**: host `sabnzbd`, port `8080`, API key, category `tv` / `movies`. Completed Download Handling on, Remove Completed on.
   - No remote path mappings needed (identical paths).
4. **Recyclarr**
   ```bash
   docker exec recyclarr recyclarr config create -t web-1080p        # Sonarr TRaSH WEB-1080p  (trash_id 72dae194…)
   docker exec recyclarr recyclarr config create -t hd-bluray-web    # Radarr HD Bluray + WEB  (trash_id d1d67249…)
   # (4K instead: web-2160p / uhd-bluray-web, per Decision 7)
   ```
   Edit `base_url` to `http://sonarr:8989` / `http://radarr:7878` and `api_key` to `!secret sonarr_api_key` (values in `/opt/media/config/recyclarr/secrets.yml`). Then:
   ```bash
   docker exec recyclarr recyclarr sync --preview    # review
   docker exec recyclarr recyclarr sync
   ```
   Scheduled sync: `CRON_SCHEDULE=0 4 * * *` in compose. See the Tdarr/x265 conflict below.
5. **Bazarr** (`:6767`)
   - Settings → Sonarr: host `sonarr` port `8989` + key; Settings → Radarr: host `radarr` port `7878` + key. No path mapping.
   - Languages: create a profile (e.g. English) and set it as default for series and movies.
   - Providers: OpenSubtitles.com (account) + others.
6. **Plex** (`http://192.0.2.242:32400/web`)
   - Claim the server on first start.
   - Libraries: Movies → `/data/media/movies`, TV → `/data/media/tv`.
   - Settings → Transcoder: **Use hardware acceleration when available ✔**, **Use hardware-accelerated video encoding ✔**, HDR tone mapping ✔, Transcoder temporary directory **`/transcode`**.
   - Settings → Library: **Empty trash automatically after every scan ✘**, **Allow media deletion ✘**.
   - Network: LAN Networks as in 3.5.
   - Verify: play something with a forced transcode; the dashboard should show **"(hw)"**. (HW transcoding requires **Plex Pass**.)
7. **Tdarr**: see 3.8.
8. **Seerr** (`:5055`): sign in with Plex, server `192.0.2.242:32400`, sync libraries. Add Radarr `radarr:7878` and Sonarr `sonarr:8989` with the Recyclarr-created profile and root folders above.
   **Tautulli** (`:8181`): Plex `192.0.2.242:32400`, sign in for the token.
   **Kometa**: `/opt/media/config/kometa/config.yml` with `plex: {url: http://192.0.2.242:32400, token: …}`, `tmdb: {apikey: …}`, and per library `collection_files: [{default: basic}, {default: imdb}]`. Runs daily at 05:00.
   **Maintainerr** (`:6246`): connect Plex, Tautulli, Seerr. *Do not* give it Sonarr/Radarr credentials unless you want arr-based rule data, and even then set every rule group's action to **"Do nothing"** (wording varies by version; verify before saving). Its effect is a Plex "Leaving soon" style collection only. Combined with Plex "Allow media deletion ✘" and no `/data` mount, it **cannot delete media**.
9. **Uptime Kuma** (`:3001`): HTTP monitors (60 s):
   `http://sabnzbd:8080`, `http://prowlarr:9696/ping`, `http://sonarr:8989/ping`, `http://radarr:7878/ping`, `http://bazarr:6767`, `http://192.0.2.242:32400/identity`, `http://tautulli:8181`, `http://seerr:5055/api/v1/status`, `http://tdarr:8265`, `http://maintainerr:6246`, `http://homepage:3000`, `http://192.0.2.242:5001`.
   **USB mounts**: one *Push* monitor per mount, fed by a host timer:
   ```bash
   # /usr/local/bin/mount-push.sh   (systemd timer every 2 min)
   declare -A T=( [/data]=TOKEN1 [/mnt/disk1]=TOKEN2 [/mnt/disk2]=TOKEN3 [/mnt/disk3]=TOKEN4 [/mnt/disk4]=TOKEN5 [/scratch]=TOKEN6 )
   for m in "${!T[@]}"; do mountpoint -q "$m" && curl -fsS -m 5 "http://127.0.0.1:3001/api/push/${T[$m]}?status=up&msg=mounted" >/dev/null; done
   ```
   No push within 5 min → alert.
10. **Homepage**: `services.yaml` with widgets `sonarr`, `radarr`, `prowlarr`, `bazarr`, `sabnzbd`, `plex`, `tautulli`, `tdarr`, `uptimekuma`, and Seerr via the `seerr` widget if your Homepage version has it (else `overseerr`, API-compatible). Maintainerr, Kometa, Dockge, and DIUN as links. Keys come from `HOMEPAGE_VAR_*` in `homepage.env`.
11. **DIUN**: notifier per Decision 11; test with `docker exec diun diun notif test`.

### 3.8 Tdarr
- **Quick Sync is present** (UHD 770, HuC loaded), so use **QSV GPU workers**.
- Node `box-qsv`: **Transcode GPU 2, Transcode CPU 0, Health-check CPU 2, Health-check GPU 0**. The single media engine is shared with Plex, so set a node schedule of **01:00–07:00** so it doesn't compete with evening playback.
- Transcode cache: `/scratch/tdarr/cache` (NVMe).
- **AV1 encode is not supported on UHD 770** (pending `vainfo` confirmation), so **hevc_qsv only**. If vainfo surprises us, I'll bring back the av1_qsv option along with its client-compatibility questions.

**Flow (hevc_qsv):**
1. Input → skip if already HEVC/AV1 → **skip Dolby Vision / HDR10+** (re-encoding drops DV/dynamic metadata) → skip files < 1 GB.
2. ffmpeg command: video encoder `hevc` with hardware **QSV**, `-preset slow -global_quality 22` (ICQ), 10-bit output (`-pix_fmt p010le`) for 10-bit sources; **copy** all audio and subtitle streams; container MKV.
3. **Compare file size**: if the output is > 85 % of the original, fail the file (not worth it).
4. **Keep originals**: output to `/scratch/tdarr/output` (move-to-directory), **no "replace original"** step until you approve.

Manual equivalent for spot checks:
```bash
ffmpeg -hwaccel qsv -hwaccel_output_format qsv -i in.mkv -map 0 \
  -c:v hevc_qsv -preset slow -global_quality 22 -c:a copy -c:s copy out.mkv
```

**Pilot:**
- Copy 5–10 representative files (animation, grainy film, dark scenes, a 4K SDR file) into `/data/media/_pilot`. Point a Tdarr library at only that folder.
- Compare size and quality: `ffprobe` bitrates, plus VMAF if the bundled ffmpeg has `libvmaf` (otherwise A/B in Plex on your TV).
- Then expand library by library. Only after you sign off, switch the flow's last step to *replace original*.

🚩 **Conflict: Tdarr vs TRaSH profiles.** TRaSH's 1080p profiles (Golden Rule HD group) score **x265 (HD)** at −10000. After Tdarr converts a 1080p file to HEVC, Sonarr/Radarr see it as below cutoff and may **re-download the x264 release**, then Tdarr converts it again, in a loop. Options (Decision 8):
- (a) in the Recyclarr config, exclude `47435ece6b99a0b477caf360e79ba0bb` (Sonarr) / `dc98083864ea246d05a42df0d05f81cc` (Radarr) from the Golden Rule HD group. The arrs will then also accept x265 HD *downloads*.
- (b) run Tdarr only on items that are unmonitored or already at cutoff.
- (c) Tdarr only on 4K/remux content, where x265 isn't penalised.

### 3.9 Resilience

**Nightly config backup** (04:30, systemd timer; ~1–3 min of app downtime):
```bash
#!/usr/bin/env bash
# /usr/local/sbin/media-config-backup
set -euo pipefail
SRC=/opt/media/config; D1=/scratch/backups/config; D2=/data/backups/config
STACKS=(core plex tdarr); STAMP=$(date +%F); KEEP=14
mkdir -p "$D1"
for s in "${STACKS[@]}"; do docker compose -f /opt/media/stacks/$s/compose.yaml stop; done
tar --zstd -cf "$D1/config-$STAMP.tar.zst" -C "$SRC" \
    --exclude='./plex/Library/Application Support/Plex Media Server/Cache' \
    --exclude='./plex/Library/Application Support/Plex Media Server/Crash Reports' .
for s in "${STACKS[@]}"; do docker compose -f /opt/media/stacks/$s/compose.yaml start; done
find "$D1" -name 'config-*.tar.zst' -mtime +$KEEP -delete                  # 14 daily
cp -a /opt/media/stacks "$D1/stacks-$STAMP" && find "$D1" -maxdepth 1 -name 'stacks-*' -mtime +$KEEP -exec rm -rf {} +
if mountpoint -q /data; then mkdir -p "$D2"; rsync -a --delete "$D1/" "$D2/"; fi   # second copy on the USB pool
```
```ini
# /etc/systemd/system/media-config-backup.timer
[Timer]
OnCalendar=*-*-* 04:30:00
Persistent=true
[Install]
WantedBy=timers.target
```
Uptime Kuma gets a push monitor that the script hits on success. A restore test is part of Phase 4 sign-off.

**Failure modes:**

| Event | Effect | Mitigation |
|---|---|---|
| USB enclosure disconnects (all 5 disks at once, single bridge) | `/data` empties or errors; Plex shows items unavailable; arrs mark files missing; downloads fail to import | `chattr +i` mountpoints (no writes to `/`); Plex auto-empty-trash **off**; arrs never auto-delete missing files; Maintainerr can't delete; SnapRAID sync is skipped when `diff` shows mass deletions; Uptime Kuma push alert. Recovery: replug, `sudo mount -a`, restart the `core`/`plex`/`tdarr` stacks. Watch `journalctl -k | grep -i 'reset\|usb 2-4'`. |
| A single disk drops | mergerfs keeps serving the remaining branches; that disk's titles go missing | Same as above, plus SnapRAID to recover a dead disk |
| Spin-down | First play after idle takes 10–20 s while the disks spin up; the JMS567 may or may not pass `hdparm -S` | Test `hdparm -C` in Phase 4; either leave them spinning (simpler, lower wear on SMR) or set a long timer (≥ 60 min). Schedule Plex scans, Kometa, SnapRAID, and Tdarr in the same night window so the disks wake once. |
| Boot without the enclosure | `nofail` + 30 s timeout means boot continues; containers start with an empty, immutable `/data` | Alert fires; replug, `mount -a`, restart stacks |
| Wi-Fi drop | Apps keep running; remote/Tailscale access and Plex streams pause; SAB retries; Plex reconnects | Power save off; DHCP reservation; **Ethernet**; `systemd-networkd` reconnects automatically |
| SMR write stalls (3 × DM004) | Long sustained writes (big imports, Tdarr replacements, SnapRAID rebuilds) can slow to tens of MB/s | Put SnapRAID parity on a CMR IronWolf; mergerfs `mfs` spreads writes; Tdarr stays overnight |

### 3.10 Risks and blockers
1. **Wi-Fi-only** host with an unused Ethernet port. This is the biggest reliability and bandwidth limiter.
2. **Single USB bridge for 5 disks**: one cable/PSU/bridge fault drops the whole library; ~400 MB/s shared; BOT, not UAS.
3. **All 5 USB disks are NTFS** with unknown contents. Converting to ext4 is destructive.
4. **No redundancy** unless SnapRAID is adopted; mergerfs is just pooling.
5. **3 of 5 disks are SMR.**
6. **nvme0n1 holds a second Ubuntu install**; repurposing it as /scratch destroys it. NVMe numbering isn't stable, so I'll target by serial/by-id only.
7. **Root LV is 100 G**; extend it before Plex metadata grows.
8. **Agent has no sudo** (password required). Phase 4 needs Decision 6.
9. **Unverified**: vainfo codec list, Wi-Fi PHY rate/band, netplan file contents, SMART health, NTFS usage.
10. **Tdarr ↔ TRaSH x265 re-download loop** (3.8).
11. **Plex Pass required** for HW transcoding; Tailscale clients need LAN Networks configured.
12. Docker socket access (Dockge) is root-equivalent; Homepage and DIUN go through the read-only proxy.
13. Host TZ is UTC (fixed in 3.1).
14. Ubuntu 26.04 / kernel 7.0 are new. The LSIO Plex image bundles its own drivers, so this should be fine, but it gets verified in Phase 4.

---

## 4. Decisions needed
1. **Ethernet**: can you run a cable (or MoCA/powerline) to the box? If yes, also reserve an IP for the I219 MAC.
2. **NTFS drives**: OK to mount them **read-only** to check contents? If they hold media: rolling migration, or wipe?
3. **SnapRAID**: 1 parity disk (IronWolf SERIAL-DISK2) for ~29 TiB protected, or all 5 as data for ~36 TiB unprotected?
4. **Wipe nvme0n1** (old Ubuntu install, serial …XXXX) for /scratch: is there anything on it you need?
5. **Extend the root LV** by +200 G (or another size)?
6. **Sudo for Phase 4**: temporary NOPASSWD file (removed at the end), or you paste the sudo blocks?
7. **Quality**: 1080p (Sonarr WEB-1080p / Radarr HD Bluray + WEB), 4K (WEB-2160p / UHD Bluray + WEB), or both as separate profiles?
8. **Tdarr vs TRaSH x265**: option (a), (b), or (c) from 3.8? Which libraries should Tdarr touch at all?
9. **Tdarr quality**: start at `global_quality 22`? Skip HDR/DV (recommended)?
10. **Plex outside your tailnet**: Tailscale-only (no ports), or forward 32400 for family/friends (Plex streaming port only, never admin UIs)?
11. **Notifications** for DIUN and Uptime Kuma: ntfy, Discord, Pushover, or email?
12. **Accounts/keys to have ready**: Usenet provider, indexers, Plex Pass, TMDb API key (Kometa), OpenSubtitles.com.
13. **Backup window and retention**: 04:30 with 14 daily OK? Want weekly/monthly tiers too?
14. **Plex transcode temp**: `/scratch` (as planned) or RAM (`/dev/shm`, you have 30 GiB)?
