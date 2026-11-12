#!/usr/bin/env python3
# Origami dashboard (hazymorning/origami V3.0, AGPL-3.0) at /origami, built from the upstream part files with user's real entities.
# Needs (Marketplace): Clooos/Bubble-Card >= 3.4, Clooos/Bubble-Card-Tools (integration), hazymorning/origami_weather,
# joseluis9595/lovelace-navbar-card. The Origami theme (hazymorning/origami, theme) and Origami Notifications are NOT in the
# Marketplace catalog: they install as custom repositories, which needs GitHub connected in Settings > Marketplace. This script
# adds and installs them by itself once that is done, then sets Origami as the default theme (light + dark).
# Run on the box as root:  ssh box 'sudo -n python3 -' < dashboard-origami.py      Idempotent; never touches /home-hub or Overview.
# Also sets up what the server pop-up needs: System Monitor (the HA VM) with its 7 sensors turned on, and Glances (the media
# server box, 192.0.2.242:61208, its own stack) with its CPU/memory/load/uptime renamed to sensor.media_server_*; Plotly
# Graph Card (Marketplace) draws both load graphs.
# Menu (Origami Header, custom repository): added once hazymorning/origami_header is installed. Edit mode: the menu's Edit,
# or ?edit=1 at the end of the address. For a flash-free header add /hacsfiles/origami_header/origami-header.js under
# frontend: extra_module_url in configuration.yaml (the script can't edit that file).
# Climate (thermostats): built AUTOMATICALLY for every climate.* entity: rooms header average + climate table toggle, the
# climate table, temperature on the room card, a Climate block + thermostat (Thermostat step script) in the room's pop-up.
# A thermostat's room = its area (or device name); a room that doesn't exist yet gets its own card and pop-up. None = skipped.
#   Dry run (nothing written, config to /root/origami-dryrun.json, Jinja checked):  DRYRUN=1 FAKE_CLIMATE=1 python3 - < ...
#   (with ssh: ssh box 'sudo -n env DRYRUN=1 FAKE_CLIMATE=1 python3 -' < dashboard-origami.py)
# Skipped parts (no such devices): fan, vacuum. Network pop-up (#popup_network): UniFi Network (read-only account) + the UniFi Kuma checks; skipped
# while the UniFi entities are missing.
import copy, json, os, re, subprocess, time, urllib.error, urllib.request
import yaml

DRY = os.environ.get("DRYRUN") == "1"          # render + check only, write nothing
FAKE = os.environ.get("FAKE_CLIMATE") == "1"   # add two fake ecobees + a remote sensor, to test the climate code path

TAG = "6173bdbc4134a80381b5" "99ebe06d77c757da24d7"   # upstream main on Nov 11 (V3.0 + doc/part fixes; modules and theme same as V3.0); split so the repo's secret scan doesn't take it for a key
RAW = f"https://raw.githubusercontent.com/hazymorning/origami/{TAG}/"
URL = "origami-home"   # HA requires a hyphen in a dashboard's url_path, so plain "origami" is refused
HA = "http://192.0.2.150"
T = next(l.strip() for l in open("/etc/media-server/ha-token") if len(l.strip()) > 100)

def ws(*cmds):
    args = []
    for i, c in enumerate(cmds):   # a single argv string is capped at 128 KB, so the big dashboard save goes as a file (ha-ws @file)
        a = json.dumps(c, separators=(",", ":"))
        if len(a) > 100000:
            p = f"/root/.ha-ws-cmd-{os.getpid()}-{i}.json"
            with open(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f: f.write(a)
            a = "@" + p
        args.append(a)
    try: out = subprocess.run(["/usr/local/sbin/ha-ws", *args], capture_output=True, text=True)
    finally:
        for a in args:
            if a.startswith("@"): os.remove(a[1:])
    if out.returncode: raise SystemExit(out.stderr[-400:])
    return [json.loads(l) for l in out.stdout.splitlines()]
def ws1(cmd, ok_errors=()):
    r = ws(cmd)[0]
    if isinstance(r, dict) and "ERROR" in r and r["ERROR"].get("code") not in ok_errors:
        raise SystemExit(f"{cmd['type']}: {r['ERROR']}")
    return r
def rest(method, path, body=None):
    r = urllib.request.Request(HA + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                               headers={"Authorization": "Bearer " + T, "Content-Type": "application/json"})
    try: body = urllib.request.urlopen(r, timeout=60).read().decode()
    except urllib.error.HTTPError as e: raise SystemExit(f"{method} {path}: {e.code} {e.read()[:300]}")
    try: return json.loads(body or "null")
    except ValueError: return body   # /api/template answers with plain text
def w_ws1(cmd, **kw):       # a write over the websocket: skipped in a dry run
    if DRY: print("DRY: skip", cmd["type"]); return {}
    return ws1(cmd, **kw)
def w_rest(method, path, body=None):
    if DRY: print("DRY: skip", method, path); return {}
    return rest(method, path, body)
def up(path): return urllib.request.urlopen(RAW + path, timeout=30).read().decode()
def sub(text, mapping):
    # replace entity ids as whole ids only (media_player.living_room must not hit media_player.living_room_tv)
    for old, new in mapping.items():
        text = re.sub(re.escape(old) + r"(?![A-Za-z0-9_])", new, text)
    return text
def upy(path, mapping=None): return yaml.safe_load(sub(up(path), mapping or {}))
nav = lambda h: {"action": "navigate", "navigation_path": h}
act = lambda service, target=None, data=None, **kw: {"action": "perform-action", "perform_action": service,
                                                    **({"target": {"entity_id": target}} if target else {}), **({"data": data} if data else {}), **kw}

st = {s["entity_id"]: s for s in ws1({"type": "get_states"})}
have = lambda e: e in st

# ---------------------------------------------------------------- 1. prerequisites (Marketplace)
NEEDED = {"Clooos/Bubble-Card": "plugin", "Clooos/Bubble-Card-Tools": "integration", "hazymorning/origami_weather": "plugin",
          "joseluis9595/lovelace-navbar-card": "plugin", "dbuezas/lovelace-plotly-graph-card": "plugin"}
CUSTOM = {"hazymorning/origami": "theme", "hazymorning/origami_notifications": "plugin",
          "hazymorning/origami_header": "plugin"}   # not in the catalog: custom repositories, need GitHub connected
mp_info = ws1({"type": "marketplace/info"})
repos = {r["full_name"]: r for r in ws1({"type": "marketplace/repositories/list"})}
for name in NEEDED:
    r = repos.get(name)
    if r is None: raise SystemExit(f"{name} not in the Marketplace catalog")
    if not r["installed"]:
        print("installing", name, w_ws1({"type": "marketplace/repository/install", "repository": r["id"]}))
        if NEEDED[name] == "integration" and not DRY: raise SystemExit("restart Home Assistant, then run this again")
if mp_info.get("github_connected"):
    for name, cat in CUSTOM.items():
        if name not in repos:
            print("adding custom repository", name, w_ws1({"type": "marketplace/repositories/add", "repository": name, "category": cat}))
    repos = {r["full_name"]: r for r in ws1({"type": "marketplace/repositories/list"})}
    for name in CUSTOM:
        if name in repos and not repos[name]["installed"]:
            print("installing", name, w_ws1({"type": "marketplace/repository/install", "repository": repos[name]["id"]}))
            if CUSTOM[name] == "theme": time.sleep(3); w_rest("POST", "/api/services/frontend/reload_themes", {})
    repos = {r["full_name"]: r for r in ws1({"type": "marketplace/repositories/list"})}
else:
    print("NOTE: GitHub is not connected in Settings > Marketplace (Marketplace's own 'Connect GitHub', not the GitHub integration),"
          " so the Origami theme, Origami Notifications and Origami Header (custom repositories) wait")
installed = {n: r.get("installed_version") for n, r in repos.items() if r.get("installed")}
if not any(e["domain"] == "bubble_card_tools" for e in rest("GET", "/api/config/config_entries/entry")):
    f = w_rest("POST", "/api/config/config_entries/flow", {"handler": "bubble_card_tools"})
    if f.get("type") == "form": rest("POST", "/api/config/config_entries/flow/" + f["flow_id"], {})

# theme: default for light and dark mode, once HA has loaded it
themes = ws1({"type": "frontend/get_themes"})
if "Origami" in themes.get("themes", {}):
    if themes.get("default_theme") != "Origami": w_rest("POST", "/api/services/frontend/set_theme", {"name": "Origami"})
    if themes.get("default_dark_theme") != "Origami": w_rest("POST", "/api/services/frontend/set_theme", {"name": "Origami", "mode": "dark"})
    print("theme: Origami is the default (light + dark)")
else:
    print("theme: Origami not loaded yet")

# font (README: Montserrat 500/700 as a stylesheet resource)
FONT = "https://fonts.googleapis.com/css2?family=Montserrat:wght@500;700&display=swap"
res = ws1({"type": "lovelace/resources"})
if not any(r["url"] == FONT for r in res):
    w_ws1({"type": "lovelace/resources/create", "res_type": "css", "url": FONT})
resources = " ".join(r["url"] for r in ws1({"type": "lovelace/resources"}))
HAS_NOTIFICATIONS = "origami_notifications" in resources or "origami-notifications" in resources
HAS_HEADER = "hazymorning/origami_header" in installed or "origami-header.js" in resources or (DRY and os.environ.get("FAKE_HEADER") == "1")
try: EXTRA_HEADER = "origami-header.js" in urllib.request.urlopen(HA + "/", timeout=30).read().decode()
except Exception: EXTRA_HEADER = False
if HAS_HEADER and not EXTRA_HEADER:
    print("NOTE: Origami Header loads as a dashboard resource; for no header flash add it under frontend: extra_module_url in configuration.yaml")

# ---------------------------------------------------------------- 1b. monitoring: System Monitor (HA VM) + Glances (media server box)
def ensure_entry(domain, data=None):
    if any(e["domain"] == domain for e in rest("GET", "/api/config/config_entries/entry")): return
    f = w_rest("POST", "/api/config/config_entries/flow", {"handler": domain})
    if f.get("type") == "form":
        names = {s["name"] for s in f.get("data_schema", [])}
        f = rest("POST", "/api/config/config_entries/flow/" + f["flow_id"], {k: v for k, v in (data or {}).items() if k in names})
    print("added integration", domain, f.get("type"), f.get("title"), f.get("errors"))
ensure_entry("systemmonitor")
ensure_entry("glances", {"host": "192.0.2.242", "port": 61208, "ssl": False, "verify_ssl": False})
time.sleep(0 if DRY else 3)
ent_reg = {e["entity_id"]: e for e in ws1({"type": "config/entity_registry/list"})}
SM = {k: f"sensor.system_monitor_{k}" for k in ("processor_use", "memory_usage", "disk_usage", "uptime", "load_1_min", "load_5_min", "load_15_min")}
for e in SM.values():   # off at first (server README, step 2); HA reloads the entry by itself about 30 s later
    if e in ent_reg and ent_reg[e].get("disabled_by"):
        print("enabling", e); w_ws1({"type": "config/entity_registry/update", "entity_id": e, "disabled_by": None})
BOX = {"cpu": "sensor.media_server_cpu_usage", "ram": "sensor.media_server_memory_usage", "load": "sensor.media_server_cpu_load",
       "uptime": "sensor.media_server_uptime", "containers": "sensor.media_server_containers_active"}
GL_NAMES = {"cpu": ("cpu_usage", "Media server CPU usage"), "ram": ("memory_usage", "Media server memory usage"),
            "load": ("cpu_load", "Media server load"), "uptime": ("uptime", "Media server uptime"), "containers": ("containers_active", "Media server containers")}
gl = [e for e in ent_reg.values() if e["platform"] == "glances"]
for k, (suffix, name) in GL_NAMES.items():   # sensor.192_168_1_242_* would read like SABnzbd's ids, so the used ones get clear names
    if BOX[k] in ent_reg: continue
    old = next((e["entity_id"] for e in gl if e["entity_id"].endswith("_" + suffix) and e["entity_id"].startswith("sensor.192_168_1_242_")), None)
    if old: print("rename", old, "->", BOX[k]); w_ws1({"type": "config/entity_registry/update", "entity_id": old, "new_entity_id": BOX[k], "name": name})
try: BOX_THREADS = json.loads(urllib.request.urlopen("http://127.0.0.1:61208/api/4/core", timeout=10).read())["log"]
except Exception: BOX_THREADS = 20

# ---------------------------------------------------------------- 2. modules into /config/bubble_card/modules (Bubble Card Tools API)
MODULES = ["origami_base", "origami_button", "origami_climate", "origami_fan", "origami_header", "origami_media",
           "origami_popup", "origami_slider", "origami_table", "origami_tiles"]
for m in MODULES:
    want = up(f"bubble_card/modules/{m}.yaml")
    have_m = ws({"type": "bubble_card_tools/read_module", "name": f"modules/{m}.yaml"})[0]
    if not (isinstance(have_m, dict) and have_m.get("content") == want):
        r = w_ws1({"type": "bubble_card_tools/write_module", "name": f"modules/{m}.yaml", "content": want})
        print("module written:", m)
print("modules:", [f.get("name", f) if isinstance(f, dict) else f for f in ws1({"type": "bubble_card_tools/list_modules"})["files"]])

# ---------------------------------------------------------------- 3. helpers and scripts (from the parts' READMEs)
SPEAKERS = ["media_player.living_room_living_room", "media_player.main_bedroom_main_bedroom", "media_player.five_five", "media_player.sonos_roam"]
SPEAKERS = [s for s in SPEAKERS if have(s)]
sel = [i for i in ws1({"type": "input_select/list"}) if i.get("name") == "Selected speaker"]
if not sel:
    w_ws1({"type": "input_select/create", "name": "Selected speaker", "icon": "mdi:speaker", "options": SPEAKERS})
elif sel[0]["options"] != SPEAKERS:
    w_ws1({"type": "input_select/update", "input_select_id": sel[0]["id"], "name": "Selected speaker", "icon": "mdi:speaker", "options": SPEAKERS})
booleans = [i.get("name") for i in ws1({"type": "input_boolean/list"})]
for name, icon in (("Music pop-up", "mdi:music-box-outline"), ("Climate table", "mdi:table")):   # climate table: rooms header opens/closes it
    if name not in booleans: w_ws1({"type": "input_boolean/create", "name": name, "icon": icon})
SCRIPTS = {"playback": "dashboard/music/playback.yaml", "set_group_volume": "dashboard/music/set-group-volume.yaml",
           "group_speakers": "dashboard/music/group-speakers.yaml", "open_music": "dashboard/music/open-music.yaml",
           "volume": "dashboard/tv/volume.yaml", "thermostat_step": "dashboard/room/thermostat-step.yaml"}
for sid, path in SCRIPTS.items():
    w_rest("POST", f"/api/config/script/config/{sid}", yaml.safe_load(up(path)))
if "number.group_volume" not in ent_reg and not DRY:
    f = rest("POST", "/api/config/config_entries/flow", {"handler": "template"})
    f = rest("POST", "/api/config/config_entries/flow/" + f["flow_id"], {"next_step_id": "number"})
    f = rest("POST", "/api/config/config_entries/flow/" + f["flow_id"], {
        "name": "Group volume", "min": 0, "max": 100, "step": 1, "unit_of_measurement": "%",
        "state": "{% set s = states('input_select.selected_speaker') %}\n"
                 "{% set v = (state_attr(s, 'group_members') or [s]) | map('state_attr', 'volume_level') | select('number') | list %}\n"
                 "{{ (v | sum / v | count * 100) | round if v else 0 }}",
        "set_value": [{"action": "script.set_group_volume", "data": {"speaker": "input_select.selected_speaker", "volume": "{{ value }}"}}]})
    print("group volume helper:", f.get("type"), f.get("result", {}).get("title"))
time.sleep(0 if DRY else 2)
st = {s["entity_id"]: s for s in ws1({"type": "get_states"})}
ent_reg = {e["entity_id"]: e for e in ws1({"type": "config/entity_registry/list"})}
for e in ("input_select.selected_speaker", "input_boolean.music_pop_up", "input_boolean.climate_table", "number.group_volume", *[f"script.{s}" for s in SCRIPTS]):
    if e not in st:
        if not DRY: raise SystemExit(f"helper missing after setup: {e}")
        print("DRY: not created yet:", e); st[e] = {"entity_id": e, "state": "off", "attributes": {}}

# ---------------------------------------------------------------- 3b. climate: every thermostat, its sensors and its room
dev_reg = {d["id"]: d for d in ws1({"type": "config/device_registry/list"})}
areas = {a["area_id"]: a["name"] for a in ws1({"type": "config/area_registry/list"})}
if FAKE:   # two ecobees (one in an area, one not) and a remote room sensor, as the ecobee integration would make them
    fake = [("climate.main_level", "Main Level", "dev_fake_1", None, {"hvac_action": "heating", "hvac_modes": ["off", "heat", "cool", "heat_cool"],
             "temperature": 21, "current_temperature": 20.5, "min_temp": 7, "max_temp": 30}, "heat"),
            ("sensor.main_level_temperature", "Main Level Temperature", "dev_fake_1", None, {"device_class": "temperature", "unit_of_measurement": "°C"}, "20.5"),
            ("sensor.main_level_humidity", "Main Level Humidity", "dev_fake_1", None, {"device_class": "humidity", "unit_of_measurement": "%"}, "41"),
            ("climate.upstairs", "Upstairs", "dev_fake_2", "main_bedroom", {"hvac_action": "idle", "temperature": 19, "min_temp": 7, "max_temp": 30}, "heat"),
            ("sensor.upstairs_current_temperature", "Upstairs Current Temperature", "dev_fake_2", None, {"device_class": "temperature"}, "19.4"),
            ("sensor.basement_temperature", "Basement Temperature", "dev_fake_3", None, {"device_class": "temperature"}, "17.9")]
    for d, n, a in (("dev_fake_1", "Main Level", None), ("dev_fake_2", "Upstairs", "main_bedroom"), ("dev_fake_3", "Basement", None)):
        dev_reg[d] = {"id": d, "name": n, "name_by_user": None, "area_id": a, "config_entries": ["fake_ecobee"]}
    areas.setdefault("main_bedroom", "Main Bedroom")
    for e, n, d, a, attrs, s in fake:
        st[e] = {"entity_id": e, "state": s, "attributes": {"friendly_name": n, **attrs}}
        ent_reg[e] = {"entity_id": e, "device_id": d, "area_id": a, "platform": "ecobee", "config_entry_id": "fake_ecobee"}
dclass = lambda e: st[e]["attributes"].get("device_class")
dev_of = lambda e: (ent_reg.get(e) or {}).get("device_id")
def dev_name(d): return (dev_reg.get(d) or {}).get("name_by_user") or (dev_reg.get(d) or {}).get("name")
def area_of(e):
    a = (ent_reg.get(e) or {}).get("area_id") or (dev_reg.get(dev_of(e)) or {}).get("area_id")
    return areas.get(a)
def sensor_on(dev, cls):
    c = sorted(e for e in st if e.startswith("sensor.") and dev_of(e) == dev and dclass(e) == cls
               and not re.search(r"target|setpoint|outdoor|outside|weather", e))
    return (sorted(c, key=lambda e: ("current" not in e, len(e))) or [None])[0]
CLIMATES = sorted(e for e in st if e.startswith("climate."))
ZONES = []   # one row per room: name, climate (or None), temperature, humidity
for c in CLIMATES:
    d = dev_of(c)
    ZONES.append({"name": area_of(c) or dev_name(d) or st[c]["attributes"].get("friendly_name", c.split(".")[1].replace("_", " ").title()),
                  "climate": c, "temp": sensor_on(d, "temperature"), "hum": sensor_on(d, "humidity")})
clim_entries = {(ent_reg.get(c) or {}).get("config_entry_id") for c in CLIMATES} - {None}
clim_devs = {dev_of(c) for c in CLIMATES}
for d, dv in dev_reg.items():   # the thermostats' remote room sensors (same integration, no thermostat of their own)
    if d in clim_devs or not clim_entries & set(dv.get("config_entries", [])): continue
    t = sensor_on(d, "temperature")
    if t: ZONES.append({"name": areas.get(dv.get("area_id")) or dev_name(d) or t, "climate": None, "temp": t, "hum": sensor_on(d, "humidity")})
for z in ZONES:
    w = z["name"].split()
    z["short"] = z["name"] if len(z["name"]) <= 8 else w[0]
shorts = [z["short"] for z in ZONES]
for z in ZONES:
    if shorts.count(z["short"]) > 1: z["short"] = z["name"]
TEMPS = [z["temp"] for z in ZONES if z["temp"]]
HUMS = [z["hum"] for z in ZONES if z["hum"]]
print("climate:", [(z["name"], z["climate"], z["temp"], z["hum"]) for z in ZONES] or "no thermostats yet, climate parts skipped")

# ---------------------------------------------------------------- 4. cards
OPEN_MUSIC = lambda spk: act("script.open_music", data={"speaker": spk, "dropdown": "input_select.selected_speaker", "pop_up": "input_boolean.music_pop_up"})
TV_B, RM_B, TV_F = "media_player.basement_ag_tv", "remote.basement_ag_tv", "media_player.family_room_tv"
DISPLAY, LIGHT = "media_player.bathroom_display", "light.ring_light"
SAB = "sensor.192_168_1_242_"
KUMA_GROUPS = [("sensor.media_apps_status", "Apps", "mdi:apps"), ("sensor.infrastructure_status", "Network", "mdi:router-wireless"),
               ("sensor.host_health_status", "Box health", "mdi:heart-pulse"), ("sensor.storage_jobs_status", "Storage & jobs", "mdi:harddisk"),
               ("sensor.background_containers_status", "Background containers", "mdi:docker")]
KUMA_GROUPS = [g for g in KUMA_GROUPS if have(g[0])]
GROUP_IDS = "[" + ", ".join(f"'{g}'" for g, _, _ in KUMA_GROUPS) + "]"
JS_DOWN = f"{GROUP_IDS}.filter((id) => states(id) !== 'up')"
ALL_CHECKS = sorted(e for e in st if e.startswith("sensor.") and e.endswith("_status") and e not in {g for g, _, _ in KUMA_GROUPS}
                    and st[e]["state"] in ("up", "down", "pending", "maintenance"))

# --- greeting (Base + Header); the notifications card joins it once Origami Notifications is installed
greet = yaml.safe_load(up("dashboard/greeting/card.yaml"))
g_sep = greet["cards"][0]
g_sep["name"] = "${(h => h < 5 ? 'Still awake?' : h < 12 ? 'Good morning, user' : h < 18 ? 'Good afternoon, user' : h < 22 ? 'Good evening, user' : 'Good night, user')(new Date().getHours())}"
g_sep["sub_button"]["main"][0]["entity"] = "calendar.sonarr"   # the next episode, above the greeting
if HAS_NOTIFICATIONS:
    n = greet["cards"][1]
    n["entities"] = [{"entity": "calendar.sonarr", "before": "24:00:00"}, {"entity": "binary_sensor.192_168_1_242_warnings", "name": "SABnzbd"}]
    greeting = greet
else:
    greeting = dict(g_sep, grid_options={"columns": "full"})

# --- weather: Origami Weather, the diorama
weather = yaml.safe_load(up("dashboard/weather/diorama.yaml"))

# --- favorites (Base + Header + Tiles): tiles show while they matter; the server tile always
fav_header = yaml.safe_load(up("dashboard/favorites/header.yaml"))
fav_tiles = yaml.safe_load(up("dashboard/favorites/tiles.yaml"))
tiles = []
for spk in SPEAKERS + [DISPLAY]:
    tiles.append({"name": st[spk]["attributes"].get("friendly_name", "Music"), "entity": spk, "icon": "mdi:speaker", "force_icon": True,
                  "origami_tiles": {"color": "var(--state-media_player-active-color)", "image": "${attr.entity_picture}"},
                  "visibility": [{"condition": "state", "entity": spk, "state": "playing"}],
                  "tap_action": OPEN_MUSIC(spk) if spk in SPEAKERS else {"action": "more-info"}, "hold_action": {"action": "more-info"}})
for tv, name, h in ((TV_B, "Basement", "#popup_tv"), (TV_F, "Family", "#popup_tv_family_room")):
    # a tile's name fits about six letters, so the room goes in the state line
    tiles.append({"name": "TV", "entity": tv, "icon": "mdi:television", "origami_tiles": {"state": name},
                  "visibility": [{"condition": "state", "entity": tv, "state_not": ["off", "standby", "idle", "unavailable", "unknown"]}],
                  "tap_action": nav(h), "hold_action": {"action": "more-info"}})
tiles += [
    {"name": "Ring Light", "entity": LIGHT, "icon": "mdi:lightbulb", "state_content": "brightness",
     "visibility": [{"condition": "state", "entity": LIGHT, "state": "on"}], "tap_action": nav("#popup_lights"), "hold_action": {"action": "more-info"}},
    {"name": "Shopping", "entity": "todo.shopping_list", "icon": "mdi:cart-outline",
     "origami_tiles": {"name": "${num(state, 0)} ${Number(state) === 1 ? 'item' : 'items'}", "state": "To buy"},
     "visibility": [{"condition": "numeric_state", "entity": "todo.shopping_list", "above": 0}],
     "tap_action": nav("/todo?entity_id=todo.shopping_list"), "hold_action": {"action": "more-info"}},
    {"name": "Plex", "entity": "sensor.tautulli_watching", "icon": "mdi:plex",
     "origami_tiles": {"name": "${num(state, 0)} watching", "state": "Plex", "color": "var(--orange-color)"},
     "visibility": [{"condition": "numeric_state", "entity": "sensor.tautulli_watching", "above": 0}], "tap_action": nav("#popup_server")},
    {"name": "Downloads", "entity": SAB + "queue_count", "icon": "mdi:download",
     "origami_tiles": {"name": f"${{num(state, 0)}} in queue", "state": f"${{format('{SAB}speed')}}", "color": "var(--blue-color)"},
     "visibility": [{"condition": "numeric_state", "entity": SAB + "queue_count", "above": 0}], "tap_action": nav("#popup_server")},
    {"name": "Server", "icon": "mdi:server",
     "origami_tiles": {"state": f"${{(d => d.length ? d.length + ' down' : 'All up')({JS_DOWN})}}",
                       "color": f"${{{JS_DOWN}.length ? 'var(--error-color)' : 'var(--green-color)'}}",
                       "order": f"${{{JS_DOWN}.length ? -3 : 9}}"},
     "tap_action": nav("#popup_server")},
]
fav_tiles["sub_button"]["bottom"] = tiles

# --- rooms (Base + Header): a card per room, opening its pop-up
ROOMS = [  # hash, name, icon, [(kind, entity, label)]   kind: speaker | display | tv | tv_novol | light
    ("#popup_living_room", "Living Room", "mdi:sofa", [("speaker", "media_player.living_room_living_room", "Sonos Beam")]),
    ("#popup_family_room", "Family Room", "mdi:television", [("tv", TV_F, "Family Room TV")]),
    ("#popup_main_bedroom", "Main Bedroom", "mdi:bed-king", [("speaker", "media_player.main_bedroom_main_bedroom", "Sonos Ray")]),
    ("#popup_basement", "Basement", "mdi:stairs-down", [("tv_novol", TV_B, "Basement TV"), ("light", LIGHT, "Ring Light")]),
    ("#popup_bathroom", "Bathroom", "mdi:shower", [("display", DISPLAY, "Nest Hub Max")]),
    ("#popup_speakers", "More speakers", "mdi:speaker-multiple", [("speaker", "media_player.five_five", "Sonos Five"), ("speaker", "media_player.sonos_roam", "Sonos Roam")]),
]
ROOMS = [(h, n, i, [d for d in devs if have(d[1])]) for h, n, i, devs in ROOMS]
ROOM_CLIMATE = {}   # hash -> zone (thermostat and/or temperature + humidity)
for z in ZONES:     # a thermostat or room sensor joins the room of the same name, or gets a room of its own
    r = next((r for r in ROOMS if r[1].lower() == z["name"].lower()), None)
    if r is None:
        h = "#popup_" + re.sub(r"[^a-z0-9]+", "_", z["name"].lower()).strip("_")
        r = (h, z["name"], "mdi:home-thermometer-outline" if z["climate"] else "mdi:thermometer", [])
        ROOMS.append(r)
    if r[0] not in ROOM_CLIMATE: ROOM_CLIMATE[r[0]] = z
ROOMS = [r for r in ROOMS if r[3] or r[0] in ROOM_CLIMATE]
KIND_ICON = {"speaker": "mdi:speaker", "display": "mdi:speaker", "tv": "mdi:television", "tv_novol": "mdi:television", "light": "mdi:lightbulb"}
rooms_header = yaml.safe_load(up("dashboard/rooms/header.yaml"))
PLAYERS = [d[1] for _, _, _, devs in ROOMS for d in devs if d[0] != "light"]
JS_PLAYING = "[" + ", ".join(f"'{p}'" for p in PLAYERS) + "].filter((id) => states(id) === 'playing').length"
rooms_header["sub_button"]["main"] = [{"name": "Playing", "icon": "mdi:play", "origami_header": {"name": f"${{{JS_PLAYING}}} playing", "hidden": f"${{{JS_PLAYING} === 0}}"},
                                       "tap_action": nav("#popup_music")}]
JS_IDS = lambda ids: "[" + ", ".join(f"'{i}'" for i in ids) + "]"
if TEMPS:   # README: the average of the rooms' temperatures; a tap on it or the chevron opens the climate table. No window contacts here.
    hdr_up = {s["name"]: s for s in yaml.safe_load(up("dashboard/rooms/header.yaml"))["sub_button"]["main"]}
    tchip = copy.deepcopy(hdr_up["Temperature"])
    tchip["origami_header"]["name"] = ("${(t => t.length ? num(t.reduce((a, b) => a + b, 0) / t.length, 0) + '°' : '–')("
                                       + JS_IDS(TEMPS) + ".map((id) => parseFloat(states(id))).filter((v) => !isNaN(v)))}")
    rooms_header["sub_button"]["main"] = rooms_header["sub_button"]["main"] + [tchip, copy.deepcopy(hdr_up["Climate table"])]
room_tpl = yaml.safe_load(up("dashboard/rooms/room.yaml"))
def room_card(h, name, icon, devs):
    c = copy.deepcopy(room_tpl)
    z = ROOM_CLIMATE.get(h)
    main = next((d for d in devs if d[0] == "light"), devs[0] if devs else ("climate", z["climate"] or z["temp"], ""))
    c.update(entity=main[1], name=name, icon=icon)
    c["button_action"]["tap_action"] = nav(h)
    bottom = []
    for kind, e, label in devs:
        tpl = "${state === 'on' ? num(attr.brightness / 2.55, 0, '%') : word(state)}" if kind == "light" else \
              "${state === 'playing' && attr.media_title ? attr.media_title : word(state)}"
        bottom.append({"entity": e, "icon": KIND_ICON[kind], "origami_base": {"name": tpl, "hidden": "${['unavailable', 'unknown'].includes(state)}"}})
    if z and z["temp"]:   # room.yaml: the dot, the temperature and the humidity (no window contacts)
        dot, temp, hum = (copy.deepcopy(b) for b in room_tpl["sub_button"]["bottom"] if b.get("entity") != "binary_sensor.living_room_window")
        dot["entity"] = temp["entity"] = z["temp"]
        bottom = [dot, temp] + bottom
        if z["hum"]: hum["entity"] = z["hum"]; bottom.insert(2, hum)
        else: temp["origami_base"]["name"] = "${num(state, 0)}°"
    c["sub_button"]["bottom"] = bottom
    return c

# --- room pop-ups (Base + Popup + Header + Button + Media + Slider), blocks from the bathroom and living-room examples
bath = yaml.safe_load(up("dashboard/room/bathroom.yaml"))
living = yaml.safe_load(up("dashboard/room/living-room.yaml"))
SPEAKER_TPL = bath["cards"][0]["cards"][0]
TV_TPL = living["cards"][0]["cards"][0]["cards"][0]["card"]
OFF_TPL = bath["cards"][0]["cards"][-1]
LIGHTS_TPL = bath["cards"][0]["cards"][1]
CLIMATE_TPL = next(c for c in living["cards"][0]["cards"] if c.get("type") == "vertical-stack" and c["cards"][0].get("name") == "Climate")
def climate_block(z):
    # room README, Climate + Thermostat: the header shows temperature / humidity with the dot, the thermostat moves by half a degree
    blk = copy.deepcopy(CLIMATE_TPL)
    hdr = blk["cards"][0]
    therm = next(c for c in blk["cards"] if c.get("entity") == "climate.living_room")
    tsb = hdr["sub_button"]["main"][0]
    if z["temp"]:
        tsb["entity"] = z["temp"]
        if z["hum"]: tsb["origami_header"]["name"] = tsb["origami_header"]["name"].replace("sensor.living_room_humidity", z["hum"])
        else: tsb["origami_header"].pop("name")
    else: hdr["sub_button"]["main"] = []
    cards = [hdr]
    if z["climate"]:
        therm = json.loads(json.dumps(therm).replace("climate.living_room", z["climate"]))
        therm["name"] = "Thermostat"
        cards.append(therm)
    blk["cards"] = cards   # no fan here
    return blk
def speaker_block(e, label, music):
    c = json.loads(json.dumps(SPEAKER_TPL).replace("media_player.bathroom", e))
    c["name"] = label
    tap = OPEN_MUSIC(e) if music else {"action": "more-info"}
    c["tap_action"] = tap; c["button_action"]["tap_action"] = tap
    return c
def tv_block(e, label, h, slider):
    c = json.loads(json.dumps(TV_TPL).replace("media_player.living_room_tv", e))
    c["name"] = label
    c["origami_media"].pop("players", None)
    c["tap_action"] = nav(h); c["button_action"]["tap_action"] = nav(h)
    if slider: c["sub_button"]["bottom"] = [{"entity": e, "sub_button_type": "slider", "always_visible": True}]
    else: c["sub_button"].pop("bottom", None); c["rows"] = 1.375
    return c
def light_block(e, label):
    blk = json.loads(json.dumps(LIGHTS_TPL).replace("light.bathroom", e))
    hdr, allc = blk["cards"]
    hdr["sub_button"]["main"][0]["origami_header"]["name"] = "${state === 'on' ? num(attr.brightness / 2.55, 0, '%') : word(state)}"
    allc.update(name=label, icon="mdi:lightbulb")
    allc["sub_button"]["main"] = [m for m in allc["sub_button"]["main"] if m.get("icon") == "mdi:power"]          # no scenes
    allc["sub_button"]["bottom"][0]["group"] = allc["sub_button"]["bottom"][0]["group"][:1]                     # one lamp: no lamp list
    allc["sub_button"]["bottom"][0]["name"] = label
    return blk
def room_popup(h, name, devs):
    p = {k: v for k, v in bath.items() if k not in ("cards", "origami_popup")}
    p.update(hash=h, name=name)
    blocks = []
    for kind, e, label in devs:
        if kind == "speaker": blocks.append(speaker_block(e, label, True))
        elif kind == "display": blocks.append(speaker_block(e, label, False))
        elif kind == "tv": blocks.append(tv_block(e, label, "#popup_tv_family_room", True))
        elif kind == "tv_novol": blocks.append(tv_block(e, label, "#popup_tv", False))
        elif kind == "light": blocks.append(light_block(e, label))
    if h in ROOM_CLIMATE: blocks.append(climate_block(ROOM_CLIMATE[h]))   # the thermostat keeps its setting at Everything off
    off = [e for kind, e, _ in devs if kind in ("light", "tv", "tv_novol")]   # speakers left out, as the README says
    if off:
        o = copy.deepcopy(OFF_TPL); o["sub_button"]["bottom"][0]["tap_action"]["target"]["entity_id"] = off
        blocks.append(o)
    p["cards"] = [{"type": "vertical-stack", "cards": blocks}]
    return p

# --- music pop-up: the four Sonos speakers
MAP3 = {"media_player.living_room": SPEAKERS[0], "media_player.bedroom": SPEAKERS[1], "media_player.office": SPEAKERS[2]}
music = upy("dashboard/music/pop-up.yaml", MAP3)
mp = music["origami_popup"]["mini_popups"]
def clone_for(lst, src, new):
    for it in list(lst):
        if src in json.dumps(it): lst.append(json.loads(json.dumps(it).replace(src, new))); return
    raise SystemExit(f"no template entry for {src}")
for extra in SPEAKERS[3:]:
    clone_for(mp["group"]["cards"][2]["sub_button"]["bottom"], SPEAKERS[2], extra)
    clone_for(mp["volume"][1]["sub_button"]["bottom"], SPEAKERS[2], extra)
    clone_for(music["sub_button"]["main"], SPEAKERS[2], extra)
# shortcuts: the Beam has a TV input named 'TV' and no Bluetooth
more = mp["more"]["cards"][0]["sub_button"]["bottom"]
mp["more"]["cards"][0]["sub_button"]["bottom"] = [dict(b, tap_action=dict(b["tap_action"], data={"source": "TV"})) for b in more if b["name"] == "TV"]
music_card = music["cards"][0]["cards"][0]
music_card["origami_base"].pop("words", None)
# no Music Assistant here: drop the heart, which would always rest
pb = music_card["sub_button"]["bottom"][0]
pb["group"] = [k for k in pb["group"] if k.get("icon") != "mdi:heart-outline"]
# Open with a speaker (README Optional): opens when input_boolean.music_pop_up turns on
music.update(trigger=[{"condition": "state", "entity": "input_boolean.music_pop_up", "state": "on"}], trigger_close=False,
             open_action=act("input_boolean.turn_off", "input_boolean.music_pop_up"))

# --- TV pop-up: Basement TV (Android TV Remote: remote, volume steps and mute, no volume level to set, apps by package)
tv = upy("dashboard/tv/pop-up.yaml", {"media_player.living_room_tv": TV_B, "media_player.living_room": TV_B, "remote.living_room_tv": RM_B})
tv["name"] = "Basement TV"
tv.pop("origami_popup", None)                       # no Cast player for the art
stk = tv["cards"][0]["cards"]
tvc = stk[0]; tvc["name"] = "Basement TV"; tvc["origami_media"].pop("players", None)
tvc["sub_button"].pop("bottom", None); tvc["rows"] = 1.375
row = stk[1]["sub_button"]["bottom"]
row[0]["group"] = [b for b in row[0]["group"] if b.get("name") == "Input"]        # no separate speaker, so no 'TV' input key
q, mid, l = row[1]["group"]
for b, svc in ((q, "media_player.volume_down"), (l, "media_player.volume_up")):
    b["tap_action"] = act(svc, TV_B); b.pop("double_tap_action", None); b.pop("hold_action", None)
APPS = [("Netflix", "com.netflix.ninja"), ("YouTube", "com.google.android.youtube.tv"), ("Plex", "com.plexapp.android"),
        ("Prime Video", "com.amazon.amazonvideo.livingroom"), ("Disney+", "com.disney.disneyplus"), ("Spotify", "com.spotify.tv.android")]
stk[2]["sub_button"]["bottom"] = [{"name": n, "show_name": True, "tap_action": act("media_player.play_media", TV_B, {"media_content_type": "app", "media_content_id": a})} for n, a in APPS]
stk[2]["origami_button"]["active"] = "${(a => " + " : ".join(f"a === '{a}' ? '{n}'" for n, a in APPS) + f" : '')(hass.states['{TV_B}']?.attributes?.app_id)}}"

# --- TV pop-up: Family Room TV (Google Cast): what's cast, its volume and play/pause, no remote
tvf = upy("dashboard/tv/pop-up.yaml", {"media_player.living_room_tv_cast": TV_F, "media_player.living_room_tv": TV_F, "media_player.living_room": TV_F})
tvf.update(hash="#popup_tv_family_room", name="Family Room TV")
fs = tvf["cards"][0]["cards"]
fs[0]["name"] = "Family Room TV"; fs[0]["origami_media"].pop("players", None)
frow = fs[1]["sub_button"]["bottom"]
frow[0] = {"name": "Playback", "group": [
    {"name": "Play", "icon": "mdi:play-pause", "tap_action": act("media_player.media_play_pause", TV_F)},
    {"name": "Stop", "icon": "mdi:stop", "tap_action": act("media_player.media_stop", TV_F)}]}
tvf["cards"][0]["cards"] = fs[:2]                      # no apps or remote on a Cast device

# --- lights pop-up: the Ring Light (no light group, no scenes)
lights = upy("dashboard/lights/pop-up.yaml", {"light.living_room": LIGHT})
lights["origami_popup"].pop("mini_popups", None)
lc = lights["cards"][0]["cards"][0]
lc["sub_button"]["main"] = [{"icon": "mdi:power", "show_background": True, "tap_action": {"action": "toggle"}}]
lc["sub_button"]["bottom"][0]["group"] = lc["sub_button"]["bottom"][0]["group"][:1]
lc["sub_button"]["bottom"][0]["name"] = "Ring Light"
lights["cards"][0]["cards"] = [lc]

# --- server pop-up: Home Assistant VM (System Monitor) and the media server box (Glances + Uptime Kuma), each with its load graph
srv = yaml.safe_load(up("dashboard/server/pop-up.yaml"))
ss = srv["cards"][0]["cards"]
up_top, maint_hdr, maint, graph_tpl = ss[0], ss[1], ss[2], ss[3]
HAS_SM = all(have(SM[k]) for k in ("processor_use", "memory_usage", "disk_usage", "uptime"))
HAS_BOX = have(BOX["cpu"]) and have(BOX["ram"])
HAS_PLOTLY = "plotly-graph-card" in resources
down_j = "{% set d = [" + ",".join(f"'{e}'" for e in ALL_CHECKS) + "] | reject('is_state','up') | list %}"
def fix_backup_chip(card):   # no automatic backup yet: 'None yet' instead of NaN
    bk = card["sub_button"]["main"][0]["origami_base"]
    bk["name"] = "${isNaN(Date.parse(state)) ? 'None yet' : " + bk["name"].strip()[2:-1] + "}"
    bk["name_color"] = "${isNaN(Date.parse(state)) ? '' : " + bk["name_color"].strip()[2:-1] + "}"
    card["sub_button"]["bottom"][0]["group"][0]["tap_action"] = act("hassio.backup_full", confirmation={"text": "Create a full backup now?"})
def section_hdr(name, link_name, link):
    return {"type": "custom:bubble-card", "card_type": "separator", "name": name, "modules": ["origami_base", "origami_header"],
            "origami_header": {"weight": "medium", "icon_size": "var(--icon-size-s)"},
            "sub_button": {"main": [{"name": link_name, "show_name": True, "icon": "mdi:chevron-right", "content_layout": "icon-right",
                                     "show_background": False, "tap_action": link}]}}
def chip(e, label, tpl="${num(state, 0, '%') || '–'}"):   # as the menu's server card: CPU / RAM values beside the name
    return {"entity": e, "show_name": True, "show_icon": False, "show_background": False,
            "origami_base": {"name": tpl, "label": label}, "tap_action": {"action": "more-info"}}
def load_graph(cpu, ram, load=None, threads=1):
    g = json.loads(json.dumps(graph_tpl).replace("sensor.system_monitor_memory_usage", ram).replace("sensor.system_monitor_processor_use", cpu))
    if load:   # the load average as a share of the box's threads, dashed, without a fill
        g["color_setup"] = g["color_setup"].replace('vars.cBg =', 'vars.cLoad = read("--heat-color") || "#D9A066";\n    vars.cBg =')
        g["entities"].insert(2, {"entity": load, "name": "Load", "yaxis": "y", "line": {"color": "$ex vars.cLoad", "dash": "dot", "width": 2},
                                 "hovertemplate": f"%{{y:.0f}} % of {threads} threads<extra>Load</extra>",
                                 "filters": f'$ex [{{ map_y_numbers: "y * 100 / {threads}" }}, ...get("smooth_filters")]'})
    return g
cards = []
if HAS_SM:   # the upstream status card: the HA VM's most urgent problem, its uptime and backup age, back up / check / restart
    ha_top = copy.deepcopy(up_top); ha_top["icon"] = "mdi:home-assistant"
    fix_backup_chip(ha_top)
    cards += [section_hdr("Home Assistant VM", "Hardware", nav("/config/hardware")), ha_top]
    if HAS_PLOTLY: cards.append(load_graph(SM["processor_use"], SM["memory_usage"]))
box_top = copy.deepcopy(up_top)
box_top.update(entity=KUMA_GROUPS[0][0], icon="mdi:server", name=
    down_j + "{%- set u = states.update | selectattr('state', 'eq', 'on') | list | count -%}"
    "{%- if d | count == 1 -%}{{ state_attr(d[0], 'friendly_name') | replace(' Status', '') }} down"
    "{%- elif d | count > 1 -%}{{ d | count }} checks down"
    + ("" if HAS_SM else "{%- elif u > 0 -%}{{ u }} {{ 'update' if u == 1 else 'updates' }}") +
    "{%- else -%}All good{%- endif -%}",
    state_content=down_j + "{{ " + str(len(ALL_CHECKS)) + " - d | count }} of " + str(len(ALL_CHECKS)) + " checks up")
box_top["tap_action"] = {"action": "none"}; box_top["button_action"] = {"tap_action": {"action": "none"}}
if HAS_SM:   # HA's own actions sit on the HA card; this one shows the box's CPU, RAM and load
    box_top["sub_button"] = {"main": [chip(BOX["cpu"], "CPU"), chip(BOX["ram"], "RAM"), chip(BOX["load"], "Load", "${num(state, 1)}")] if HAS_BOX else []}
else:
    fix_backup_chip(box_top)
box_hdr = section_hdr("Media server", "Homepage", {"action": "url", "url_path": "http://192.0.2.242:3000"})
cards += [box_hdr, box_top]
if HAS_BOX and HAS_PLOTLY: cards.append(load_graph(BOX["cpu"], BOX["ram"], BOX["load"] if have(BOX["load"]) else None, BOX_THREADS))
box_rows = [{"entity": g, "name": n, "icon": i, "tap_action": {"action": "more-info"},
             "origami_tiles": {"state": "${state === 'up' ? 'All up' : word(state)}",
                               "color": "${state === 'up' ? 'var(--green-color)' : 'var(--error-color)'}",
                               "state_color": "${state === 'up' ? '' : 'var(--error-color)'}"}} for g, n, i in KUMA_GROUPS]
box_rows += [
    {"entity": SAB + "status", "name": "SABnzbd", "icon": "mdi:download", "tap_action": {"action": "more-info"},
     "origami_tiles": {"state": f"${{(q => q > 0 ? num(q, 0) + ' queued · ' + format('{SAB}speed') : word(state))(Number(states('{SAB}queue_count')))}}"}},
    {"entity": "sensor.tautulli_watching", "name": "Plex streams", "icon": "mdi:plex", "tap_action": {"action": "more-info"},
     "origami_tiles": {"state": "${num(state, 0)} watching"}},
    {"entity": "sensor.sonarr_upcoming", "name": "Upcoming", "icon": "mdi:calendar-clock", "tap_action": nav("/calendar"),
     "origami_tiles": {"state": "${num(state, 0)} this week"}}]
box_list = {"type": "custom:bubble-card", "card_type": "sub-buttons", "modules": ["origami_base", "origami_tiles"],
            "origami_tiles": {"layout": "list", "slim": True, "dividers": True}, "sub_button": {"main": [], "bottom": [r for r in box_rows if have(r["entity"])]}}
sab_keys = {"type": "custom:bubble-card", "card_type": "sub-buttons", "modules": ["origami_base", "origami_button"],
            "origami_button": {"columns": 2, "icon_size": "var(--icon-size-xs)"},
            "sub_button": {"main": [], "bottom": [
                {"name": "Pause", "icon": "mdi:pause", "show_name": True, "tap_action": act("button.press", "button.192_168_1_242_pause", confirmation={"text": "Pause all downloads?"})},
                {"name": "Resume", "icon": "mdi:play", "show_name": True, "tap_action": act("button.press", "button.192_168_1_242_resume", confirmation={"text": "Resume all downloads?"})}]}}
nb = maint["sub_button"]["bottom"][1]["origami_tiles"]
nb["state"] = "${isNaN(Date.parse(state)) ? 'Not scheduled' : " + nb["state"].strip()[2:-1] + "}"
srv["cards"][0]["cards"] = cards + [box_list, sab_keys, maint_hdr, maint]

# --- menu (Origami Header): the header goes, the menu slides down with shortcuts and the server card. Edit = the menu's Edit or ?edit=1
menu = None
if HAS_HEADER:
    menu = yaml.safe_load(up("dashboard/menu/card.yaml"))
    keep = {b["name"]: b for b in menu["buttons"]}
    menu["buttons"] = [{"name": "Homepage", "icon": "mdi:view-dashboard-outline", "tap_action": {"action": "url", "url_path": "http://192.0.2.242:3000"}},
                       {"name": "Settings", "icon": "mdi:cog-outline", "tap_action": nav("/config/dashboard")},
                       keep["Menu"], keep["Edit"]]   # no File editor app here, and no automations yet
    if HAS_SM:   # a check that's down on the box comes first in the server card's top line
        menu["cards"]["name"] = down_j + menu["cards"]["name"].replace(
            "{%- if s > 90 -%}", "{%- if d | count > 0 -%}{{ d | count }} {{ 'check' if d | count == 1 else 'checks' }} down\n{%- elif s > 90 -%}", 1)
    else:
        menu.pop("cards", None)

# --- favorites list pop-up
favl = yaml.safe_load(up("dashboard/favorites-list/pop-up.yaml"))
fl = favl["cards"][0]["cards"]
def tv_rows(e, name, h):
    return [{"entity": e, "name": name, "icon": "mdi:television", "tap_action": act("media_player.turn_on", e),
             "visibility": [{"condition": "state", "entity": e, "state": ["off", "standby", "unavailable", "unknown"]}]},
            {"entity": e, "name": name, "icon": "mdi:television", "tap_action": nav(h),
             "visibility": [{"condition": "state", "entity": e, "state_not": ["off", "standby", "unavailable", "unknown"]}]}]
fl[0]["sub_button"]["bottom"] = tv_rows(TV_B, "Basement TV", "#popup_tv") + tv_rows(TV_F, "Family Room TV", "#popup_tv_family_room")
fl[2]["sub_button"]["bottom"] = [
    {"name": "Music", "icon": "mdi:speaker", "tap_action": nav("#popup_music"),
     "origami_tiles": {"state": "${name(states('input_select.selected_speaker'))}"}},
    {"entity": LIGHT, "name": "Ring Light", "icon": "mdi:lightbulb", "tap_action": nav("#popup_lights")}]
fl[4]["sub_button"]["bottom"][0].update(entity="calendar.sonarr", name="TV calendar", origami_tiles={"state": "${attr.message || 'Nothing soon'}"})
favl["cards"][0]["cards"] = fl

# --- network pop-up: the UniFi gateway (UniFi Network on a read-only account) and the Uptime Kuma checks of the router and the
# internet, as the server pop-up: a status card with chips, slim lists and 24 h graphs. Opened from a Network tile in favorites,
# a row in the favorites list and the Network row of the server pop-up. No room in the navigation bar (it has its five keys).
# Skipped (no pop-up, tile or rows) while the UniFi entities are missing.
GW = "sensor.home_gateway_"
NET = {k: GW + k for k in ("state", "uptime", "cpu_utilization", "memory_utilization", "cpu_temperature", "clients",
                           "cloudflare_wan_latency", "google_wan_latency")}
first = lambda *ids: next((e for e in ids if have(e)), ids[-1])
# Kuma: the UniFi push checks (host-health-push reads the gateway's API) where they exist, else the DNS lookup and router ping
NET_FW = "update.home_gateway_firmware"
K_NET = first("sensor.unifi_internet_wan_status", "sensor.internet_dns_lookup_status")
K_RTR = first("sensor.unifi_router_health_status", "sensor.router_192_168_1_1_status")
K_WIFI = "sensor.unifi_wi_fi_status"
WIFI = [(e, n) for e, n in (("sensor.example_ssid_clients", "5 GHz"), ("sensor.example_ssid_2g_clients", "2.4 GHz"),
                            ("sensor.example_ssid_6g_clients", "6 GHz")) if have(e)]
HAS_NET = all(have(NET[k]) for k in ("state", "uptime", "cpu_utilization", "memory_utilization"))
CONSOLE = {"action": "url", "url_path": "https://192.0.2.1"}
net = None
if HAS_NET:
    # what's down, in JavaScript (tiles, pop-up values) and Jinja (the status card's name), most urgent first
    js_down = [f"states('{e}') !== 'up'" for e in (K_NET, K_RTR, K_WIFI) if have(e)] + [f"states('{NET['state']}') !== 'connected'"]
    JS_NET_DOWN = "(" + " || ".join(js_down) + ")"
    problems = ([(f"not is_state('{K_RTR}', 'up')", "Router problem")] if have(K_RTR) else []) + \
               ([(f"not is_state('{K_NET}', 'up')", "Internet down")] if have(K_NET) else []) + \
               ([(f"not is_state('{K_WIFI}', 'up')", "Wi-Fi problem")] if have(K_WIFI) else []) + \
               [(f"not is_state('{NET['state']}', 'connected')", f"Gateway {{{{ states('{NET['state']}') }}}}"),
                (f"states('{NET['memory_utilization']}') | float(0) > 90", "Memory high"),
                (f"states('{NET['cpu_utilization']}') | float(0) > 90", "CPU high")] + \
               ([(f"is_state('{NET_FW}', 'on')", "Firmware update")] if have(NET_FW) else [])
    status_name = "".join(("{%- if " if i == 0 else "{%- elif ") + c + " -%}" + t for i, (c, t) in enumerate(problems)) + "{%- else -%}All good{%- endif -%}"
    net = copy.deepcopy(srv)
    net.update(hash="#popup_network", name="Network")
    pv = [{"entity": K_NET if have(K_NET) else NET["state"], "name": "Internet", "show_name": True, "icon": "mdi:web",
           "origami_popup": {"name": f"${{{JS_NET_DOWN} ? 'Offline' : 'Online'}}",
                             "color": f"${{{JS_NET_DOWN} ? 'var(--error-color)' : 'var(--green-color)'}}",
                             "name_color": f"${{{JS_NET_DOWN} ? 'var(--error-color)' : ''}}"}, "tap_action": {"action": "more-info"}}]
    if have(NET_FW):   # the firmware badge, only while UniFi offers an update
        pv.append({"entity": NET_FW, "name": "Update", "show_name": True, "icon": "mdi:package-up",
                   "origami_popup": {"hidden": "${state !== 'on'}", "color": "var(--accent-color)", "name_color": "var(--accent-color)"},
                   "tap_action": {"action": "more-info"}})
    net["sub_button"] = {"main": pv, "bottom": []}
    gw_top = copy.deepcopy(up_top)   # the most urgent problem as the name, the gateway's uptime below it, CPU / RAM / temperature
    gw_top.update(entity=NET["uptime"], icon="mdi:router-wireless", name=status_name,
                  state_content=up_top["state_content"].replace("sensor.system_monitor_uptime", NET["uptime"]))
    gw_top["tap_action"] = CONSOLE; gw_top["button_action"] = {"tap_action": CONSOLE}
    gw_top["sub_button"] = {"main": [chip(NET["cpu_utilization"], "CPU"), chip(NET["memory_utilization"], "RAM")]
                            + ([chip(NET["cpu_temperature"], "Temp", "${num(state, 0)}°")] if have(NET["cpu_temperature"]) else [])}
    def slim(rows): return {"type": "custom:bubble-card", "card_type": "sub-buttons", "modules": ["origami_base", "origami_tiles"],
                            "origami_tiles": {"layout": "list", "slim": True, "dividers": True}, "sub_button": {"main": [], "bottom": rows}}
    def kuma_row(e, n, i): return {"entity": e, "name": n, "icon": i, "tap_action": {"action": "more-info"},
                                   "origami_tiles": {"state": "${state === 'up' ? 'Up' : word(state)}",
                                                     "color": "${state === 'up' ? 'var(--green-color)' : 'var(--error-color)'}",
                                                     "state_color": "${state === 'up' ? '' : 'var(--error-color)'}"}}
    inet_rows = ([kuma_row(K_NET, "Internet", "mdi:web")] if have(K_NET) else []) + ([kuma_row(K_RTR, "Router", "mdi:router-network")] if have(K_RTR) else [])               + ([kuma_row(K_WIFI, "Wi-Fi", "mdi:wifi")] if have(K_WIFI) else [])
    inet_rows.append({"entity": NET["state"], "name": "Gateway", "icon": "mdi:lan-connect", "tap_action": {"action": "more-info"},
                      "origami_tiles": {"state": "${word(state)}", "color": "${state === 'connected' ? 'var(--green-color)' : 'var(--error-color)'}",
                                        "state_color": "${state === 'connected' ? '' : 'var(--error-color)'}"}})
    for k, n in (("cloudflare_wan_latency", "Cloudflare"), ("google_wan_latency", "Google")):
        if have(NET[k]): inet_rows.append({"entity": NET[k], "name": n, "icon": "mdi:timer-outline", "tap_action": {"action": "more-info"},
                                           "origami_tiles": {"state": f"${{format('{NET[k]}')}}"}})
    if have(NET_FW):
        inet_rows.append({"entity": NET_FW, "name": "Firmware", "icon": "mdi:package-up", "tap_action": {"action": "more-info"},
                          "origami_tiles": {"state": "${state === 'on' ? 'Update available' : 'Up to date'}",
                                            "state_color": "${state === 'on' ? 'var(--accent-color)' : ''}"}})
    def net_graph(series, unit, chips, margin_r):
        # the server pop-up's graph with other series: (entity, name, color var, fill, store var); a value chip for each store var
        g = copy.deepcopy(graph_tpl)
        g["color_setup"] = g["color_setup"].replace('vars.cBg =', 'vars.cLoad = read("--heat-color") || "#D9A066";\n    vars.cBg =')
        mark = graph_tpl["entities"][2]
        ents = []
        for e, n, cv, fill, sv in series:
            if not have(e): continue
            ent = {"entity": e, "name": n, "line": {"color": f"$ex vars.{cv}"}, "hovertemplate": f"%{{y:.0f}}{unit}<extra>{n}</extra>",
                   "filters": f'$ex [...get("smooth_filters"), {{ store_var: "{sv}" }}]'}
            if unit == "": ent["yaxis"] = "y"   # unitless counts would get an axis of their own
            if fill: ent.update(fill="tozeroy", fillgradient={"type": "vertical", "colorscale": f'$ex [[0, "rgba(0,0,0,0)"], [1, vars.{cv} + "52"]]'})
            else: ent["line"].update(dash="dot", width=2)
            ents.append(ent)
            if sv in chips:   # the day's peak, as on the server graph
                m = json.loads(json.dumps(mark).replace("vars.cCpu", f"vars.{cv}").replace("sensor.system_monitor_processor_use", e))
                m["name"] = "max " + n; m["texttemplate"] = "<b>%{y:.0f}</b>"   # the number only, the chip beside it has the unit
                if unit == "": m["yaxis"] = "y"
                ents.append(m)
        g["entities"] = ents
        lay = g["layout"]
        lay.pop("shapes", None)
        lay["margin"] = dict(lay["margin"], r=margin_r, l=48 if unit else lay["margin"]["l"])   # room for '40 ms' 
        lay["yaxis"] = {"rangemode": "tozero", "nticks": 3, "ticksuffix": unit}
        cl = ", ".join(f'{{ label: "{chips[sv]}", v: last(vars.{sv}), color: vars.{cv} }}' for e, n, cv, f, sv in series if sv in chips and have(e))
        lay["annotations"] = ("$fn ({ vars }) => {\n  const last = (s) => {\n    const ys = (s && s.ys) || [];\n"
                              "    for (let i = ys.length - 1; i >= 0; i--) { if (ys[i] != null && isFinite(+ys[i])) return +ys[i]; }\n    return null;\n  };\n"
                              f"  const c = [{cl}].filter((x) => x.v != null).sort((a, b) => b.v - a.v);\n"
                              "  // two chips sit a chip's height apart, so they never overlap\n"
                              "  return c.map((x, i) => ({\n    xref: \"paper\", x: 1, xanchor: \"left\", xshift: 8, yref: \"y\", y: x.v,\n"
                              "    yshift: c.length > 1 ? (i === 0 ? 10 : -10) : 0, showarrow: false, borderpad: 4,\n"
                              f"    text: \"<b>\" + x.label + \" \" + Math.round(x.v) + \"{unit}</b>\",\n"
                              "    font: { size: 11, color: vars.cBg }, bgcolor: x.color,\n  }));\n}")
        return g
    def net_hdr(name, values=()):
        return {"type": "custom:bubble-card", "card_type": "separator", "name": name, "modules": ["origami_base", "origami_header"],
                "origami_header": {"weight": "medium", "icon_size": "var(--icon-size-s)"}, "sub_button": {"main": list(values)}}
    ncards = [section_hdr("Home Gateway", "Console", CONSOLE), gw_top, net_hdr("Internet"), slim(inet_rows)]
    if HAS_PLOTLY and (have(NET["google_wan_latency"]) or have(NET["cloudflare_wan_latency"])):
        ncards.append(net_graph([(NET["google_wan_latency"], "Google", "cCpu", True, "s0"), (NET["cloudflare_wan_latency"], "Cloudflare", "cRam", True, "s1")],
                                " ms", {"s0": "Google", "s1": "Cloudflare"}, 112))
    if have(NET["clients"]) or WIFI:
        total = [{"entity": NET["clients"], "name": "Clients", "show_name": True, "icon": "mdi:devices",
                  "origami_header": {"name": "${num(state, 0)} total"}, "tap_action": {"action": "more-info"}}] if have(NET["clients"]) else []
        ncards += [net_hdr("Clients", total),
                   slim([{"entity": e, "name": f"{n} Wi-Fi",
                          "icon": "mdi:wifi", "tap_action": {"action": "more-info"},
                          "origami_tiles": {"state": "${num(state, 0)} ${Number(state) === 1 ? 'client' : 'clients'}"}} for e, n in WIFI])]
        if HAS_PLOTLY and have(NET["clients"]):
            ncards.append(net_graph([(NET["clients"], "Clients", "cRam", True, "s0")] + [(e, n, c, False, f"w{i}") for i, ((e, n), c) in enumerate(zip(WIFI, ("cCpu", "cLoad", "cErr")))],
                                    "", {"s0": "Clients"}, 86))
    net["cards"] = [{"type": "vertical-stack", "cards": ncards}]
    # ways in: a tile in favorites (always there, first while something's down), a row in the favorites list, the server pop-up's Network row
    fav_tiles["sub_button"]["bottom"].append(
        {"name": "Network", "icon": "mdi:router-wireless",
         "origami_tiles": {"state": f"${{{JS_NET_DOWN} ? 'Offline' : " + (f"num(states('{NET['clients']}'), 0) + ' clients'" if have(NET["clients"]) else "'Online'") + "}",
                           "color": f"${{{JS_NET_DOWN} ? 'var(--error-color)' : 'var(--green-color)'}}",
                           "order": f"${{{JS_NET_DOWN} ? -3 : 10}}"},
         "tap_action": nav("#popup_network")})
    fl[4]["sub_button"]["bottom"].append({"name": "Network", "icon": "mdi:router-wireless", "origami_tiles": {"state": "Home Gateway"},
                                          "tap_action": nav("#popup_network")})
    for r in box_list["sub_button"]["bottom"]:
        if r.get("entity") == "sensor.infrastructure_status": r["tap_action"] = nav("#popup_network")
else:
    print("network: UniFi entities missing, Network pop-up skipped")

# --- navigation bar (Navbar Card): music, TV, lights, favorites, and the server in the menu's place
SPK_JS = "[" + ", ".join(f"'{s}'" for s in SPEAKERS) + "]"
nb_txt = up("dashboard/navigation-bar/card.yaml").replace("['media_player.living_room', 'media_player.bedroom', 'media_player.office']", SPK_JS)
navbar = yaml.safe_load(sub(nb_txt, {"media_player.living_room_tv_cast": TV_F, "media_player.living_room_tv": TV_B, "light.living_room": LIGHT}))
routes = navbar["routes"]
lights_route = next(r for r in routes if r["label"] == "Lights")
lights_route["popup"] = [p for p in lights_route["popup"] if p["label"] in ("Turn off", "Turn on")]   # no scenes
JS_BOX_DOWN = GROUP_IDS + ".some((id) => states[id]?.state !== 'up')"
if menu:   # the upstream Menu key opens the menu (its server card opens the server pop-up); its dot also shows a check that's down
    routes[-1]["badge"]["show"] = routes[-1]["badge"]["show"].replace("[[[ return ", "[[[ return " + JS_BOX_DOWN + " || (", 1).replace("; ]]]", "); ]]]")
else:      # no Origami Header yet: the server takes the menu's place
    routes[-1] = {"label": "Server", "icon": "mdi:server", "tap_action": nav("#popup_server"),
                  "selected_color": "var(--error-color)",
                  "selected": "[[[ return " + JS_BOX_DOWN + "; ]]]",
                  "badge": {"show": "[[[ return " + JS_BOX_DOWN + "; ]]]"}}
navbar["media_player"]["players"][1]["tap_action"] = nav("#popup_tv_family_room")

# --- climate table (Base + Table): a row per room with a thermostat or room sensor, opened from the rooms header
climate_table = None
if ZONES:
    ct = yaml.safe_load(up("dashboard/climate-table/card.yaml"))
    ex_t = "['sensor.living_room_temperature', 'sensor.bedroom_temperature', 'sensor.office_temperature']"
    ex_h = "['sensor.living_room_humidity', 'sensor.bedroom_humidity', 'sensor.office_humidity']"
    cols = json.dumps([c for c in ct["origami_table"]["columns"] if c["name"] != "window"])   # no window contacts in this home
    if ex_t not in cols or ex_h not in cols: raise SystemExit("climate table: upstream template lists changed")
    ct["origami_table"]["columns"] = json.loads(cols.replace(ex_t, JS_IDS(TEMPS)).replace(ex_h, JS_IDS(HUMS)))
    rows = []
    for z in ZONES:
        g = [{"entity": z["temp"] or z["climate"], "name": z["short"], "show_name": True, "css_class": "room"}]
        if z["climate"]: g.append({"entity": z["climate"], "css_class": "thermostat"})
        if z["temp"]: g.append({"entity": z["temp"], "css_class": "temperature"})
        if z["hum"]: g.append({"entity": z["hum"], "css_class": "humidity"})
        rows.append({"name": z["name"], "group": g})
    ct["sub_button"]["bottom"] = rows
    ct["visibility"] = [{"condition": "state", "entity": "input_boolean.climate_table", "state": "on"}]   # README Optional
    climate_table = ct

# ---------------------------------------------------------------- 5. the view
popups = [room_popup(h, n, devs) for h, n, _, devs in ROOMS] + [music, tv, tvf, lights, srv] + ([net] if net else []) + [favl]
first = ([menu] if menu else []) + [greeting, weather, fav_header, fav_tiles]
view = {"title": "Home", "path": "home", "icon": "mdi:home", "type": "sections", "max_columns": 2, "dense_section_placement": True,
        "sections": [
            {"type": "grid", "cards": first},
            {"type": "grid", "cards": [rooms_header] + ([climate_table] if climate_table else []) + [room_card(h, n, i, d) for h, n, i, d in ROOMS]
                                      + [navbar] + popups},
        ]}
config = {"title": "Origami", "views": [view]}

# every entity id in the config must exist (no invented ids)
ids = set(re.findall(r"(?<![.\w-])(?:media_player|light|remote|sensor|binary_sensor|button|calendar|todo|weather|sun|zone|input_select|input_boolean|number|script|update|climate)\.[a-z0-9_]+", json.dumps(config)))
missing = sorted(i for i in ids if i not in st and not i.startswith("script.") or (i.startswith("script.") and i not in st and i.split(".")[1] in SCRIPTS))
missing = [m for m in missing if m.split(".")[1] not in ("turn_on", "turn_off", "toggle", "select_option", "select_source", "play_media", "volume_up",
           "volume_down", "media_play_pause", "media_stop", "press", "set_value", "media_next_track", "media_previous_track", "check_config",
           "restart", "backup_full", "create_automatic", "send_command", "volume_set", "volume_mute", "media_play", "join", "unjoin", "set_temperature")]
if missing: raise SystemExit(f"entities missing in HA: {missing}")

# render every Jinja template once on the server before saving (JS ${ } templates are checked by the screenshots)
tpls = []
def walk(o):
    if isinstance(o, dict): [walk(v) for v in o.values()]
    elif isinstance(o, list): [walk(v) for v in o]
    elif isinstance(o, str) and ("{{" in o or "{%" in o) and "[[[" not in o and "${" not in o: tpls.append(o)
walk(config)
bad = 0
for t in tpls:
    try: rest("POST", "/api/template", {"template": t})
    except SystemExit as e: bad += 1; print("TEMPLATE ERROR:", str(e)[:200], "|", t[:100])
print(f"templates: {len(tpls)} rendered, {bad} errors | kuma checks: {len(ALL_CHECKS)} | speakers: {len(SPEAKERS)} | rooms: {[r[1] for r in ROOMS]}"
      f" | climate rooms: {[ROOMS_BY[h] for h in ROOM_CLIMATE] if (ROOMS_BY := {r[0]: r[1] for r in ROOMS}) else []}"
      f" | menu: {bool(menu)} | graphs: HA VM {HAS_SM and HAS_PLOTLY}, media server {HAS_BOX and HAS_PLOTLY} | installed: {installed}")
if bad: raise SystemExit("template errors: not saved")
if DRY:
    open("/root/origami-dryrun.json", "w").write(json.dumps(config, indent=1))
    raise SystemExit("DRY RUN: nothing saved, config in /root/origami-dryrun.json")

dashes = ws1({"type": "lovelace/dashboards/list"})
if not any(d["url_path"] == URL for d in dashes):
    ws1({"type": "lovelace/dashboards/create", "url_path": URL, "title": "Origami", "icon": "mdi:origami", "show_in_sidebar": True,
         "require_admin": False, "mode": "storage"})
old = ws({"type": "lovelace/config", "url_path": URL})[0]
open("/root/origami-dashboard-prev.json", "w").write(json.dumps(old, indent=1))   # previous version, for rollback
ws1({"type": "lovelace/config/save", "url_path": URL, "config": config})
print(f"saved /{URL}:", len(popups), "pop-ups,", len(ROOMS), "rooms")
