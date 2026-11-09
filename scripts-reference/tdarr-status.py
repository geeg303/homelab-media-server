#!/usr/bin/env python3
"""Live Tdarr conversion status for the Homepage dashboard.
Reads Tdarr's API (key from /opt/media/stacks/tdarr/.env, never printed) and the pilot folders on /scratch,
writes /opt/media/status/tdarr.json (served by the read-only 'status' container). Runs every 30 s from tdarr-status.timer."""
import json, os, re, time, datetime, urllib.request

OUT = "/opt/media/status/tdarr.json"
PILOT_IN = "/scratch/tdarr/pilot-input"
PILOT_OUT = "/scratch/tdarr/output"
VIDEO = (".mkv", ".mp4", ".m4v", ".avi", ".mov", ".ts", ".m2ts")

def key():
    for l in open("/opt/media/stacks/tdarr/.env"):
        if l.startswith("TDARR_API_KEY="): return l.split("=", 1)[1].strip()
H = {"x-api-key": key() or "", "Content-Type": "application/json"}

def call(path, data=None):
    r = urllib.request.Request("http://127.0.0.1:8266" + path, headers=H,
                               data=json.dumps(data).encode() if data is not None else None, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(r, timeout=15) as x:
        b = x.read(); return json.loads(b) if b else None

def short(path):
    """'Show 23 - S01E07 - Episode Bluray-1080p Remux.mkv' -> 'Show 23 S01E07'"""
    b = os.path.basename(str(path))
    m = re.match(r"(.+?) - (S\d+E\d+)", b, re.I)
    return f"{m.group(1)} {m.group(2).upper()}" if m else os.path.splitext(b)[0][:45]

def num(v):
    try: return float(v)
    except Exception: return None

def mins(sec):
    if sec is None or sec < 0: return "–"
    m, s = divmod(int(sec), 60); h, m = divmod(m, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"

def bar(frac, width=14):
    frac = max(0.0, min(1.0, frac)); n = int(frac * width)
    return "█" * n + "░" * (width - n)

data = {"updated": datetime.datetime.now().strftime("%a %-I:%M:%S %p")}
try:
    nodes = call("/api/v2/get-nodes") or {}
    jobs, limits, paused = [], {}, False
    for node in nodes.values():
        limits = node.get("workerLimits") or {}
        paused = paused or bool(node.get("nodePaused"))
        for w in (node.get("workers") or {}).values():
            pct = num(w.get("percentage")) or 0.0
            fps = num(w.get("fps"))
            eta = w.get("ETA") or w.get("eta")
            typ = {"transcodegpu": "GPU", "transcodecpu": "CPU", "healthcheckgpu": "check (GPU)",
                   "healthcheckcpu": "check (CPU)"}.get(str(w.get("workerType", "")), str(w.get("workerType", "")))
            line = f"{bar(pct/100)} {pct:4.1f}%  {short(w.get('file', '?'))}"
            extra = [x for x in (typ, f"{fps:.0f} fps" if fps else None, f"ETA {eta}" if eta else None) if x]
            jobs.append(line + ("  · " + " · ".join(str(e) for e in extra) if extra else ""))
    st = call("/api/v2/cruddb", {"data": {"collection": "StatisticsJSONDB", "mode": "getById", "docID": "statistics"}}) or {}
    q, ok, err = st.get("table1Count", 0), st.get("table2Count", 0), st.get("table3Count", 0)
    saved = num(st.get("sizeDiff")) or 0.0
    gpu = int(limits.get("transcodegpu", 0) or 0); cpu = int(limits.get("transcodecpu", 0) or 0)
    if paused: now = "⏸️ node paused"
    elif jobs: now = f"🎞️ {len(jobs)} converting · {q} queued"
    elif gpu + cpu == 0: now = "💤 idle · workers off (pilot not running)"
    elif q: now = f"⏳ {q} queued, waiting for a worker"
    else: now = "✅ idle · nothing queued"
    data.update({
        "now": now,
        "job1": jobs[0] if len(jobs) > 0 else "—",
        "job2": jobs[1] if len(jobs) > 1 else "—",
        "totals": f"queue {q} · done {ok} · errors {err}",
        "saved": f"{saved:.2f} GB saved (Tdarr total)",
        "workers": f"GPU encode {gpu} · CPU encode {cpu} · health check {int(limits.get('healthcheckcpu', 0) or 0)}",
    })
except Exception as e:
    data.update({"now": f"⚠️ Tdarr API unreachable ({type(e).__name__})", "job1": "—", "job2": "—", "totals": "–", "saved": "–", "workers": "–"})

# pilot results: originals in pilot-input vs encodes in output (matched by file name without extension)
def walk(d):
    out = {}
    for root, _, files in os.walk(d):
        for f in files:
            if f.lower().endswith(VIDEO):
                out[os.path.splitext(f)[0]] = os.path.getsize(os.path.join(root, f))
    return out
ins, outs = walk(PILOT_IN), walk(PILOT_OUT)
done = [k for k in outs if k in ins]
if ins:
    a = sum(ins[k] for k in done); b = sum(outs[k] for k in done)
    data["pilot"] = (f"{len(done)}/{len(ins)} encoded · {a/1e9:.1f} GB → {b/1e9:.1f} GB ({(1 - b/a)*100:.0f}% smaller)"
                     if done else f"0/{len(ins)} encoded yet ({sum(ins.values())/1e9:.1f} GB of test copies)")
else:
    data["pilot"] = "no pilot files"

# replacements done by tdarr-swap (originals held on disk2 until user OKs deleting them)
try:
    sw = [l for l in open("/var/log/media-server/tdarr-swap.log", errors="replace") if " SWAPPED " in l or " FAIL " in l]
    n_ok = sum(1 for l in sw if " SWAPPED " in l); n_bad = sum(1 for l in sw if " FAIL " in l)
    saved_b = 0
    for l in sw:
        m = re.search(r"\| (\d+) -> (\d+) bytes", l)
        if m and " SWAPPED " in l: saved_b += int(m.group(1)) - int(m.group(2))
    pend = len([f for _, _, fs in os.walk("/scratch/tdarr/output-4k") for f in fs if f.lower().endswith(VIDEO)])
    data["swap"] = f"{n_ok} replaced in library · {saved_b/1e9:.1f} GB freed on disk1 · {pend} waiting · {n_bad} failed checks"
except FileNotFoundError:
    data["swap"] = "no replacements yet"

os.makedirs(os.path.dirname(OUT), exist_ok=True)
tmp = OUT + ".tmp"
with open(tmp, "w") as f: json.dump(data, f, ensure_ascii=False, indent=1)
os.chmod(tmp, 0o644); os.replace(tmp, OUT)
