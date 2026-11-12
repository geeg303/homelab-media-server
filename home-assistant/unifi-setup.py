#!/usr/bin/env python3
# UniFi setup (prepared Nov 11, run after user saves ~/.unifi_creds on the box: line 1 username, 2 password, 3 API key optional).
# Run on the box as root:  ssh box 'sudo -n python3 -' < unifi-setup.py
# 1) moves the creds to /etc/media-server/unifi-creds (600)  2) checks the login and that the account is NOT an admin
# 3) adds HA's UniFi Network integration (read-only account; client blocking / DPI / PoE stay off)
# 4) Homepage: HOMEPAGE_VAR_UNIFI_KEY in ops/homepage.env + "UniFi" tile in Ops, recreates only the homepage container.
# Never prints a secret.
import json, os, shutil, ssl, subprocess, sys, time, urllib.request, urllib.error, http.cookiejar
CONSOLE = "https://192.0.2.1"          # UniFi Dream Router 7 (UniFi OS, Network app under /proxy/network)
SRC, DST = "/home/user/.unifi_creds", "/etc/media-server/unifi-creds"
if os.path.exists(SRC):
    shutil.move(SRC, DST)
os.chmod(DST, 0o600); os.chown(DST, 0, 0)
lines = [l.strip() for l in open(DST) if l.strip()]
if len(lines) < 2: sys.exit("ABORT: need username and password lines")
user, pw, key = lines[0], lines[1], (lines[2] if len(lines) > 2 else "")
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), urllib.request.HTTPCookieProcessor(jar))
def u(method, path, body=None, headers=None):
    r = urllib.request.Request(CONSOLE + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                               headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with op.open(r, timeout=20) as x: return x.status, json.loads(x.read() or b"null"), dict(x.headers)
    except urllib.error.HTTPError as e: return e.code, None, dict(e.headers)
s, _, h = u("POST", "/api/auth/login", {"username": user, "password": pw, "rememberMe": False})
print("UniFi login:", s)
if s != 200: sys.exit("ABORT: login failed (check the username/password, and that it's a LOCAL account)")
csrf = h.get("X-Updated-Csrf-Token") or h.get("X-Csrf-Token") or ""
s, me, _ = u("GET", "/proxy/network/api/s/default/self", headers={"X-Csrf-Token": csrf})
role = ((me or {}).get("data") or [{}])[0]
print("Network role:", role.get("role"), "| is_super:", role.get("is_super"), "| site:", role.get("site_name"))
if role.get("role") == "admin" or role.get("is_super"):
    sys.exit("ABORT: this account is an admin. Set its Network role to View Only (read-only), then re-run.")
if key:
    s, sites, _ = u("GET", "/proxy/network/integration/v1/sites", headers={"X-API-KEY": key})
    print("API key check:", s, "| sites:", len((sites or {}).get("data", [])) if isinstance(sites, dict) else "?")
    if s != 200: print("WARN: API key rejected; Homepage will use the username/password instead"); key = ""
# --- Home Assistant
T = next(l.strip() for l in open("/etc/media-server/ha-token") if len(l.strip()) > 100)
def ha(m, p, b=None):
    q = urllib.request.Request("http://192.0.2.150" + p, data=json.dumps(b).encode() if b is not None else None, method=m,
                               headers={"Authorization": "Bearer " + T, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(q, timeout=60) as x: return json.loads(x.read() or b"null")
    except urllib.error.HTTPError as e: return {"http": e.code, "body": e.read()[:300].decode()}
entries = ha("GET", "/api/config/config_entries/entry")
ent = next((e for e in entries if e["domain"] == "unifi"), None)
if not ent:
    f = ha("POST", "/api/config/config_entries/flow", {"handler": "unifi"})
    r = ha("POST", f"/api/config/config_entries/flow/{f['flow_id']}",
           {"host": "192.0.2.1", "username": user, "password": pw, "port": 443, "verify_ssl": False})
    if r.get("type") == "form" and r.get("step_id") == "site":   # more than one site: pick default
        r = ha("POST", f"/api/config/config_entries/flow/{f['flow_id']}", {"site": r["data_schema"][0].get("default") or "default"})
    print("HA UniFi:", r.get("type"), r.get("title") or r.get("errors") or r.get("reason") or r.get("body"))
    if r.get("type") != "create_entry": sys.exit("ABORT: HA config flow failed")
    time.sleep(15)
    ent = next(e for e in ha("GET", "/api/config/config_entries/entry") if e["domain"] == "unifi")
# options: presence on (wireless only), no client blocking, no DPI control; bandwidth sensors only on chosen clients later
o = ha("POST", "/api/config/config_entries/options/flow", {"handler": ent["entry_id"]})
steps = 0
while o.get("type") == "form" and steps < 6:
    steps += 1
    names = [x["name"] for x in o.get("data_schema", [])]
    data = {}
    for x in o.get("data_schema", []):
        n = x["name"]
        if n in ("block_client", "dpi_restrictions"): data[n] = [] if x.get("type") == "multi_select" or n == "block_client" else False
        elif n in ("track_clients", "track_devices"): data[n] = True
        elif n == "track_wired_clients": data[n] = False
        elif n in ("allow_bandwidth_sensors", "allow_uptime_sensors"): data[n] = False
        elif "default" in x: data[n] = x["default"]
    if "dpi_restrictions" in names: data["dpi_restrictions"] = False
    print(" options step", o.get("step_id"), "->", {k: v for k, v in data.items() if k in ("block_client", "dpi_restrictions", "track_clients", "track_wired_clients", "track_devices", "allow_bandwidth_sensors")})
    o = ha("POST", f"/api/config/config_entries/options/flow/{o['flow_id']}", data)
print("options:", o.get("type"))
# --- Homepage
envf = "/opt/media/stacks/ops/homepage.env"
env = open(envf).read()
lines_env = [l for l in env.splitlines() if not l.startswith(("HOMEPAGE_VAR_UNIFI_KEY=", "HOMEPAGE_VAR_UNIFI_USER=", "HOMEPAGE_VAR_UNIFI_PASS="))]
if key: lines_env.append("HOMEPAGE_VAR_UNIFI_KEY=" + key)
else: lines_env += ["HOMEPAGE_VAR_UNIFI_USER=" + user, "HOMEPAGE_VAR_UNIFI_PASS=" + pw]
shutil.copy2(envf, envf + ".bak-unifi")
open(envf, "w").write("\n".join(lines_env) + "\n"); os.chmod(envf, 0o600)
SF = "/opt/media/config/homepage/services.yaml"
s = open(SF).read()
if "type: unifi" not in s:
    import yaml
    auth = ("          key: \"{{HOMEPAGE_VAR_UNIFI_KEY}}\"\n" if key else
            '          username: "{{HOMEPAGE_VAR_UNIFI_USER}}"\n          password: "{{HOMEPAGE_VAR_UNIFI_PASS}}"\n')
    tile = ("    - UniFi:\n        href: https://192.0.2.1\n        icon: unifi.png\n        description: \"Dream Router 7 · read-only\"\n"
            "        widget:\n          type: unifi\n          url: https://192.0.2.1\n" + auth +
            "          fields: [\"uptime\", \"wan\", \"wlan_users\", \"lan_users\"]\n")
    anchor = "    - Uptime Kuma:\n"
    assert s.count(anchor) == 1, "Uptime Kuma tile anchor not found"
    shutil.copy2(SF, SF + ".bak-unifi")
    s = s.replace(anchor, tile + anchor, 1); yaml.safe_load(s); open(SF, "w").write(s); os.chown(SF, 1000, 1000)
subprocess.run(["docker", "compose", "up", "-d", "homepage"], cwd="/opt/media/stacks/ops", check=True, capture_output=True)
time.sleep(12)
r = subprocess.run(["curl", "-s", "http://127.0.0.1:3000/api/services/proxy?group=Ops&service=UniFi&index=0"], capture_output=True, text=True).stdout
print("Homepage UniFi widget:", "ok" if r.strip().startswith(("{", "[")) and "error" not in r.lower()[:200] else r[:160])
print("done")
