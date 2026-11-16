#!/usr/bin/env python3
"""tdarr-pool-switch: once the Show 36 queue is finished, point Tdarr at the whole /data pool (user, Nov 16:
"Point it the whole pool so it starts automatically once show-x is completed").
Run by tdarr-pool-switch.timer every 10 min. Does nothing until ALL of these hold:
  Tdarr queue empty, no transcode running, both scratch output dirs empty (tdarr-swap has placed every encode).
Then, once:
  1. compose: mount /data/media read-only at /media/pool in tdarr + tdarr-node (keeps the legacy disk1 mount), recreate both.
  2. flow "poolAuto": the approved 1080p flow (q22) and 4K HDR10 flow (q20, Dolby Vision skipped) behind a router node
     (height > 1088 -> 4K branch, else 1080p branch). Built from the live flows, so settings stay exactly as approved.
  3. old libraries (pilots + disk1 per-show) set to processLibrary=false; new library "Pool - all TV + movies"
     (folder /media/pool, ignores music/), then a scan-find-new.
  4. ntfy (high), marker file, timer disabled.  Log: /var/log/media-server/tdarr-pool-switch.log"""
import copy, glob, json, os, re, shutil, subprocess, sys, time, urllib.request
MARK = "/var/lib/media-server/tdarr-pool.switched"
LOG = "/var/log/media-server/tdarr-pool-switch.log"
COMPOSE = "/opt/media/stacks/tdarr/compose.nodata.yaml"   # active volume list (!override)
DRY = "--check" in sys.argv
def log(m):
    line = time.strftime("%F %T ") + m; print(line, flush=True)
    if not DRY: open(LOG, "a").write(line + "\n")
def sh(c, check=True):
    r = subprocess.run(c, shell=True, capture_output=True, text=True)
    if check and r.returncode: raise RuntimeError(f"{c[:80]}: {r.stderr.strip()[:300]}")
    return r.stdout.strip()
env = "".join(open(f).read() for f in glob.glob("/opt/media/stacks/*/.env"))
KEY = re.search(r"^TDARR_API_KEY=(\S+)", env, re.M).group(1)
TOPIC = re.search(r"^NTFY_TOPIC=(\S+)", env, re.M).group(1)
def ntfy(title, msg, prio="high"):
    try: urllib.request.urlopen(urllib.request.Request("https://ntfy.sh/" + TOPIC, data=msg.encode(), headers={"Title": "box: " + title, "Priority": prio}), timeout=10)
    except Exception: pass
def post(path, data, port=8265):
    r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps({"data": data}).encode(), headers={"Content-Type": "application/json", "x-api-key": KEY})
    b = urllib.request.urlopen(r, timeout=120).read()
    try: return json.loads(b) if b.strip() else None
    except ValueError: return b.decode(errors="replace")   # e.g. scan-files answers with plain text
def cr(coll, mode, **kw): return post("/api/v2/cruddb", dict(collection=coll, mode=mode, **kw))

def build_flow():
    # ---------- 2. flow
    f1080 = cr("FlowsJSONDB", "getById", docID="hevcQsv1080p"); f4k = cr("FlowsJSONDB", "getById", docID="hdr10Qsv4k")
    plugins, edges = [], []
    inp = next(p for p in f1080["flowPlugins"] if p["id"] == "in"); inp = copy.deepcopy(inp); plugins.append(inp)
    router = copy.deepcopy(next(p for p in f1080["flowPlugins"] if p["id"] == "gate"))
    router["id"] = "route"; router["name"] = "Router: 4K or 1080p"
    router["position"] = {"x": inp["position"]["x"], "y": inp["position"]["y"] + 120}
    router["inputsDB"] = {"code": """
    module.exports = async (args) => {
      // Output 1 = above 1080p -> 4K HDR10 branch (q20, Dolby Vision skipped). Output 2 = 1080p and below -> 1080p branch (q22).
      const st = (args.inputFileObj.ffProbeData && args.inputFileObj.ffProbeData.streams) || [];
      const v = st.find((s) => s.codec_type === 'video') || {};
      const h = Number(v.height || 0);
      args.jobLog('Router: video height ' + h + (h > 1088 ? ' -> 4K branch' : ' -> 1080p branch'));
      return { outputFileObj: args.inputFileObj, outputNumber: h > 1088 ? 1 : 2, variables: args.variables };
    };
    """}
    plugins.append(router); edges.append({"source": "in", "sourceHandle": "1", "target": "route", "targetHandle": None, "id": "e_in_route"})
    for pre, fl, dx, handle in (("k_", f4k, -500, "1"), ("h_", f1080, 500, "2")):
        for p in fl["flowPlugins"]:
            if p["id"] == "in": continue
            q2 = copy.deepcopy(p); q2["id"] = pre + p["id"]
            q2["position"] = {"x": p["position"]["x"] + dx, "y": p["position"]["y"] + 240}
            plugins.append(q2)
        for e in fl["flowEdges"]:
            e2 = copy.deepcopy(e)
            if e["source"] == "in": e2["source"] = "route"; e2["sourceHandle"] = handle
            else: e2["source"] = pre + e["source"]
            e2["target"] = pre + e["target"]; e2["id"] = f"{pre}{e.get('id') or e['source'] + '_' + e['target']}_{e.get('sourceHandle')}"
            edges.append(e2)
    ids = {p["id"] for p in plugins}
    bad = [e for e in edges if e["source"] not in ids or e["target"] not in ids]
    if bad: raise RuntimeError(f"flow edges point to missing nodes: {bad[:2]}")
    flow = {"_id": "poolAuto", "name": "Pool - auto: 1080p q22 / 4K HDR10 q20 (output to scratch, swapped by tdarr-swap)",
            "description": "Router by height into the approved 1080p and 4K HDR10 flows (copied Nov 16). Dolby Vision, already-encoded and low-bitrate files are skipped.",
            "tags": "", "flowPlugins": plugins, "flowEdges": edges}
    if cr("FlowsJSONDB", "getById", docID="poolAuto"): cr("FlowsJSONDB", "update", docID="poolAuto", obj=flow)
    else: cr("FlowsJSONDB", "insert", docID="poolAuto", obj=flow)
    log(f"flow poolAuto saved: {len(plugins)} nodes, {len(edges)} edges")


if "--build-flow-only" in sys.argv:
    build_flow(); sys.exit(0)
if os.path.exists(MARK): print("already switched"); sys.exit(0)
# ---------- gate
q = cr("StatisticsJSONDB", "getById", docID="statistics").get("table1Count", 1)
active = int(sh("/usr/local/sbin/tdarr-workers active", check=False) or 99)
if q or active:
    print(f"waiting: queue {q}, active {active}"); sys.exit(0)
sh("/usr/local/sbin/tdarr-swap /scratch/tdarr/output-1080p >/dev/null 2>&1; /usr/local/sbin/tdarr-swap /scratch/tdarr/output-4k >/dev/null 2>&1", check=False)
left = sh("find /scratch/tdarr/output-1080p /scratch/tdarr/output-4k -type f \\( -name '*.mkv' -o -name '*.mp4' \\) | wc -l", check=False)
if left != "0":
    print(f"waiting: {left} encodes not swapped yet (failed checks stay put: see tdarr-swap.log)")
    # an encode that failed its checks would block forever: allow the switch if nothing changed for 2 h
    newest = sh("find /scratch/tdarr/output-1080p /scratch/tdarr/output-4k -type f -printf '%T@\\n' | sort -n | tail -1", check=False)
    if not newest or time.time() - float(newest) < 7200: sys.exit(0)
    log(f"{left} encodes left in output (failed verification, kept for review); switching anyway")
if DRY: print("CHECK: all gates passed, would switch now"); sys.exit(0)
try:
    log("Show 36 queue finished: switching Tdarr to the whole pool")
    # ---------- 1. compose
    c = open(COMPOSE).read()
    old = "/mnt/disk1/media/tv:/media/disk1/tv:ro"
    if "/data/media:/media/pool:ro" not in c:
        n = c.count(old)
        if n != 2: raise RuntimeError(f"expected 2 disk1 mount lines in compose, found {n}")
        shutil.copy2(COMPOSE, COMPOSE + time.strftime(".bak-%Y%m%d-%H%M%S"))
        lines = c.split("\n"); out = []
        for l in lines:
            out.append(l)
            if old in l:
                ind = l[: len(l) - len(l.lstrip())]
                out.append(f"{ind}- /data/media:/media/pool:ro      # whole pool, read-only; encodes go to /scratch, tdarr-swap replaces (Nov 16)")
        open(COMPOSE, "w").write("\n".join(out))
    sh("cd /opt/media/stacks/tdarr && docker compose config -q && docker compose up -d tdarr tdarr-node")
    for _ in range(36):
        time.sleep(5)
        try:
            nodes = post("/api/v2/get-nodes", {}, port=8266) if False else json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8266/api/v2/get-nodes", headers={"x-api-key": KEY}), timeout=10))
            if nodes: break
        except Exception: pass
    else: raise RuntimeError("tdarr node did not come back within 3 min")
    if not sh("docker exec tdarr ls /media/pool/tv | head -1") or not sh("docker exec tdarr-node ls /media/pool/movies | head -1"):
        raise RuntimeError("/media/pool not visible in the containers")
    log("compose: /data/media -> /media/pool (ro) in tdarr + tdarr-node; node back")
    sh("/usr/local/sbin/tdarr-workers set 2 0", check=False)
    build_flow()
    # ---------- 3. libraries
    libs = cr("LibrarySettingsJSONDB", "getAll"); libs = list(libs.values()) if isinstance(libs, dict) else libs
    for l in libs:
        if l["_id"] != "libPool" and l.get("processLibrary"):
            cr("LibrarySettingsJSONDB", "update", docID=l["_id"], obj={"processLibrary": False, "scanOnStart": False, "folderWatching": False})
    tpl = cr("LibrarySettingsJSONDB", "getById", docID="lib1080_LoveIsland")
    lib = copy.deepcopy(tpl)
    lib.update({"_id": "libPool", "name": "Pool - all TV + movies", "folder": "/media/pool", "flowId": "poolAuto",
                "cache": "/scratch/tdarr/cache", "priority": 0, "processLibrary": True, "processHealthChecks": False,
                "scanOnStart": False, "folderWatching": False, "scheduledScanFindNew": False,
                "foldersToIgnore": "music", "foldersToIgnoreCaseInsensitive": True, "totalTranscodeCount": 0,
                "totalHealthCheckCount": 0, "sizeDiff": 0, "scanFound": "Files found:0", "createdAt": int(time.time() * 1000)})
    lib["decisionMaker"]["settingsPlugin"] = False; lib["decisionMaker"]["settingsFlows"] = True
    if cr("LibrarySettingsJSONDB", "getById", docID="libPool"): cr("LibrarySettingsJSONDB", "update", docID="libPool", obj=lib)
    else: cr("LibrarySettingsJSONDB", "insert", docID="libPool", obj=lib)
    post("/api/v2/scan-files", {"scanConfig": {"dbID": "libPool", "arrayOrPath": "/media/pool", "mode": "scanFindNew"}})
    log("old libraries paused; library libPool (/media/pool, flow poolAuto) created; scan started")
    open(MARK, "w").write(time.strftime("%F %T\n"))
    sh("systemctl disable --now tdarr-pool-switch.timer", check=False)
    ntfy("Tdarr: Show 36 done, now on the whole pool",
         "Show 36 queue finished. Tdarr now scans the whole /data pool (TV + movies, 1080p q22 and 4K HDR10 q20, Dolby Vision skipped). Encodes are verified and swapped in by tdarr-swap.")
    log("done")
except Exception as e:
    log(f"ERROR: {e}")
    ntfy("Tdarr pool switch FAILED", f"{e} (Show 36 is finished; Tdarr left as it was where possible). Log: {LOG}", "urgent")
    sh("systemctl disable --now tdarr-pool-switch.timer", check=False)
    sys.exit(1)
