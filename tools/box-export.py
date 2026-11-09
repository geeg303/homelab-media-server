#!/usr/bin/env python3
"""Export app settings that live in databases/APIs (not plain files) for the GitHub mirror.
Runs ON the box as root, called by tools/box-collect.sh:  python3 box-export.py <outdir> <secrets-file>
- Reads app API keys from the apps' own config files on the box (never from the command line).
- Redacts secret fields; every redacted value >= 8 chars is appended to <secrets-file> so the final
  value scan proves it appears nowhere in the staged repo.
- Drops volatile fields (timestamps, run stats) so an unchanged setup produces an identical export.
- Prints only names/counts, never values. A failing app is reported and skipped, not fatal."""
import json, os, re, sys, sqlite3, urllib.request, urllib.error, configparser, xml.etree.ElementTree as ET

OUT, SECRETS = sys.argv[1], sys.argv[2]
CFG = "/opt/media/config"
found_secrets = set()
report = []

SECRET_KEY = re.compile(r"(api_?key|apikey|nzb_?key|password|passwd|pass$|secret|token|cookie|salt|jwt|private|vapid|session|"
                        r"clientid|webhook|topic|auth_?hash|http_?hash|pms_uuid|identifier|uuid$|^key$|credential|license|plexid)", re.I)
PERSONAL_KEY = re.compile(r"(username|^user$|^login$|e?mail|plexonline|owner|^ip$|machine)", re.I)
VOLATILE_KEY = re.compile(r"^(last.*|next.*|.*(updated|modified|created|added|scanned|ping|heartbeat)(_?at|_?date|_?time)?|"
                          r".*timestamp.*|uptime|lastrun|.*_?stats?|totals?|.*count|.*percent.*|progress|status|statusmessage|"
                          r"hasupdate|version|_rev|ts|lastexecution|.*duration.*|queue.*|.*_?size)$", re.I)

def redact(v, key=""):
    if isinstance(v, dict):
        # *arr style {"name": "apiKey", "value": "..."} field lists
        if "name" in v and "value" in v and isinstance(v.get("name"), str) and (SECRET_KEY.search(v["name"]) or PERSONAL_KEY.search(v["name"])):
            v = dict(v); v["value"] = mark(v["value"], v["name"])
        return {k: redact(x, k) for k, x in sorted(v.items()) if not VOLATILE_KEY.match(str(k))}
    if isinstance(v, list):
        return [redact(x, key) for x in v]
    if isinstance(v, str) and v[:1] in "{[":
        try: return redact(json.loads(v), key)          # JSON stored inside a DB column (Kuma notification config, etc.)
        except Exception: pass
    if key and (SECRET_KEY.search(key) or PERSONAL_KEY.search(key)):
        return mark(v, key)
    return v

def mark(v, key):
    if v in (None, "", [], {}, 0, False, True):
        return v
    if isinstance(v, (str, int, float)) and SECRET_KEY.search(key):
        s = str(v)
        if len(s) >= 8: found_secrets.add(s)
    return "<REDACTED>"

def write(rel, data):
    p = os.path.join(OUT, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f: json.dump(redact(data), f, indent=2, sort_keys=True, ensure_ascii=False); f.write("\n")

def get(url, headers=None, data=None):
    req = urllib.request.Request(url, headers=headers or {}, data=json.dumps(data).encode() if data is not None else None)
    if data is not None: req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as r: return json.loads(r.read().decode())

def app(name, fn):
    try:
        n = fn(); report.append(f"{name}: {n}")
    except Exception as e:
        report.append(f"{name}: SKIPPED ({type(e).__name__}: {str(e)[:60]})")

def xml_key(path):
    return ET.parse(path).getroot().findtext("ApiKey")

# ---------------- Sonarr / Radarr / Prowlarr ----------------
def arr(name, port, ver, endpoints):
    def run():
        k = xml_key(f"{CFG}/{name}/config.xml"); ok = 0
        for ep in endpoints:
            try:
                d = get(f"http://127.0.0.1:{port}/api/{ver}/{ep}", {"X-Api-Key": k})
            except urllib.error.HTTPError as e:
                if e.code in (404, 405): continue
                raise
            if isinstance(d, list):
                d = sorted(d, key=lambda x: (str(x.get("name", x.get("title", ""))), x.get("id", 0)) if isinstance(x, dict) else str(x))
            write(f"{name}/{ep.replace('/', '-')}.json", d); ok += 1
        return f"{ok} endpoints"
    return run

ARR_COMMON = ["config/host", "config/naming", "config/mediamanagement", "config/ui", "config/downloadclient", "config/indexer",
              "downloadclient", "indexer", "notification", "qualityprofile", "customformat", "qualitydefinition", "rootfolder",
              "tag", "importlist", "importlistexclusion", "delayprofile", "releaseprofile", "remotepathmapping", "metadata", "autotagging"]
app("sonarr", arr("sonarr", 8989, "v3", ARR_COMMON))
app("radarr", arr("radarr", 7878, "v3", ARR_COMMON))
app("prowlarr", arr("prowlarr", 9696, "v1", ["config/host", "config/ui", "indexer", "applications", "downloadclient",
                                              "notification", "tag", "appprofile", "indexerproxy"]))

# ---------------- Bazarr ----------------
def bazarr():
    import yaml
    c = yaml.safe_load(open(f"{CFG}/bazarr/config/config.yaml"))
    k = c["auth"]["apikey"]; h = {"X-API-KEY": k}
    write("bazarr/settings.json", get("http://127.0.0.1:6767/api/system/settings", h))
    write("bazarr/language-profiles.json", get("http://127.0.0.1:6767/api/system/languages/profiles", h))
    return "settings + language profiles"
app("bazarr", bazarr)

# ---------------- ini-file apps ----------------
def ini(name, path, skip_sections=()):
    def run():
        cp = configparser.RawConfigParser(strict=False, interpolation=None); cp.optionxform = str
        txt = open(path, errors="replace").read()
        if not txt.lstrip().startswith("["): txt = "[_top]\n" + txt     # SABnzbd: top-level keys before the first section
        cp.read_string(txt)
        d = {s: dict(cp.items(s)) for s in cp.sections() if s not in skip_sections}
        # SABnzbd keeps servers/categories as [[name]] sub-sections; configparser sees them as "[name]" keys
        write(f"{name}/{os.path.basename(path)}.json", d)
        return f"{len(d)} sections"
    return run
app("sabnzbd", ini("sabnzbd", f"{CFG}/sabnzbd/sabnzbd.ini"))
app("tautulli", ini("tautulli", f"{CFG}/tautulli/config.ini"))

# ---------------- Seerr ----------------
def seerr():
    write("seerr/settings.json", json.load(open(f"{CFG}/seerr/settings.json"))); return "settings.json"
app("seerr", seerr)

# ---------------- Plex ----------------
def plex():
    p = f"{CFG}/plex/Library/Application Support/Plex Media Server/Preferences.xml"
    a = dict(ET.parse(p).getroot().attrib)
    tok = a.get("PlexOnlineToken")
    write("plex/preferences.json", a)
    n = "prefs"
    if tok:
        req = urllib.request.Request("http://127.0.0.1:32400/library/sections", headers={"X-Plex-Token": tok, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r: secs = json.loads(r.read().decode())
        libs = secs.get("MediaContainer", {}).get("Directory", [])
        keep = ("title", "type", "agent", "scanner", "language", "Location")
        write("plex/libraries.json", [{k: v for k, v in L.items() if k in keep} for L in libs])
        n += f" + {len(libs)} libraries"
    return n
app("plex", plex)

# ---------------- SQLite apps (read-only) ----------------
def dump(db, tables, rel):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True); c.row_factory = sqlite3.Row
    have = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
    out = {}
    for t in tables:
        if t in have:
            out[t] = sorted([dict(r) for r in c.execute(f'select * from "{t}"')], key=lambda r: json.dumps(r, sort_keys=True, default=str))
    write(rel, out)
    return f"{len(out)} tables, {sum(len(v) for v in out.values())} rows"

app("uptime-kuma", lambda: dump(f"{CFG}/uptime-kuma/kuma.db",
    ["monitor", "monitor_group", "group", "notification", "monitor_notification", "tag", "monitor_tag", "maintenance",
     "monitor_maintenance", "status_page", "maintenance_status_page", "docker_host", "proxy"], "uptime-kuma/monitors.json"))
app("maintainerr", lambda: dump(f"{CFG}/maintainerr/maintainerr.sqlite",
    ["settings", "rule_group", "rules", "exclusion", "collection", "notification", "notification_rulegroup",
     "radarr_settings", "sonarr_settings", "overlay_settings", "overlay_templates", "log_settings"], "maintainerr/settings.json"))

# ---------------- Tdarr ----------------
def tdarr():
    k = None
    for line in open("/opt/media/stacks/tdarr/.env"):
        if line.startswith("TDARR_API_KEY="): k = line.split("=", 1)[1].strip()
    h = {"x-api-key": k} if k else {}
    n = 0
    for coll, rel in [("FlowsJSONDB", "flows"), ("LibrarySettingsJSONDB", "libraries"), ("SettingsGlobalJSONDB", "settings-global"),
                      ("NodeJSONDB", "nodes")]:
        try:
            d = get("http://127.0.0.1:8266/api/v2/cruddb", h, {"data": {"collection": coll, "mode": "getAll"}})
        except urllib.error.HTTPError:
            continue
        if coll == "NodeJSONDB":   # keep only the node's configuration, not live worker state
            d = [{x: n_.get(x) for x in ("nodeName", "workerLimits", "gpuSelect", "nodePaths", "config", "priority") if x in n_} for n_ in (d or [])]
        if isinstance(d, list): d = sorted(d, key=lambda x: str(x.get("_id", x.get("name", ""))) if isinstance(x, dict) else str(x))
        write(f"tdarr/{rel}.json", d); n += 1
    try: write("tdarr/Tdarr_Server_Config.json", json.load(open(f"{CFG}/tdarr/configs/Tdarr_Server_Config.json")))
    except Exception: pass
    return f"{n} collections"
app("tdarr", tdarr)

with open(SECRETS, "a") as f:
    for s in sorted(found_secrets): f.write(s + "\n")
for line in report: print("export", line)
print(f"export redacted values added to scan: {len(found_secrets)}")
