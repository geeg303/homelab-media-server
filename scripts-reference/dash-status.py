#!/usr/bin/env python3
# dash-status: writes /opt/media/status/disks.json and host.json for Homepage tiles.
# Read-only: statfs (df) on fixed mount points, systemctl/docker/tailscale queries. No disk I/O on the data drives.
import json, os, subprocess, time, datetime

OUT = "/opt/media/status"
MOUNTS = [("root", "/", "OS (NVMe)"), ("scratch", "/scratch", "scratch (NVMe)")] + \
    [(f"disk{i}", f"/mnt/disk{i}", f"disk{i}") for i in range(1, 7)] + \
    [("backup", "/mnt/backup", "backup"),
     ("mig_sdb", "/mnt/mig/sdb", "NTFS source sdb"),
     ("mig_sdd", "/mnt/mig/sdd", "NTFS source sdd"),
     ("mig_sde", "/mnt/mig/sde", "NTFS source sde")]


def sh(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        return ""


def human(b):
    for unit, div in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6)):
        if b >= div:
            return f"{b / div:.1f} {unit}"
    return f"{b:.0f} B"


def bar(pct, width=20):
    n = round(pct / 100 * width)
    return "█" * n + "░" * (width - n)


def ismount(p):
    return os.path.ismount(p)


def write(name, data):
    tmp = os.path.join(OUT, f".{name}.tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o644)
    os.replace(tmp, os.path.join(OUT, name))


now = datetime.datetime.now()
stamp = now.strftime("%a %-I:%M %p")

disks = {}
arr_used = arr_size = 0
for key, path, label in MOUNTS:
    if not ismount(path):
        disks[key] = "— not mounted"
        continue
    st = os.statvfs(path)
    size = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    used = size - st.f_bfree * st.f_frsize
    pct = used / size * 100 if size else 0
    disks[key] = f"{bar(pct)} {pct:4.0f}%  {human(used)} / {human(size)}"
    if key.startswith("disk"):
        arr_used += used
        arr_size += size
disks["array_total"] = (f"{bar(arr_used / arr_size * 100)} {arr_used / arr_size * 100:.0f}%  "
                        f"{human(arr_used)} / {human(arr_size)} on disk1-6") if arr_size else "—"
disks["updated"] = stamp
write("disks.json", disks)

host = {}
with open("/proc/uptime") as f:
    up = int(float(f.read().split()[0]))
d, r = divmod(up, 86400)
h, r = divmod(r, 3600)
host["uptime"] = f"{d}d {h}h {r // 60}m"
host["load"] = " · ".join(open("/proc/loadavg").read().split()[:3]) + f"  ({os.cpu_count()} threads)"
host["kernel"] = os.uname().release
osr = dict(l.strip().split("=", 1) for l in open("/etc/os-release") if "=" in l)
host["os"] = osr.get("PRETTY_NAME", "").strip('"')
mem = dict((l.split(":")[0], int(l.split()[1])) for l in open("/proc/meminfo"))
mu = (mem["MemTotal"] - mem["MemAvailable"]) * 1024
host["memory"] = f"{human(mu)} used / {human(mem['MemTotal'] * 1024)}"
running = sh("docker", "ps", "-q").split()
allc = sh("docker", "ps", "-aq").split()
host["containers"] = f"{len(running)} running / {len(allc)} total"
try:
    ts = json.loads(sh("tailscale", "status", "--json") or "{}")
    me = ts.get("Self", {})
    peers = ts.get("Peer", {}) or {}
    online = sum(1 for p in peers.values() if p.get("Online"))
    host["tailscale"] = f"{ts.get('BackendState', '?')} · {me.get('HostName', '?')} · {online}/{len(peers)} peers online"
    host["tailscale_ip"] = (me.get("TailscaleIPs") or ["?"])[0]
except Exception:
    host["tailscale"] = "unknown"
    host["tailscale_ip"] = "?"


def unit_info(svc, timer):
    p = dict(l.split("=", 1) for l in sh("systemctl", "show", svc, "-p", "Result,ExecMainExitTimestamp,ExecMainStatus").splitlines() if "=" in l)
    t = dict(l.split("=", 1) for l in sh("systemctl", "show", timer, "-p", "NextElapseUSecRealtime").splitlines() if "=" in l)
    ok = "✅" if p.get("Result") == "success" and p.get("ExecMainStatus", "0") == "0" else "❌"
    last = p.get("ExecMainExitTimestamp", "") or "never"
    return f"{ok} {last}", t.get("NextElapseUSecRealtime", "") or "—"


host["backup_last"], host["backup_next"] = unit_info("media-config-backup.service", "media-config-backup.timer")
timers = sh("systemctl", "list-timers", "--no-legend", "--all").splitlines()
host["timers"] = f"{len(timers)} systemd timers scheduled"
failed = [l.split()[0] for l in sh("systemctl", "--failed", "--no-legend", "--plain").splitlines() if l.strip()]
host["failed_units"] = "✅ none" if not failed else "❌ " + ", ".join(failed)
host["updated"] = stamp
write("host.json", host)
