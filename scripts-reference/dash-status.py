#!/usr/bin/env python3
# dash-status: writes /opt/media/status/disks.json, host.json and diskio.json for Homepage tiles.
# diskio.json: per-disk read/write MB/s from /proc/diskstats deltas, keyed by role and resolved BY SERIAL
# (/dev/disk/by-id), so sdX renumbering after a reboot can't mislabel tiles.
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


# ---------------- diskio.json (per-disk throughput, keyed by serial) ----------------
DISKIO_ROLES = [  # (role, serial, label)
    ("system", "240246A1D2E0", "system NVMe"),
    ("scratch", "NVME-SERIAL-2", "scratch NVMe"),
    ("disk1", "SERIAL-DISK1", "disk1 Seagate"),
    ("disk2", "SERIAL-DISK2", "disk2 IronWolf"),
    ("disk3", "SERIAL-WD1", "disk3 WD"),
    ("disk4", "7SJ8JDXW", "disk4 WD"),
    ("disk5", "7HJY59ZF", "disk5 WD"),
    ("disk6", "7HJY82BF", "disk6 WD"),
    ("backup", "7HK2YR2H", "backup WD"),
    ("src_sdb", "SERIAL-SDB", "source IronWolf (ex-sdb)"),
    ("src_sdd", "SERIAL-SDD", "source Seagate (ex-sdd)"),
    ("src_sde", "SERIAL-SDE", "source Seagate (ex-sde)"),
]
DISKIO_PREV = "/var/lib/media-server/diskio-prev.json"
BYID = "/dev/disk/by-id"


def diskio_dev(serial):
    try:
        names = os.listdir(BYID)
    except OSError:
        return None
    for n in sorted(names):
        if (n.startswith("ata-") or n.startswith("nvme-")) and n.endswith("_" + serial):
            return os.path.basename(os.path.realpath(os.path.join(BYID, n)))
    return None


def diskio_mbs(v):
    return f"{v:.1f} MB/s" if v >= 0.05 or v == 0 else "<0.1 MB/s"


def diskio():
    stats = {}
    for line in open("/proc/diskstats"):
        f = line.split()
        if len(f) >= 14:  # name, reads, rmerged, rsect, rms, writes, wmerged, wsect, wms, inflight, io_ticks
            stats[f[2]] = {"rs": int(f[5]), "ws": int(f[9]), "ticks": int(f[12])}
    try:
        boot = open("/proc/sys/kernel/random/boot_id").read().strip()
    except OSError:
        boot = "?"
    t = time.monotonic()
    try:
        prev = json.load(open(DISKIO_PREV))
        if prev.get("boot") != boot:
            prev = {}
    except Exception:
        prev = {}
    pdisks = prev.get("disks", {})
    dt = t - prev["t"] if prev.get("t") else 0
    out, cur = {}, {}
    total_r = total_w = 0.0
    for role, serial, label in DISKIO_ROLES:
        dev = diskio_dev(serial)
        d = {"role": role, "serial": serial, "label": label, "dev": dev or "absent"}
        st = stats.get(dev) if dev else None
        if st is None:
            d.update(read="— not present", write="—", busy="—", rw="— not present",
                     line=f"absent · {serial}", read_mbs=None, write_mbs=None, busy_pct=None)
        else:
            cur[serial] = dict(st, dev=dev)
            p = pdisks.get(serial)
            if p and p.get("dev") == dev and dt > 5 and st["rs"] >= p["rs"] and st["ws"] >= p["ws"]:
                r = (st["rs"] - p["rs"]) * 512 / dt / 1e6
                w = (st["ws"] - p["ws"]) * 512 / dt / 1e6
                b = min(100.0, max(0.0, (st["ticks"] - p["ticks"]) / (dt * 1000) * 100))
                total_r += r
                total_w += w
                d.update(read=diskio_mbs(r), write=diskio_mbs(w), busy=f"{b:.0f}%",
                         rw=f"R {diskio_mbs(r)} · W {diskio_mbs(w)}",
                         line=f"{dev} · R {r:.1f} · W {w:.1f} MB/s · {b:.0f}% busy",
                         read_mbs=round(r, 2), write_mbs=round(w, 2), busy_pct=round(b, 1))
            else:
                d.update(read="… warming up", write="…", busy="…", rw="… warming up (next run)",
                         line=f"{dev} · warming up", read_mbs=None, write_mbs=None, busy_pct=None)
        out[role] = d
        # flat keys for customapi mappings (field: disk4_read etc.)
        for k in ("dev", "serial", "read", "write", "busy", "rw", "line"):
            out[f"{role}_{k}"] = d[k]
    out["total"] = f"R {diskio_mbs(total_r)} · W {diskio_mbs(total_w)}" if dt > 5 else "… warming up"
    out["interval"] = f"{dt:.0f} s average" if dt > 5 else "first sample"
    out["updated"] = stamp
    write("diskio.json", out)
    tmp = DISKIO_PREV + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"boot": boot, "t": t, "disks": cur}, f)
    os.replace(tmp, DISKIO_PREV)


try:
    diskio()
except Exception as e:
    write("diskio.json", {"updated": stamp, "error": f"diskio failed: {e}"})
