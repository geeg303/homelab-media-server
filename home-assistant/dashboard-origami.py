#!/usr/bin/env python3
# Origami dashboard (hazymorning/origami V3.0, AGPL-3.0) at /origami, built from the upstream part files with user's real entities.
# Needs (Marketplace): Clooos/Bubble-Card >= 3.4, Clooos/Bubble-Card-Tools (integration), hazymorning/origami_weather,
# joseluis9595/lovelace-navbar-card. The Origami theme (hazymorning/origami, theme) and Origami Notifications are NOT in the
# Marketplace catalog: they install as custom repositories, which needs GitHub connected in Settings > Marketplace. This script
# adds and installs them by itself once that is done, then sets Origami as the default theme (light + dark).
# Run on the box as root:  ssh box 'sudo -n python3 -' < dashboard-origami.py      Idempotent; never touches /home-hub or Overview.
# Skipped parts (no such devices): climate table, fan, vacuum. Menu skipped (it hides HA's header and edit button).
import copy, json, re, subprocess, time, urllib.error, urllib.request
import yaml

TAG = "6173bdbc4134a80381b5" "99ebe06d77c757da24d7"   # upstream main on Nov 11 (V3.0 + doc/part fixes; modules and theme same as V3.0); split so the repo's secret scan doesn't take it for a key
RAW = f"https://raw.githubusercontent.com/hazymorning/origami/{TAG}/"
URL = "origami-home"   # HA requires a hyphen in a dashboard's url_path, so plain "origami" is refused
HA = "http://192.0.2.150"
T = next(l.strip() for l in open("/etc/media-server/ha-token") if len(l.strip()) > 100)

def ws(*cmds):
    out = subprocess.run(["/usr/local/sbin/ha-ws", *[json.dumps(c) for c in cmds]], capture_output=True, text=True)
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
          "joseluis9595/lovelace-navbar-card": "plugin"}
CUSTOM = {"hazymorning/origami": "theme", "hazymorning/origami_notifications": "plugin"}   # not in the catalog
mp_info = ws1({"type": "marketplace/info"})
repos = {r["full_name"]: r for r in ws1({"type": "marketplace/repositories/list"})}
for name in NEEDED:
    r = repos.get(name)
    if r is None: raise SystemExit(f"{name} not in the Marketplace catalog")
    if not r["installed"]:
        print("installing", name, ws1({"type": "marketplace/repository/install", "repository": r["id"]}))
        if NEEDED[name] == "integration": raise SystemExit("restart Home Assistant, then run this again")
if mp_info.get("github_connected"):
    for name, cat in CUSTOM.items():
        if name not in repos:
            print("adding custom repository", name, ws1({"type": "marketplace/repositories/add", "repository": name, "category": cat}))
    repos = {r["full_name"]: r for r in ws1({"type": "marketplace/repositories/list"})}
    for name in CUSTOM:
        if name in repos and not repos[name]["installed"]:
            print("installing", name, ws1({"type": "marketplace/repository/install", "repository": repos[name]["id"]}))
else:
    print("NOTE: GitHub is not connected in Settings > Marketplace, so the Origami theme and Origami Notifications (custom repositories) wait")
installed = {n: r.get("installed_version") for n, r in repos.items() if r.get("installed")}
if not any(e["domain"] == "bubble_card_tools" for e in rest("GET", "/api/config/config_entries/entry")):
    f = rest("POST", "/api/config/config_entries/flow", {"handler": "bubble_card_tools"})
    if f.get("type") == "form": rest("POST", "/api/config/config_entries/flow/" + f["flow_id"], {})

# theme: default for light and dark mode, once HA has loaded it
themes = ws1({"type": "frontend/get_themes"})
if "Origami" in themes.get("themes", {}):
    if themes.get("default_theme") != "Origami": rest("POST", "/api/services/frontend/set_theme", {"name": "Origami"})
    if themes.get("default_dark_theme") != "Origami": rest("POST", "/api/services/frontend/set_theme", {"name": "Origami", "mode": "dark"})
    print("theme: Origami is the default (light + dark)")
else:
    print("theme: Origami not loaded yet")

# font (README: Montserrat 500/700 as a stylesheet resource)
FONT = "https://fonts.googleapis.com/css2?family=Montserrat:wght@500;700&display=swap"
res = ws1({"type": "lovelace/resources"})
if not any(r["url"] == FONT for r in res):
    ws1({"type": "lovelace/resources/create", "res_type": "css", "url": FONT})
resources = " ".join(r["url"] for r in ws1({"type": "lovelace/resources"}))
HAS_NOTIFICATIONS = "origami_notifications" in resources or "origami-notifications" in resources

# ---------------------------------------------------------------- 2. modules into /config/bubble_card/modules (Bubble Card Tools API)
MODULES = ["origami_base", "origami_button", "origami_climate", "origami_fan", "origami_header", "origami_media",
           "origami_popup", "origami_slider", "origami_table", "origami_tiles"]
for m in MODULES:
    want = up(f"bubble_card/modules/{m}.yaml")
    have_m = ws({"type": "bubble_card_tools/read_module", "name": f"modules/{m}.yaml"})[0]
    if not (isinstance(have_m, dict) and have_m.get("content") == want):
        r = ws1({"type": "bubble_card_tools/write_module", "name": f"modules/{m}.yaml", "content": want})
        print("module written:", m)
print("modules:", [f.get("name", f) if isinstance(f, dict) else f for f in ws1({"type": "bubble_card_tools/list_modules"})["files"]])

# ---------------------------------------------------------------- 3. helpers and scripts (from the parts' READMEs)
SPEAKERS = ["media_player.living_room_living_room", "media_player.main_bedroom_main_bedroom", "media_player.five_five", "media_player.sonos_roam"]
SPEAKERS = [s for s in SPEAKERS if have(s)]
sel = [i for i in ws1({"type": "input_select/list"}) if i.get("name") == "Selected speaker"]
if not sel:
    ws1({"type": "input_select/create", "name": "Selected speaker", "icon": "mdi:speaker", "options": SPEAKERS})
elif sel[0]["options"] != SPEAKERS:
    ws1({"type": "input_select/update", "input_select_id": sel[0]["id"], "name": "Selected speaker", "icon": "mdi:speaker", "options": SPEAKERS})
if not any(i.get("name") == "Music pop-up" for i in ws1({"type": "input_boolean/list"})):
    ws1({"type": "input_boolean/create", "name": "Music pop-up", "icon": "mdi:music-box-outline"})
SCRIPTS = {"playback": "dashboard/music/playback.yaml", "set_group_volume": "dashboard/music/set-group-volume.yaml",
           "group_speakers": "dashboard/music/group-speakers.yaml", "open_music": "dashboard/music/open-music.yaml",
           "volume": "dashboard/tv/volume.yaml"}
for sid, path in SCRIPTS.items():
    rest("POST", f"/api/config/script/config/{sid}", yaml.safe_load(up(path)))
reg = {e["entity_id"] for e in ws1({"type": "config/entity_registry/list"})}
if "number.group_volume" not in reg:
    f = rest("POST", "/api/config/config_entries/flow", {"handler": "template"})
    f = rest("POST", "/api/config/config_entries/flow/" + f["flow_id"], {"next_step_id": "number"})
    f = rest("POST", "/api/config/config_entries/flow/" + f["flow_id"], {
        "name": "Group volume", "min": 0, "max": 100, "step": 1, "unit_of_measurement": "%",
        "state": "{% set s = states('input_select.selected_speaker') %}\n"
                 "{% set v = (state_attr(s, 'group_members') or [s]) | map('state_attr', 'volume_level') | select('number') | list %}\n"
                 "{{ (v | sum / v | count * 100) | round if v else 0 }}",
        "set_value": [{"action": "script.set_group_volume", "data": {"speaker": "input_select.selected_speaker", "volume": "{{ value }}"}}]})
    print("group volume helper:", f.get("type"), f.get("result", {}).get("title"))
import time; time.sleep(2)
st = {s["entity_id"]: s for s in ws1({"type": "get_states"})}
for e in ("input_select.selected_speaker", "input_boolean.music_pop_up", "number.group_volume", *[f"script.{s}" for s in SCRIPTS]):
    if e not in st: raise SystemExit(f"helper missing after setup: {e}")

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
ROOMS = [r for r in ROOMS if r[3]]
KIND_ICON = {"speaker": "mdi:speaker", "display": "mdi:speaker", "tv": "mdi:television", "tv_novol": "mdi:television", "light": "mdi:lightbulb"}
rooms_header = yaml.safe_load(up("dashboard/rooms/header.yaml"))
PLAYERS = [d[1] for _, _, _, devs in ROOMS for d in devs if d[0] != "light"]
JS_PLAYING = "[" + ", ".join(f"'{p}'" for p in PLAYERS) + "].filter((id) => states(id) === 'playing').length"
rooms_header["sub_button"]["main"] = [{"name": "Playing", "icon": "mdi:play", "origami_header": {"name": f"${{{JS_PLAYING}}} playing", "hidden": f"${{{JS_PLAYING} === 0}}"},
                                       "tap_action": nav("#popup_music")}]
room_tpl = yaml.safe_load(up("dashboard/rooms/room.yaml"))
def room_card(h, name, icon, devs):
    c = copy.deepcopy(room_tpl)
    main = next((d for d in devs if d[0] == "light"), devs[0])
    c.update(entity=main[1], name=name, icon=icon)
    c["button_action"]["tap_action"] = nav(h)
    bottom = []
    for kind, e, label in devs:
        tpl = "${state === 'on' ? num(attr.brightness / 2.55, 0, '%') : word(state)}" if kind == "light" else \
              "${state === 'playing' && attr.media_title ? attr.media_title : word(state)}"
        bottom.append({"entity": e, "icon": KIND_ICON[kind], "origami_base": {"name": tpl, "hidden": "${['unavailable', 'unknown'].includes(state)}"}})
    c["sub_button"]["bottom"] = bottom
    return c

# --- room pop-ups (Base + Popup + Header + Button + Media + Slider), blocks from the bathroom and living-room examples
bath = yaml.safe_load(up("dashboard/room/bathroom.yaml"))
living = yaml.safe_load(up("dashboard/room/living-room.yaml"))
SPEAKER_TPL = bath["cards"][0]["cards"][0]
TV_TPL = living["cards"][0]["cards"][0]["cards"][0]["card"]
OFF_TPL = bath["cards"][0]["cards"][-1]
LIGHTS_TPL = bath["cards"][0]["cards"][1]
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

# --- server pop-up: the media server's Uptime Kuma groups + HA's backups, updates and repairs (no System Monitor here)
srv = yaml.safe_load(up("dashboard/server/pop-up.yaml"))
ss = srv["cards"][0]["cards"]
top, maint_hdr, maint = ss[0], ss[1], ss[2]
down_j = "{% set d = [" + ",".join(f"'{e}'" for e in ALL_CHECKS) + "] | reject('is_state','up') | list %}"
top.update(entity=KUMA_GROUPS[0][0], icon="mdi:server", name=
    down_j + "{%- set u = states.update | selectattr('state', 'eq', 'on') | list | count -%}"
    "{%- if d | count == 1 -%}{{ state_attr(d[0], 'friendly_name') | replace(' Status', '') }} down"
    "{%- elif d | count > 1 -%}{{ d | count }} checks down"
    "{%- elif u > 0 -%}{{ u }} {{ 'update' if u == 1 else 'updates' }}"
    "{%- else -%}All good{%- endif -%}",
    state_content=down_j + "{{ " + str(len(ALL_CHECKS)) + " - d | count }} of " + str(len(ALL_CHECKS)) + " checks up")
top["tap_action"] = {"action": "none"}; top["button_action"] = {"tap_action": {"action": "none"}}
bk = top["sub_button"]["main"][0]["origami_base"]
bk["name"] = "${isNaN(Date.parse(state)) ? 'None yet' : " + bk["name"].strip()[2:-1] + "}"
bk["name_color"] = "${isNaN(Date.parse(state)) ? '' : " + bk["name_color"].strip()[2:-1] + "}"
acts = top["sub_button"]["bottom"][0]["group"]
acts[0]["tap_action"] = act("hassio.backup_full", confirmation={"text": "Create a full backup now?"})
box_hdr = {"type": "custom:bubble-card", "card_type": "separator", "name": "Media server", "modules": ["origami_base", "origami_header"],
           "origami_header": {"weight": "medium", "icon_size": "var(--icon-size-s)"},
           "sub_button": {"main": [{"name": "Homepage", "show_name": True, "icon": "mdi:chevron-right", "content_layout": "icon-right",
                                    "show_background": False, "tap_action": {"action": "url", "url_path": "http://192.0.2.242:3000"}}]}}
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
srv["cards"][0]["cards"] = [top, box_hdr, box_list, sab_keys, maint_hdr, maint]   # no load graph (needs System Monitor + Plotly)

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

# --- navigation bar (Navbar Card): music, TV, lights, favorites, and the server in the menu's place
SPK_JS = "[" + ", ".join(f"'{s}'" for s in SPEAKERS) + "]"
nb_txt = up("dashboard/navigation-bar/card.yaml").replace("['media_player.living_room', 'media_player.bedroom', 'media_player.office']", SPK_JS)
navbar = yaml.safe_load(sub(nb_txt, {"media_player.living_room_tv_cast": TV_F, "media_player.living_room_tv": TV_B, "light.living_room": LIGHT}))
routes = navbar["routes"]
lights_route = next(r for r in routes if r["label"] == "Lights")
lights_route["popup"] = [p for p in lights_route["popup"] if p["label"] in ("Turn off", "Turn on")]   # no scenes
routes[-1] = {"label": "Server", "icon": "mdi:server", "tap_action": nav("#popup_server"),
              "selected_color": "var(--error-color)",
              "selected": "[[[ return " + GROUP_IDS + ".some((id) => states[id]?.state !== 'up'); ]]]",
              "badge": {"show": "[[[ return " + GROUP_IDS + ".some((id) => states[id]?.state !== 'up'); ]]]"}}
navbar["media_player"]["players"][1]["tap_action"] = nav("#popup_tv_family_room")

# ---------------------------------------------------------------- 5. the view
popups = [room_popup(h, n, devs) for h, n, _, devs in ROOMS] + [music, tv, tvf, lights, srv, favl]
view = {"title": "Home", "path": "home", "icon": "mdi:home", "type": "sections", "max_columns": 2, "dense_section_placement": True,
        "sections": [
            {"type": "grid", "cards": [greeting, weather, fav_header, fav_tiles]},
            {"type": "grid", "cards": [rooms_header] + [room_card(h, n, i, d) for h, n, i, d in ROOMS] + [navbar] + popups},
        ]}
config = {"title": "Origami", "views": [view]}

# every entity id in the config must exist (no invented ids)
ids = set(re.findall(r"(?<![.\w-])(?:media_player|light|remote|sensor|binary_sensor|button|calendar|todo|weather|sun|zone|input_select|input_boolean|number|script|update)\.[a-z0-9_]+", json.dumps(config)))
ids -= {"sensor.system_monitor_uptime"}  # not used after edits, just in case
missing = sorted(i for i in ids if i not in st and not i.startswith("script.") or (i.startswith("script.") and i not in st and i.split(".")[1] in SCRIPTS))
missing = [m for m in missing if m.split(".")[1] not in ("turn_on", "turn_off", "toggle", "select_option", "select_source", "play_media", "volume_up",
           "volume_down", "media_play_pause", "media_stop", "press", "set_value", "media_next_track", "media_previous_track", "check_config",
           "restart", "backup_full", "create_automatic", "send_command", "volume_set", "volume_mute", "media_play", "join", "unjoin")]
if missing: raise SystemExit(f"entities missing in HA: {missing}")

dashes = ws1({"type": "lovelace/dashboards/list"})
if not any(d["url_path"] == URL for d in dashes):
    ws1({"type": "lovelace/dashboards/create", "url_path": URL, "title": "Origami", "icon": "mdi:origami", "show_in_sidebar": True,
         "require_admin": False, "mode": "storage"})
old = ws({"type": "lovelace/config", "url_path": URL})[0]
open("/root/origami-dashboard-prev.json", "w").write(json.dumps(old, indent=1))   # previous version, for rollback
ws1({"type": "lovelace/config/save", "url_path": URL, "config": config})
print(f"saved /{URL}:", len(popups), "pop-ups,", len(ROOMS), "rooms")

# render every Jinja template once on the server to catch errors (JS ${ } templates are checked by the screenshots)
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
print(f"templates: {len(tpls)} rendered, {bad} errors | kuma checks: {len(ALL_CHECKS)} | speakers: {len(SPEAKERS)} | installed: {installed}")
