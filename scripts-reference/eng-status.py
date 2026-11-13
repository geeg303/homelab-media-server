#!/usr/bin/env python3
# eng-status: writes /opt/media/status/eng.json (engineering health) for the Pro Homepage dashboard.
# Read-only on the host: /proc, /sys, systemctl show, journalctl -k, docker inspect --format, iw, tailscale,
# cached apt data (no apt update), smartctl -n standby (cached, refreshed at most every 30 min).
# Every probe is isolated: a failing probe sets its fields to "unknown" and is listed in "errors"; the file is always written.
# Env overrides (for testing): OUT=<file>  SMART_CACHE=<file>  SMART_MAX_AGE=<sec>  SMART_FORCE_AGE=<sec>  SMART_BUDGET=<sec>
# SMART: -n standby skips sleeping disks where the bridge supports CHECK POWER MODE (NVMe yes; the JMicron USB bridges
# do NOT and smartctl ignores -n there), so USB disks with no block I/O since the last read are left alone (cached).
# No secrets: never dumps env, container config, tokens, SSIDs/BSSIDs or tailnet peer names (counts only).
import datetime
import glob
import json
import os
import re
import subprocess
import time

OUT = os.environ.get("OUT", "/opt/media/status/eng.json")
SMART_CACHE = os.environ.get("SMART_CACHE", "/var/lib/media-server/eng-smart-cache.json")
SMART_MAX_AGE = int(os.environ.get("SMART_MAX_AGE", "1800"))   # refresh SMART at most every 30 min
SMART_FORCE_AGE = int(os.environ.get("SMART_FORCE_AGE", "86400"))  # idle USB disks: re-read at most once a day anyway
SMART_BUDGET = float(os.environ.get("SMART_BUDGET", "6"))      # total wall-clock budget for SMART refresh
WIFI_IF = "wlp0s20f3"
TIMERS = [  # (key, service, timer or None)
    ("media_config_backup", "media-config-backup.service", "media-config-backup.timer"),
    ("dash_status", "dash-status.service", "dash-status.timer"),
    ("tdarr_status", "tdarr-status.service", "tdarr-status.timer"),
    ("migration_status", "migration-status.service", "migration-status.timer"),
    ("host_health_push", "host-health-push.service", "host-health-push.timer"),
    ("selftest_status", "selftest-status.service", "selftest-status.timer"),
    ("eng_status", "eng-status.service", "eng-status.timer"),
    ("usb_watchdog", "usb-watchdog.service", None),
    ("migrate_round3", "migrate-round3.service", None),
]
USB_PAT = re.compile(r"usb 2-[34]: (reset|USB disconnect)|I/O error, dev sd[a-z]|\[sd[a-z]\] .*(FAILED|timing out|abort)"
                     r"|uas_eh|device offline")

T0 = time.monotonic()
now = datetime.datetime.now().astimezone()
D = {"updated": now.strftime("%a %-I:%M %p"), "updated_iso": now.isoformat(timespec="seconds"), "errors": []}


def sh(*cmd, timeout=8):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


def probe(name):
    def deco(fn):
        try:
            fn()
        except Exception as e:  # never fail the whole file
            D["errors"].append(f"{name}: {type(e).__name__}")
        return fn
    return deco


def human_dur(sec):
    sec = int(sec)
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    return f"{d}d {h}h {m}m" if d else (f"{h}h {m}m" if h else f"{m}m")


def ago(epoch):
    if not epoch:
        return "never"
    s = time.time() - epoch
    if abs(s) < 60:
        return "just now"
    return "in " + human_dur(-s) if s < 0 else human_dur(s) + " ago"


def systemd_ts(v):
    """'Fri 2026-11-13 12:14:28 MST' -> epoch (local), or None."""
    v = (v or "").strip()
    if not v or v in ("n/a", "0"):
        return None
    m = re.match(r"\w{3} (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", v)
    if not m:
        return None
    return time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))


def short_time(epoch):
    if not epoch:
        return "—"
    t = datetime.datetime.fromtimestamp(epoch)
    fmt = "%-I:%M %p" if t.date() == datetime.date.today() else "%a %-I:%M %p"
    return t.strftime(fmt)


def show(unit, props):
    out = sh("systemctl", "show", unit, "-p", ",".join(props))
    return dict(l.split("=", 1) for l in out.splitlines() if "=" in l)


# ---------------------------------------------------------------- host basics
@probe("host")
def _host():
    up = float(open("/proc/uptime").read().split()[0])
    D["uptime"] = human_dur(up)
    D["uptime_s"] = int(up)
    D["kernel"] = os.uname().release
    osr = dict(l.strip().split("=", 1) for l in open("/etc/os-release") if "=" in l)
    D["os"] = osr.get("PRETTY_NAME", "").strip('"')


@probe("docker_version")
def _dockerver():
    D["docker_version"] = sh("docker", "version", "--format", "{{.Server.Version}}") or "unknown"


@probe("reboot")
def _reboot():
    req = os.path.exists("/var/run/reboot-required")
    pkgs = []
    if req and os.path.exists("/var/run/reboot-required.pkgs"):
        pkgs = sorted({l.strip() for l in open("/var/run/reboot-required.pkgs") if l.strip()})
    D["reboot_required"] = req
    D["reboot_pkgs"] = len(pkgs)
    D["reboot"] = (f"⚠️ reboot required ({', '.join(pkgs[:3])}{'…' if len(pkgs) > 3 else ''})" if req else "✅ not required")


@probe("apt")
def _apt():
    # Cached data only: update-notifier's text (refreshed by apt's own timers). Never runs apt update.
    f = "/var/lib/update-notifier/updates-available"
    total = sec = None
    if os.path.exists(f):
        txt = open(f).read()
        m = re.search(r"(\d+) updates? can be applied", txt)
        total = int(m.group(1)) if m else (0 if "0 updates" in txt or not txt.strip() else None)
        m = re.search(r"(\d+) of these updates? (?:is a|are) standard security", txt)
        sec = int(m.group(1)) if m else 0
        D["apt_checked"] = short_time(os.path.getmtime(f))
    if total is None and os.path.exists("/usr/lib/update-notifier/apt-check"):
        r = subprocess.run(["/usr/lib/update-notifier/apt-check"], capture_output=True, text=True, timeout=6)
        m = re.match(r"(\d+);(\d+)", r.stderr.strip())
        if m:
            total, sec = int(m.group(1)), int(m.group(2))
            D["apt_checked"] = "live (apt cache)"
    D["apt_updates"] = total
    D["apt_security"] = sec
    D["apt"] = "unknown" if total is None else ("✅ up to date" if total == 0 else
                                               f"{'⚠️' if sec else 'ℹ️'} {total} pending ({sec} security)")


# ---------------------------------------------------------------- systemd
@probe("failed_units")
def _failed():
    failed = [l.split()[0] for l in sh("systemctl", "--failed", "--no-legend", "--plain").splitlines() if l.strip()]
    D["failed_count"] = len(failed)
    D["failed_names"] = failed
    D["failed_units"] = "✅ none" if not failed else "❌ " + ", ".join(failed)


@probe("timers")
def _timers():
    units = {}
    lst = []
    nexts = {}  # list-timers JSON covers monotonic timers (OnUnitActiveSec) whose NextElapseUSecRealtime is empty
    try:
        for t in json.loads(sh("systemctl", "list-timers", "--all", "--output=json") or "[]"):
            nexts[t.get("unit")] = t["next"] / 1e6 if t.get("next") else None
    except Exception:
        pass
    for key, svc, tmr in TIMERS:
        try:
            s = show(svc, ["ActiveState", "SubState", "Result", "ExecMainStatus", "ExecMainExitTimestamp",
                           "ExecMainStartTimestamp", "ActiveEnterTimestamp", "LoadState"])
            u = {"unit": svc, "active": s.get("ActiveState", "?"), "sub": s.get("SubState", "?"),
                 "result": s.get("Result", "?")}
            if s.get("LoadState") == "not-found":
                u.update(state="not installed", display="— not installed")
                units[key] = u
                lst.append({"name": key.replace("_", "-"), "value": u["display"]})
                continue
            if tmr is None:  # long-running service (watchdog / migration runner)
                since = systemd_ts(s.get("ActiveEnterTimestamp"))
                ok = u["active"] == "active" and u["sub"] == "running"
                done = u["active"] == "inactive" and u["result"] == "success"
                u["since"] = short_time(since)
                u["since_epoch"] = since
                u["state"] = "running" if ok else ("finished" if done else u["active"])
                u["display"] = (f"✅ running {human_dur(time.time() - since) if since else ''}".rstrip() if ok else
                                "✅ finished" if done else f"❌ {u['active']}/{u['sub']} ({u['result']})")
            else:
                t = show(tmr, ["ActiveState", "UnitFileState", "NextElapseUSecRealtime", "LastTriggerUSec"])
                last = systemd_ts(s.get("ExecMainExitTimestamp")) or systemd_ts(t.get("LastTriggerUSec"))
                nxt = nexts.get(tmr) or systemd_ts(t.get("NextElapseUSecRealtime"))
                good = u["result"] == "success" and s.get("ExecMainStatus", "0") == "0"
                running = u["active"] in ("activating", "active") and u["sub"] in ("start", "running")
                u.update(timer=tmr, timer_state=t.get("ActiveState", "?"), enabled=t.get("UnitFileState", "?"),
                         last=short_time(last), last_ago=ago(last), last_epoch=last,
                         next=short_time(nxt), next_epoch=nxt, ok=good)
                icon = "🔄" if running else ("✅" if good else "❌")
                if t.get("ActiveState") != "active":
                    u["state"] = "timer off"
                    u["display"] = f"⏸️ timer {t.get('UnitFileState', 'off')} · last {u['last_ago']}" + ("" if good else " ❌")
                else:
                    u["state"] = "running" if running else ("ok" if good else "failed")
                    u["display"] = f"{icon} {u['last_ago']} · next {'now' if running and not nxt else u['next']}"
            units[key] = u
            lst.append({"name": key.replace("_", "-"), "value": u["display"]})
        except Exception as e:
            units[key] = {"unit": svc, "display": "unknown"}
            D["errors"].append(f"timer {key}: {type(e).__name__}")
    D["units"] = units
    D["units_list"] = lst
    bad = [k for k, u in units.items() if u.get("state") in ("failed",) or u.get("display", "").startswith("❌")]
    D["units_bad"] = len(bad)
    D["units_summary"] = "✅ all jobs OK" if not bad else "❌ " + ", ".join(b.replace("_", "-") for b in bad)


# ---------------------------------------------------------------- SMART (cached, standby-aware)
def disk_map():
    """serial -> {dev, model, kind, by_id}. Uses /dev/disk/by-id only (no scanning)."""
    disks = {}
    for p in sorted(glob.glob("/dev/disk/by-id/ata-*")) + sorted(glob.glob("/dev/disk/by-id/nvme-*")):
        name = os.path.basename(p)
        if "-part" in name or name.startswith("nvme-eui") or name.endswith("_1"):
            continue
        dev = os.path.realpath(p)
        kind = "nvme" if name.startswith("nvme-") else "ata"
        model, _, serial = name.split("-", 1)[1].rpartition("_")
        if not serial or serial in disks:
            continue
        base = os.path.basename(dev)
        usb = "/usb" in os.path.realpath(f"/sys/block/{base}/device") if kind == "ata" else False
        disks[serial] = {"dev": dev, "base": base, "model": model.replace("_", " "), "kind": kind,
                         "bus": "usb" if usb else kind, "by_id": p}
    return disks


def mount_of(base):
    try:
        for l in open("/proc/mounts"):
            src, mnt = l.split()[:2]
            if os.path.basename(src).startswith(base) and (src.startswith("/dev/" + base)):
                return mnt
    except Exception:
        pass
    return None


def io_count(base):
    try:
        f = open(f"/sys/block/{base}/stat").read().split()
        return int(f[0]) + int(f[4])  # reads + writes completed
    except Exception:
        return None


def query_smart(info, timeout):
    cmd = ["smartctl", "-n", "standby", "-j", "-H", "-A", "-i"]
    if info["kind"] == "ata":
        cmd += ["-d", "sat"]
    cmd.append(info["by_id"])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode & 2 and not r.stdout.strip().startswith("{"):
        return {"state": "standby"}
    j = json.loads(r.stdout)
    if (j.get("smartctl", {}).get("exit_status", 0) & 2) and "temperature" not in j:
        return {"state": "standby"}
    res = {"state": "ok", "model": j.get("model_name"), "passed": (j.get("smart_status") or {}).get("passed"),
           "temp_c": (j.get("temperature") or {}).get("current"),
           "power_on_hours": (j.get("power_on_time") or {}).get("hours")}
    if info["kind"] == "nvme":
        n = j.get("nvme_smart_health_information_log") or {}
        res.update(media_errors=n.get("media_errors"), critical_warning=n.get("critical_warning"),
                   percentage_used=n.get("percentage_used"), unsafe_shutdowns=n.get("unsafe_shutdowns"),
                   err_log_entries=n.get("num_err_log_entries"))
    else:
        raw = {a["id"]: (a.get("raw") or {}).get("value") for a in (j.get("ata_smart_attributes") or {}).get("table", [])}
        res.update(reallocated=raw.get(5), pending=raw.get(197), uncorrectable=raw.get(198), crc=raw.get(199),
                   reported_uncorrect=raw.get(187), load_cycles=raw.get(193))
    return res


@probe("smart")
def _smart():
    try:
        cache = json.load(open(SMART_CACHE))
    except Exception:
        cache = {}
    disks = disk_map()
    deadline = time.monotonic() + SMART_BUDGET
    changed = False
    nowt = time.time()
    for serial, info in disks.items():
        c = cache.get(serial, {})
        io = io_count(info["base"])
        fresh = nowt - c.get("checked", 0) < SMART_MAX_AGE
        # USB bridges ignore -n standby (no CHECK POWER MODE), so don't poke a disk that has had no I/O since
        # the last check: it may be spun down. Keep the cached values and mark it idle.
        idle = (info["bus"] == "usb" and c.get("io") is not None and io == c.get("io") and "temp_c" in c
                and nowt - c.get("checked", 0) < SMART_FORCE_AGE)
        if fresh or idle:
            if idle and not fresh:
                c["state_note"] = "idle (cached)"
            continue
        left = deadline - time.monotonic()
        if left < 0.5:
            c["state_note"] = "skipped (time budget)"
            cache[serial] = c
            continue
        try:
            r = query_smart(info, min(5.0, left))
            if r.get("state") == "standby":
                c.update(state_note="💤 standby (cached)", checked=nowt, io=io)
            else:
                # CRC errors are cable/bridge noise; only a RISE since first seen is worth a warning.
                base = c.get("crc_base", r.get("crc"))
                c = {**r, "checked": nowt, "io": io, "state_note": "", "crc_base": base}
        except subprocess.TimeoutExpired:
            c["state_note"] = "timeout (cached)"
        except Exception as e:
            c["state_note"] = f"error {type(e).__name__}"
        cache[serial] = c
        changed = True
    if changed:
        tmp = SMART_CACHE + ".tmp"
        os.makedirs(os.path.dirname(SMART_CACHE), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(cache, f)
        os.replace(tmp, SMART_CACHE)

    out, lst, warn = {}, [], []
    for serial, info in disks.items():
        c = cache.get(serial, {})
        mnt = mount_of(info["base"])
        if mnt and mnt.startswith("/mnt/mig/"):
            label = "mig-" + os.path.basename(mnt)
        else:
            label = (os.path.basename(mnt) if mnt and mnt != "/" else ("os" if mnt == "/" else "")) or info["base"]
        bad_attrs = sum((c.get(k) or 0) for k in ("reallocated", "pending", "uncorrectable", "media_errors"))
        crc_new = max(0, (c.get("crc") or 0) - (c.get("crc_base") or 0))
        t = c.get("temp_c")
        hot = t is not None and t >= (70 if info["kind"] == "nvme" else 55)
        passed = c.get("passed")
        if passed is False or bad_attrs or (c.get("critical_warning") or 0):
            icon = "❌"
        elif hot or crc_new:
            icon = "⚠️"
        elif passed:
            icon = "✅"
        else:
            icon = "❔"
        if icon in ("❌", "⚠️"):
            warn.append(serial)
        parts = [f"{t}°C" if t is not None else "—°C",
                 f"{c['power_on_hours']:,} h" if c.get("power_on_hours") is not None else "— h"]
        if info["kind"] == "nvme":
            parts.append(f"wear {c.get('percentage_used', '?')}% · media err {c.get('media_errors', '?')}")
        else:
            parts.append(f"realloc {c.get('reallocated', '?')} · pend {c.get('pending', '?')} · "
                         f"unc {c.get('uncorrectable', '?')} · crc {c.get('crc', '?')}" + (f" (+{crc_new} new)" if crc_new else ""))
        note = c.get("state_note") or ""
        disp = f"{icon} {' · '.join(parts)}" + (f" · {note}" if note else "")
        out[serial] = {"dev": info["base"], "mount": mnt, "label": label, "model": info["model"], "bus": info["bus"],
                       "passed": passed, "temp_c": t, "power_on_hours": c.get("power_on_hours"),
                       "reallocated": c.get("reallocated"), "pending": c.get("pending"),
                       "uncorrectable": c.get("uncorrectable"), "crc": c.get("crc"), "crc_new": crc_new,
                       "media_errors": c.get("media_errors"), "percentage_used": c.get("percentage_used"),
                       "checked": short_time(c.get("checked")), "checked_ago": ago(c.get("checked")),
                       "status": icon, "display": disp}
        lst.append({"name": f"{label} · {serial}", "value": disp})
    D["smart"] = out
    D["smart_list"] = sorted(lst, key=lambda x: x["name"])
    D["smart_count"] = len(out)
    D["smart_warn"] = len(warn)
    temps = [v["temp_c"] for v in out.values() if v["temp_c"] is not None and v["bus"] != "nvme"]
    D["smart_hottest_hdd_c"] = max(temps) if temps else None
    D["smart_summary"] = (f"✅ {len(out)} drives PASSED" if not warn else f"⚠️ {len(warn)}/{len(out)} need a look: "
                          + ", ".join(warn)) + (f" · hottest HDD {max(temps)}°C" if temps else "")


# ---------------------------------------------------------------- USB watchdog + kernel errors
@probe("usb")
def _usb():
    s = show("usb-watchdog.service", ["ActiveState", "SubState"])
    D["usb_watchdog"] = "✅ watching" if s.get("ActiveState") == "active" else f"❌ {s.get('ActiveState', '?')}"
    log = sh("journalctl", "-k", "--since", "-24h", "--no-pager", "-q", "-o", "cat", timeout=8).splitlines()
    hits = [l for l in log if USB_PAT.search(l)]
    D["usb_errors_24h"] = len(hits)
    D["usb_resets_24h"] = sum(1 for l in hits if re.search(r"usb 2-[34]: (reset|USB disconnect)", l))
    D["io_errors_24h"] = sum(1 for l in hits if "I/O error" in l)
    last = None
    try:
        with open("/var/log/usb-watchdog.log", "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            tail = f.read().decode(errors="replace").strip().splitlines()
        if tail:
            last = datetime.datetime.fromisoformat(tail[-1].split()[0]).timestamp()
    except Exception:
        pass
    D["usb_last_alert"] = ago(last)
    paused = 0
    for p in glob.glob("/proc/[0-9]*/stat"):
        try:
            st = open(p).read()
            if st[st.index("(") + 1:st.rindex(")")] == "rsync" and st[st.rindex(")") + 2] == "T":
                paused += 1
        except Exception:
            continue
    D["rsync_paused"] = paused
    D["usb"] = (("✅" if not hits else "⚠️") + f" {len(hits)} USB/disk errors in 24 h"
                + (f" · last alert {D['usb_last_alert']}" if last else "")
                + (f" · ⏸️ {paused} rsync paused" if paused else ""))


# ---------------------------------------------------------------- Docker
@probe("docker")
def _docker():
    ids = sh("docker", "ps", "-aq").split()
    rows = []
    if ids:
        fmt = "{{.Name}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}|{{.RestartCount}}"
        rows = [l.split("|") for l in sh("docker", "inspect", "--format", fmt, *ids, timeout=10).splitlines() if l]
    running = [r for r in rows if r[1] == "running"]
    unhealthy = [r[0].lstrip("/") for r in rows if r[2] == "unhealthy"]
    restarts = {r[0].lstrip("/"): int(r[3]) for r in rows if r[3].isdigit() and int(r[3]) > 0}
    stopped = [r[0].lstrip("/") for r in rows if r[1] != "running"]
    D["containers_running"] = len(running)
    D["containers_total"] = len(rows)
    D["containers_stopped"] = stopped
    D["containers_unhealthy"] = unhealthy
    D["containers_healthy"] = sum(1 for r in rows if r[2] == "healthy")
    D["container_restarts"] = restarts
    D["containers"] = f"{len(running)} / {len(rows)} running"
    D["docker_health"] = ("✅ all healthy" if not unhealthy else "❌ unhealthy: " + ", ".join(unhealthy))
    D["docker_restarts"] = ("✅ no restarts" if not restarts else
                            "⚠️ " + ", ".join(f"{k}×{v}" for k, v in sorted(restarts.items(), key=lambda x: -x[1])))


@probe("image_updates")
def _wud():
    # WUD's REST API needs auth on this box; its Prometheus endpoint may be open. Skip quietly if not.
    import urllib.request
    try:
        txt = urllib.request.urlopen("http://127.0.0.1:3002/metrics", timeout=2).read().decode()
    except Exception:
        D["image_updates"] = None
        D["image_updates_display"] = "— see WUD"
        return
    names = set()
    for l in txt.splitlines():
        if l.startswith("wud_containers{") and 'update_available="true"' in l:
            m = re.search(r'name="([^"]+)"', l)
            if m:
                names.add(m.group(1))
    D["image_updates"] = len(names)
    D["image_updates_names"] = sorted(names)
    D["image_updates_display"] = "✅ all current" if not names else f"ℹ️ {len(names)}: " + ", ".join(sorted(names))


# ---------------------------------------------------------------- Network
@probe("wifi")
def _wifi():
    link = sh("iw", "dev", WIFI_IF, "link")
    if not link.startswith("Connected"):
        D["wifi"] = "❌ not connected"
        D["wifi_connected"] = False
        return
    g = lambda pat: (re.search(pat, link) or [None, None])[1]
    sig = g(r"signal: (-?\d+) dBm")
    rx = g(r"rx bitrate: ([\d.]+) MBit/s")
    tx = g(r"tx bitrate: ([\d.]+) MBit/s")
    freq = g(r"freq: ([\d.]+)")
    q = None
    for l in open("/proc/net/wireless"):
        if l.strip().startswith(WIFI_IF + ":"):
            q = float(l.split()[2].rstrip("."))
    qpct = round(q / 70 * 100) if q is not None else None
    band = None
    if freq:
        f = float(freq)
        band = "6 GHz" if f > 5925 else ("5 GHz" if f > 4900 else "2.4 GHz")
    D.update(wifi_connected=True, wifi_signal_dbm=int(sig) if sig else None, wifi_quality_pct=qpct,
             wifi_rx_mbit=float(rx) if rx else None, wifi_tx_mbit=float(tx) if tx else None, wifi_band=band)
    icon = "✅" if sig and int(sig) >= -67 else "⚠️"
    D["wifi"] = f"{icon} {sig} dBm ({qpct}%) · {band} · ↓{rx} ↑{tx} Mbit/s"


@probe("tailscale")
def _ts():
    ts = json.loads(sh("tailscale", "status", "--json", timeout=5) or "{}")
    peers = ts.get("Peer") or {}
    online = sum(1 for p in peers.values() if p.get("Online"))
    state = ts.get("BackendState", "unknown")
    D.update(tailscale_state=state, tailscale_up=state == "Running",
             tailscale_peers=len(peers), tailscale_peers_online=online)
    D["tailscale"] = (f"✅ up · {online}/{len(peers)} peers online" if state == "Running" else f"❌ {state}")


# ---------------------------------------------------------------- pressure / load / top
@probe("pressure")
def _psi():
    psi = {}
    for k in ("cpu", "memory", "io"):
        for l in open(f"/proc/pressure/{k}"):
            kind, *kv = l.split()
            vals = dict(x.split("=") for x in kv)
            psi[f"{k}_{kind}_avg10"] = float(vals["avg10"])
            psi[f"{k}_{kind}_avg60"] = float(vals["avg60"])
    D["psi"] = psi
    D["pressure"] = " · ".join(f"{k} {psi[f'{k}_some_avg60']:.0f}%" for k in ("cpu", "memory", "io")) + " stalled (60 s)"
    worst = max(psi[f"{k}_some_avg60"] for k in ("cpu", "memory"))
    D["memory_pressure"] = (("✅" if psi["memory_some_avg60"] < 5 else "⚠️") +
                            f" {psi['memory_some_avg60']:.1f}% (full {psi['memory_full_avg60']:.1f}%)")
    D["io_pressure"] = (("✅" if psi["io_some_avg60"] < 20 else "⚠️") + f" {psi['io_some_avg60']:.0f}% stalled"
                        + (" (migration copy)" if psi["io_some_avg60"] >= 20 else ""))
    D["cpu_pressure"] = ("✅" if worst < 10 else "⚠️") + f" {psi['cpu_some_avg60']:.1f}%"


@probe("load")
def _load():
    l1, l5, l15 = (float(x) for x in open("/proc/loadavg").read().split()[:3])
    n = os.cpu_count() or 1
    D.update(load1=l1, load5=l5, load15=l15, cpu_threads=n, load_per_core=round(l1 / n, 2))
    D["load"] = f"{l1:.2f} · {l5:.2f} · {l15:.2f}  ({l1 / n:.2f}/core, {n} threads)"
    mem = dict((x.split(":")[0], int(x.split()[1])) for x in open("/proc/meminfo"))
    used = mem["MemTotal"] - mem["MemAvailable"]
    swap = mem["SwapTotal"] - mem["SwapFree"]
    D.update(mem_used_pct=round(used / mem["MemTotal"] * 100, 1), swap_used_mb=swap // 1024)
    D["memory"] = f"{used / 1048576:.1f} / {mem['MemTotal'] / 1048576:.1f} GB ({D['mem_used_pct']:.0f}%) · swap {swap // 1024} MB"


@probe("top")
def _top():
    def snap():
        r = {}
        for p in glob.glob("/proc/[0-9]*/stat"):
            try:
                st = open(p).read()
                name = st[st.index("(") + 1:st.rindex(")")]
                f = st[st.rindex(")") + 2:].split()
                r[p] = (name, int(f[11]) + int(f[12]))
            except Exception:
                continue
        return r
    a = snap()
    time.sleep(0.5)
    b = snap()
    hz = os.sysconf("SC_CLK_TCK")
    agg = {}
    for p, (name, t) in b.items():
        if p in a and a[p][0] == name:
            agg[name] = agg.get(name, 0) + (t - a[p][1])
    top = sorted(((n, v / hz / 0.5 * 100) for n, v in agg.items() if v > 0), key=lambda x: -x[1])[:3]
    D["top_cpu"] = [{"name": n, "cpu_pct": round(c)} for n, c in top]
    D["top_cpu_display"] = " · ".join(f"{n} {c:.0f}%" for n, c in top) or "idle"


# ---------------------------------------------------------------- overall + write
bad = []
if D.get("failed_count"):
    bad.append(f"{D['failed_count']} failed unit(s)")
if D.get("units_bad"):
    bad.append("job(s) failing")
if D.get("smart_warn"):
    bad.append("SMART")
if D.get("containers_unhealthy"):
    bad.append("unhealthy container(s)")
if D.get("tailscale_up") is False:
    bad.append("Tailscale down")
if D.get("wifi_connected") is False:
    bad.append("Wi-Fi down")
info = []
if D.get("reboot_required"):
    info.append("reboot pending")
if D.get("apt_updates"):
    info.append(f"{D['apt_updates']} updates")
D["overall_ok"] = not bad
D["overall"] = ("❌ " + ", ".join(bad) if bad else "✅ all systems nominal") + (" · ℹ️ " + ", ".join(info) if info else "")
D["runtime_s"] = round(time.monotonic() - T0, 2)
if not D["errors"]:
    D["errors"] = []

os.makedirs(os.path.dirname(OUT), exist_ok=True)
tmp = os.path.join(os.path.dirname(OUT), "." + os.path.basename(OUT) + ".tmp")
with open(tmp, "w") as f:
    json.dump(D, f, ensure_ascii=False, indent=1)
os.chmod(tmp, 0o644)
os.replace(tmp, OUT)
