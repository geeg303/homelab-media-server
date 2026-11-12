#!/usr/bin/env python3
# tdarr-workers: show or set the Tdarr node's transcode worker limits.  Usage: tdarr-workers [status|set <gpu> <cpu>|active]
import json, sys, time, urllib.request
k = next(l.split("=", 1)[1].strip() for l in open("/opt/media/stacks/tdarr/.env") if l.startswith("TDARR_API_KEY="))
H = {"x-api-key": k, "Content-Type": "application/json"}
def get(p):
    with urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8266" + p, headers=H), timeout=30) as x: return json.loads(x.read())
def post(p, d):
    r = urllib.request.Request("http://127.0.0.1:8266" + p, data=json.dumps({"data": d}).encode(), headers=H, method="POST")
    with urllib.request.urlopen(r, timeout=30) as x: return x.status
nodes = get("/api/v2/get-nodes")
cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
if cmd == "set":
    want = {"transcodegpu": int(sys.argv[2]), "transcodecpu": int(sys.argv[3])}
    for nid, n in nodes.items():
        for wt, w in want.items():
            cur = int((n.get("workerLimits") or {}).get(wt, 0) or 0)
            for _ in range(abs(w - cur)): post("/api/v2/alter-worker-limit", {"nodeID": nid, "process": "increase" if w > cur else "decrease", "workerType": wt})
    time.sleep(3); nodes = get("/api/v2/get-nodes")
active = sum(1 for n in nodes.values() for w in (n.get("workers") or {}).values() if str(w.get("workerType", "")).startswith("transcode"))
if cmd == "active": print(active)
else: print(json.dumps({"limits": [n.get("workerLimits") for n in nodes.values()], "active_transcodes": active}))
