#!/usr/bin/env python3
"""Migration progress for the Homepage dashboard.
Reads only cheap sources (process list, df, migrate logs, du on the ext4 destination) and writes
/opt/media/status/migration.json, which a tiny read-only web container serves to Homepage.
Runs every minute from migration-status.timer. Never touches the NTFS disks except `ls` of the source dirs."""
import json, os, re, subprocess, time, glob, datetime

OUT = "/opt/media/status/migration.json"
STATE = "/var/lib/media-server/migration-status-state.json"
CONF = "/etc/media-server/migration-rounds.json"   # per-round details, added as each round is scripted
LOGDIR = "/var/log/migrate"
TOTAL_ALL = 29.878e12

DEFAULT_ROUNDS = {
    "1": {"label": "sdc → staging on sda + sdd", "total": 4.280e12, "format": "sdc → disk1"},
    "2": {"label": "sda → disk1", "total": 7.284e12, "format": "sda → disk2", "baseline": 0,
          "sources": ["/mnt/mig/sda/TV", "/mnt/mig/sda/_from_sdc/TV Shows"], "dest_shows": "/mnt/disk1/media/tv"},
    "3": {"label": "sdd → pool", "total": 7.212e12, "format": "sdd → disk3"},
    "4": {"label": "sde → pool", "total": 7.910e12, "format": "sde → disk4"},
    "5": {"label": "sdb → pool", "total": 7.472e12, "format": "sdb → parity1"},
}

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout

def load(p, d):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return d

def tb(b): return f"{b/1e12:.2f} TB"

def bar(frac, width=20):
    frac = max(0.0, min(1.0, frac)); n = int(frac * width)
    return "█" * n + "░" * (width - n) + f" {frac*100:5.1f}%"

def hm(sec):
    if sec is None or sec < 0: return "–"
    h, m = divmod(int(sec // 60), 60); d, h = divmod(h, 24)
    return (f"{d}d " if d else "") + f"{h}h {m:02d}m"

def at(sec):
    if sec is None: return ""
    t = datetime.datetime.now() + datetime.timedelta(seconds=sec)
    return t.strftime(" (≈ %a %-I:%M %p)")

rounds = DEFAULT_ROUNDS
cfg = load(CONF, {})
for k, v in cfg.items(): rounds.setdefault(k, {}).update(v)
state = load(STATE, {"samples": [], "sizes": {}, "verify_start": {}, "baseline": {}})

def done(n):
    p = f"{LOGDIR}/round{n}-verify.log"
    return os.path.exists(p) and re.search(r"VERIFY TOTAL differences=", open(p, errors="replace").read()) is not None

procs = sh("ps -eo pid,stat,args")
running = [int(m.group(1)) for m in re.finditer(r"migrate-round(\d)", procs)]
cur = str(running[0]) if running else None
if cur is None:  # nothing running: the latest round with a log is "current"
    have = sorted(int(re.search(r"round(\d)\.log", p).group(1)) for p in glob.glob(f"{LOGDIR}/round[0-9].log"))
    cur = str(have[-1]) if have else "1"
R = rounds[cur]
log = f"{LOGDIR}/round{cur}.log"
vlog = f"{LOGDIR}/round{cur}-verify.log"
logtxt = open(log, errors="replace").read() if os.path.exists(log) else ""
vtxt = open(vlog, errors="replace").read() if os.path.exists(vlog) else ""

rs_lines = [l for l in procs.splitlines() if " rsync " in f" {l} " and "rsync" in l.split()[2]]
verifying_proc = any(" -rc " in l or "--dry-run" in l for l in rs_lines)
paused = any(l.split()[1].startswith("T") for l in rs_lines)
verify_lines = re.findall(r"^VERIFY \[[^\]]+\] (.+): differences=(\d+)$", vtxt, re.M)
verify_total_line = re.search(r"VERIFY TOTAL differences=(\d+)", vtxt)

# shows
shows_total = 0
for s in R.get("sources", []):
    try: shows_total += len([d for d in os.listdir(s) if not d.startswith(("$", "System Volume"))])
    except Exception: pass
copy_started = re.findall(r"^=== \S+ COPY (.+)$", logtxt, re.M)
copy_phase_done = bool(verify_lines) or verifying_proc or verify_total_line is not None or (cur in [str(x) for x in range(1, 6)] and done(cur))

# copy bytes = destination growth since the round started
used = sum(int(x) for x in sh("df -B1 --output=used " + " ".join(sorted(glob.glob("/mnt/disk[0-9]*"))) + " 2>/dev/null | tail -n +2").split())
base = R.get("baseline", state["baseline"].get(cur))
if base is None:
    base = used; state["baseline"][cur] = used
copied = max(0, used - base)
total = R["total"]
copy_frac = 1.0 if copy_phase_done else min(copied / total, 0.999)

# copy rate / ETA from samples (last 20 min)
now = time.time()
smp = [s for s in state.get("samples", []) if s[0] > now - 1200 and s[2] == cur] + [[now, copied, cur]]
state["samples"] = smp
rate = (smp[-1][1] - smp[0][1]) / (smp[-1][0] - smp[0][0]) if len(smp) > 1 and smp[-1][0] > smp[0][0] else None
copy_eta = (total - copied) / rate if (rate and rate > 0 and not copy_phase_done) else None

# verify progress by verified bytes (destination size per verified show, cached)
dest = R.get("dest_shows")
vbytes = 0
for name, _ in verify_lines:
    key = f"{cur}:{name}"
    if key not in state["sizes"] and dest:
        out = sh(f"du -sb {json.dumps(os.path.join(dest, name))} 2>/dev/null").split()
        state["sizes"][key] = int(out[0]) if out else 0
    vbytes += state["sizes"].get(key, 0)
diffs = sum(int(d) for _, d in verify_lines)
if verify_total_line: vfrac = 1.0
elif verify_lines or verifying_proc: vfrac = min(vbytes / total, 0.999)
else: vfrac = 0.0
if (verify_lines or verifying_proc) and cur not in state["verify_start"]:
    state["verify_start"][cur] = now
vstart = state["verify_start"].get(cur)
verify_eta = None
if vstart and 0.02 < vfrac < 1.0:
    verify_eta = (now - vstart) * (1 - vfrac) / vfrac
elif not copy_phase_done:
    verify_eta = None

# stage
if paused:
    stage = "⏸️ PAUSED by USB watchdog (check ntfy)"
elif verify_total_line and R.get("formatted"):
    stage = f"✅ Round {cur} done · {R['format']} formatted"
elif verify_total_line:
    stage = f"✅ Round {cur} verified · waiting for your 'format {R['format'].split()[0]}'"
elif verify_lines or verifying_proc:
    cur_show = verify_lines[-1][0] if verify_lines else "starting"
    stage = f"🔍 Checksum check · {len(verify_lines)}/{shows_total or '?'} shows done"
elif running:
    stage = f"📦 Copying · show {len(copy_started)}/{shows_total or '?'}: {copy_started[-1] if copy_started else '…'}"
else:
    stage = "⏳ Idle"

# ETA line
if verify_total_line and R.get("formatted"):
    eta = "Next: " + R.get("next", "the next round")
elif verify_total_line:
    eta = "Round done · next: your format OK, then the next round"
elif copy_phase_done:
    eta = f"Checksum check: {hm(verify_eta)}{at(verify_eta)}" if verify_eta else "Checksum check: estimating…"
else:
    eta = f"Copy: {hm(copy_eta)}{at(copy_eta)}" + (f" · {rate/1e6:.0f} MB/s" if rate else "") + " · then checksum ≈ 20–27 h"

# overall
done_rounds = [n for n in sorted(rounds) if done(n)]
moved = sum(rounds[n]["total"] for n in done_rounds) + (0 if cur in done_rounds else (total if copy_phase_done else copied))
icons = []
for n in sorted(rounds):
    icons.append(f"R{n} " + ("✅" if n in done_rounds else ("🔍" if n == cur and copy_phase_done else ("📦" if n == cur else "⬜"))))

wd = sh("systemctl is-active usb-watchdog").strip()
kern = sh("journalctl -k --since '-30 min' --no-pager 2>/dev/null | grep -ciE 'usb .*reset|i/o error|disconnect'").strip() or "0"
health = f"watchdog {wd} · USB/disk errors (30 min): {kern}"
if verify_lines or verify_total_line:
    health += f" · differences so far: {diffs} (only the 5 dup shows may differ)"

data = {
    "round": f"{cur} of 5 · {R['label']}",
    "stage": stage,
    "copy_bar": bar(copy_frac) + f"  {tb(total if copy_phase_done else copied)} / {tb(total)}",
    "verify_bar": bar(vfrac) + (f"  {tb(total if verify_total_line else vbytes)} / {tb(total)}" if (verify_lines or verify_total_line) else "  starts after the copy"),
    "eta": eta,
    "overall_bar": bar(moved / TOTAL_ALL) + f"  {tb(moved)} / {tb(TOTAL_ALL)}",
    "rounds": "  ".join(icons),
    "health": health,
    "updated": datetime.datetime.now().strftime("%a %-I:%M %p"),
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
tmp = OUT + ".tmp"
with open(tmp, "w") as f: json.dump(data, f, ensure_ascii=False, indent=1)
os.chmod(tmp, 0o644); os.replace(tmp, OUT)
os.makedirs(os.path.dirname(STATE), exist_ok=True)
with open(STATE, "w") as f: json.dump(state, f)
