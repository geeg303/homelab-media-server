#!/usr/bin/env python3
# prismcast-watchdog (user Nov 14: "1. Yes"). Every minute: if PrismCast's browser is disconnected (or /health is not
# 'healthy') for 2+ minutes AND nothing is streaming, restart the prismcast container. Max 3 restarts per 6 h, then alert only.
import json, os, subprocess, time, urllib.request
STATE = "/var/lib/media-server/prismcast-watchdog.json"; LOG = "/var/log/media-server/prismcast-watchdog.log"
def log(m):
    with open(LOG, "a") as f: f.write(time.strftime("%Y-%m-%dT%H:%M:%S ") + m + "\n")
def alert(m, high=False):
    t = next((l.split("=", 1)[1].strip() for l in open("/opt/media/stacks/ops/.env") if l.startswith("NTFY_TOPIC=")), "")
    h = {"Title": "box PrismCast"}; h.update({"Priority": "high"} if high else {})
    try: urllib.request.urlopen(urllib.request.Request("https://ntfy.sh/" + t, data=m.encode(), headers=h), timeout=10)
    except Exception: pass
st = json.load(open(STATE)) if os.path.exists(STATE) else {"bad_since": None, "restarts": []}
try:
    d = json.load(urllib.request.urlopen("http://127.0.0.1:5589/health", timeout=5))
    ok = d.get("status") == "healthy" and d.get("browser", {}).get("connected") is True
    active = int(d.get("streams", {}).get("active", 0))
except Exception as e:
    try: d = json.loads(e.read()) if hasattr(e, "read") else {}
    except Exception: d = {}
    ok = False; active = int((d.get("streams") or {}).get("active", 0) or 0)
now = time.time()
st["restarts"] = [r for r in st["restarts"] if now - r < 6 * 3600]
if ok:
    if st["bad_since"]: log(f"recovered after {int(now - st['bad_since'])} s")
    st["bad_since"] = None
else:
    st["bad_since"] = st["bad_since"] or now
    bad = now - st["bad_since"]
    if bad >= 120 and active == 0:
        if len(st["restarts"]) >= 3:
            if not st.get("gave_up"): alert("PrismCast browser still down after 3 automatic restarts in 6 h. Not restarting again; please check (VNC :6080).", True); st["gave_up"] = True
            log("down, restart limit reached")
        else:
            log(f"browser down {int(bad)} s, 0 streams: restarting prismcast")
            r = subprocess.run(["docker", "compose", "restart", "prismcast"], cwd="/opt/media/stacks/livetv", capture_output=True, text=True)
            st["restarts"].append(now); st["bad_since"] = None; st["gave_up"] = False
            log("restart rc=%d" % r.returncode)
            alert("PrismCast's browser had disconnected; restarted it automatically (%d in the last 6 h)." % len(st["restarts"]))
    elif bad >= 120:
        log(f"browser down {int(bad)} s but {active} stream(s) active: waiting")
json.dump(st, open(STATE, "w"))
