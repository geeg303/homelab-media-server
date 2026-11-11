#!/usr/bin/env python3
# selftest-status: progress of SMART long self-tests on the second-enclosure WD drives -> /opt/media/status/selftest.json (Homepage).
# Also runs every 2 min, which keeps the JMicron bridge from idling the drives mid-test. Read-only (smartctl -c / -l selftest / -A).
import json, re, subprocess, time, datetime, os
DRIVES = ["SERIAL-WD1", "7SJ8JDXW", "7HJY59ZF", "7HJY82BF", "7HK2YR2H"]   # bays 1-5
STATE = "/var/lib/media-server/selftest-start.json"
def sh(*a): return subprocess.run(a, capture_output=True, text=True).stdout
def dev(serial):
    for n in os.listdir("/dev/disk/by-id"):
        if n.startswith("ata-") and n.endswith("_" + serial) and "-part" not in n:
            return os.path.realpath("/dev/disk/by-id/" + n)
start = json.load(open(STATE)) if os.path.exists(STATE) else {}
def bar(p, w=14): f = int(round(p / 100 * w)); return "█" * f + "░" * (w - f) + f" {p:3.0f}%"
out, worst, done, fail = {}, 100, 0, 0
for i, s in enumerate(DRIVES, 1):
    d = dev(s)
    if not d: out[f"bay{i}"] = f"{s}: not found"; fail += 1; continue
    c = sh("smartctl", "-d", "sat", "-c", d)
    m = re.search(r"Self-test execution status:\s*\(\s*(\d+)\)(.*?)(?:\n\S|\Z)", c, re.S)
    code = int(m.group(1)) if m else -1
    temp = re.search(r"^194 .* (\d+)(?: \(|$)", sh("smartctl", "-d", "sat", "-A", d), re.M)
    t = f" · {temp.group(1)}°C" if temp else ""
    if code >> 4 == 15:   # in progress, low nibble = remaining tenths
        rem = (code & 15) * 10; p = 100 - rem
        st = start.get(s); eta = ""
        mins = re.search(r"Extended self-test routine\s*recommended polling time:\s*\(\s*(\d+)\)", c)
        if st and mins:   # drive's own estimate; progress itself only moves in 10% steps
            eta = " · ETA " + datetime.datetime.fromtimestamp(st + int(mins.group(1)) * 60).strftime("%a %H:%M")
        out[f"bay{i}"] = f"{bar(p)}  {s}{t}{eta}"; worst = min(worst, p)
    else:
        log = sh("smartctl", "-d", "sat", "-l", "selftest", d)
        first = next((l for l in log.splitlines() if re.match(r"^# ?1 ", l)), "")
        if "Extended offline" in first and "Completed without error" in first:
            out[f"bay{i}"] = f"✅ passed  {s}{t}"; done += 1
        elif first and "Extended offline" in first:
            out[f"bay{i}"] = f"❌ {re.sub(r'\s+', ' ', first[25:70]).strip()}  {s}"; fail += 1
        else:
            out[f"bay{i}"] = f"… not started  {s}{t}"; worst = 0
n = len(DRIVES)
out["now"] = ("✅ all passed" if done == n else f"❌ {fail} failed · {done} passed" if fail else f"🔎 testing · {done}/{n} passed · slowest at {worst}%")
out["updated"] = datetime.datetime.now().strftime("%H:%M")
tmp = "/opt/media/status/selftest.json.tmp"
json.dump(out, open(tmp, "w"), ensure_ascii=False, indent=1); os.replace(tmp, "/opt/media/status/selftest.json")
