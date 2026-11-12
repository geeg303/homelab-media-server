# Coverage audit — 2026-11-11

Checked every container (`docker ps -a`), compose stack (`docker compose ls`), listening port (`ss -tlnp`),
box script (`/usr/local/sbin`), systemd unit/timer and web UI against the Homepage dashboard, Uptime Kuma
and the GitHub mirror (`tools/box-collect.sh`).

## Coverage matrix

| Item | Port(s) | Homepage | Kuma | Repo mirror |
|---|---|---|---|---|
| Plex | 32400 (host net; 32401/32600 localhost only) | tile (widget parked) | Plex | compose + exports |
| Sonarr / Radarr / Prowlarr / Bazarr / SABnzbd | 8989 / 7878 / 9696 / 6767 / 8080 | tiles + widgets | yes | compose + exports |
| Tautulli / Seerr / Maintainerr | 8181 / 5055 / 6246 | tiles + widgets | yes | compose + exports |
| Tdarr server + node | 8265/8266 | tiles + Conversions tile | web UI, API, node container | compose + exports |
| Kometa / Recyclarr / DIUN | — | tiles (container status) | docker monitors | compose + configs |
| PrismCast web UI + tuner | 5589 / 5004 | Live TV (PrismCast) tile | 2 monitors | livetv compose + env keys + config.json/provider-lineups.json (**new**) |
| PrismCast noVNC | 6080 (raw VNC 5900 on localhost only) | **PrismCast browser (VNC) tile — new** | **PrismCast browser (noVNC) — new** | compose |
| Dockge | 5001 | tile, **container status added** | Dockge | dockge compose |
| Uptime Kuma | 3001 | tile + uptimekuma widget | (itself) | compose + exports |
| Homepage | 3000 | (the dashboard itself) | Homepage | compose + configs |
| WUD (Updates) / FileBrowser | 3002 / 8099 | tiles | yes | compose + config |
| socket-proxy | 2375 (media network) | **tile — new** | Docker socket proxy | compose |
| status (tile JSON) | 80 (media network) | **Status feed tile — new** (+ the 3 live tiles it feeds) | Dashboard status feed | compose + the 3 status scripts |
| Home Assistant VM `haos` | 192.0.2.150:80 | tile | Home Assistant | libvirt XML (`host/libvirt/haos.xml`) |
| sshd | 22 | — | **Box SSH (port 22) — new** | — |
| Tailscale | tailnet only | — | Host health → Tailscale | prefs JSON |
| Timers: tdarr-status, migration-status, selftest-status | — | the live tiles | only indirectly (feed file present) | units + scripts |
| Timers: host-health-push, mount-push, media-config-backup, tdarr-swap | — | — | push monitors (missed push = alert) | units + scripts |
| usb-watchdog.service, wifi-powersave-off.service | — | — | **none** | units + scripts |
| Scripts tdarr-pilot-copy, ha-ws | — | — | — | **added to box-collect.sh** |
| /etc/docker/daemon.json (log rotation) | — | — | — | **added** (`host/docker-daemon.json`) |

## Gaps not fixed (need a script/unit change, so they need approval)

1. **The three status timers can fail silently.** If `tdarr-status`, `migration-status` or `selftest-status` breaks, the tile just freezes; the Kuma "Dashboard status feed" check only proves the JSON file exists. Fix: a "Status tiles fresh" push check in `host-health-push` (JSON mtime < 5 min), or `OnFailure=` ntfy on the three units.
2. **usb-watchdog.service has no monitor.** It is active now, but nothing alerts if it dies. Fix: add `systemctl is-active usb-watchdog` to `host-health-push` as its own push monitor.
3. **Nightly backup doesn't stop the `livetv` stack.** `media-config-backup` stops core/plex/tdarr/ops only, so PrismCast's Chrome profile is tarred while running (it is included, but may be inconsistent). Fix: add `livetv` to `STACKS` (live TV pauses for the backup minutes at 04:30), or exclude `chromedata` and rely on re-login.
4. **Backups stay on the box.** Config backups live on `/scratch` only until `/data` exists (then also on the pool) — no off-box copy. `/etc/media-server` (push tokens, HA token) and the HAOS VM disk are not in any backup (the repo has everything else except secrets). Fix: an off-box copy (e.g. to the Windows PC or cloud) and HA's own scheduled backups.
5. **`systemd-networkd-wait-online.service` is in failed state** (Wi-Fi-only box; harmless so far, but shows as a failed unit). Fix: give it `--any`/the wlan interface or mask it.
6. **`/etc/sudoers.d/90-hermes-temp`** (passwordless sudo for the agent) is still in place. It was meant to be temporary; decide whether to keep it.
