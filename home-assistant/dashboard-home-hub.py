#!/usr/bin/env python3
# "Home" dashboard v2 (Nov 11): Mushroom on the main page, Bubble Card pop-ups per room + media server.
# Needs Marketplace installs: piitaya/lovelace-mushroom, Clooos/Bubble-Card. Run on the box as root (uses /usr/local/sbin/ha-ws). Idempotent.
import json, subprocess
def ws(*cmds):
    out = subprocess.run(["/usr/local/sbin/ha-ws", *[json.dumps(c) for c in cmds]], capture_output=True, text=True)
    if out.returncode: raise SystemExit(out.stderr[-400:])
    return [json.loads(l) for l in out.stdout.splitlines()]
URL = "home-hub"
st = {s["entity_id"]: s for s in ws({"type": "get_states"})[0]}
have = lambda e: e in st
nav = lambda h: {"action": "navigate", "navigation_path": h}

# ---------- rooms: (hash, name, icon, [(entity, label, kind)])  kind: speaker | tv | tv_novol | light
ROOMS = [
    ("#living-room", "Living Room", "mdi:sofa", [("media_player.living_room_living_room", "Sonos Beam", "speaker")]),
    ("#family-room", "Family Room", "mdi:television", [("media_player.family_room_tv", "Family Room TV", "tv")]),
    ("#main-bedroom", "Main Bedroom", "mdi:bed-king", [("media_player.main_bedroom_main_bedroom", "Sonos Ray", "speaker")]),
    ("#basement", "Basement", "mdi:stairs-down", [("media_player.basement_ag_tv", "Basement TV", "tv_novol"), ("light.ring_light", "Ring Light", "light")]),
    ("#bathroom", "Bathroom", "mdi:shower", [("media_player.bathroom_display", "Nest Hub Max", "tv")]),
    ("#speakers", "More speakers", "mdi:speaker-multiple", [("media_player.five_five", "Sonos Five", "speaker"), ("media_player.sonos_roam", "Sonos Roam", "speaker")]),
]
ACTIVE = "['playing','on','paused','buffering']"
def room_secondary(devs):
    # e.g. "Sonos Beam · Playing Song" / "Ring Light on" / "All off"
    parts = []
    for e, label, kind in devs:
        if kind == "light":
            parts.append(f"{{% if is_state('{e}','on') %}}{label} {{{{ state_attr('{e}','brightness') | int(0) * 100 // 255 }}}}%|{{% endif %}}")
        else:
            parts.append(f"{{% if is_state('{e}','playing') %}}▶ {{{{ state_attr('{e}','media_title') or '{label}' }}}}|"
                         f"{{% elif is_state('{e}','on') %}}{label} on|{{% elif is_state('{e}','paused') %}}{label} paused|{{% endif %}}")
    return "{% set s = '" + "' %}{% set s = s ~ '".join([""]) + "' %}" if False else \
        "{% set s %}" + "".join(parts) + "{% endset %}{{ s.strip('|').replace('|', ' · ') if s.strip('|') else 'All quiet' }}"
def room_color(devs):
    ents = [e for e, _, _ in devs]
    return "{{ 'amber' if " + " or ".join(f"states('{e}') in {ACTIVE}" for e in ents) + " else 'disabled' }}"

def room_card(h, name, icon, devs):
    return {"type": "custom:mushroom-template-card", "primary": name, "secondary": room_secondary(devs), "icon": icon,
            "color": room_color(devs), "tap_action": nav(h), "icon_tap_action": nav(h), "multiline_secondary": False,
            "grid_options": {"columns": 6, "rows": 1}}

def popup_cards(devs):
    out = []
    for e, label, kind in devs:
        if not have(e): continue
        if kind == "light":
            out.append({"type": "custom:bubble-card", "card_type": "button", "button_type": "slider", "entity": e, "name": label,
                        "icon": "mdi:lightbulb", "show_state": True, "grid_options": {"columns": "full"}})
        else:
            c = {"type": "custom:bubble-card", "card_type": "media-player", "entity": e, "name": label, "card_layout": "large",
                 "cover_background": True, "grid_options": {"columns": "full"}}
            if kind == "tv_novol": c["hide"] = {"volume_button": True}
            out.append(c)
    return out

def popup(h, name, icon, cards):
    return {"type": "custom:bubble-card", "card_type": "pop-up", "hash": h, "name": name, "icon": icon,
            "button_type": "name", "popup_style": "bubble", "bg_opacity": "88", "bg_blur": "14", "cards": cards}

# ---------- media server
kuma = lambda n: f"sensor.{n}_status"
GROUPS = [("media_apps", "Apps"), ("infrastructure", "Network"), ("host_health", "Box health"), ("storage_jobs", "Storage & jobs")]
GROUP_ENTS = [kuma(g) for g, _ in GROUPS if have(kuma(g))]
GROUP_ALL = {kuma(g) for g in ("media_apps", "background_containers", "infrastructure", "host_health", "storage_jobs")}
ALL_CHECKS = sorted(e for e in st if e.startswith("sensor.") and e.endswith("_status") and e not in GROUP_ALL
                    and st[e]["state"] in ("up", "down", "pending", "maintenance"))
down_tpl = "{% set d = [" + ",".join(f"'{e}'" for e in ALL_CHECKS) + "] | reject('is_state','up') | list %}"
server_secondary = down_tpl + "{{ 'All ' ~ " + str(len(ALL_CHECKS)) + " ~ ' checks up' if d | count == 0 else (d | count) ~ ' down: ' ~ (d | map('state_attr','friendly_name') | map('replace',' Status','') | join(', ')) }}"
server_color = down_tpl + "{{ 'green' if d | count == 0 else 'red' }}"
HEALTH = [("disk_space", "Disk space", "mdi:harddisk"), ("drive_health_smart", "Drive health", "mdi:heart-pulse"),
          ("all_10_drives_connected", "Drives connected", "mdi:usb"), ("usb_watchdog", "USB watchdog", "mdi:shield-check"),
          ("quick_sync_gpu_no_hangs", "GPU", "mdi:expansion-card"), ("tailscale", "Tailscale", "mdi:vpn"),
          ("router_192_168_1_1", "Router", "mdi:router-wireless"), ("internet_dns_lookup", "Internet", "mdi:web")]
APPS = [("plex", "Plex", "mdi:plex"), ("sonarr", "Sonarr", "mdi:television-classic"), ("radarr", "Radarr", "mdi:filmstrip"),
        ("sabnzbd", "SABnzbd", "mdi:download"), ("prowlarr", "Prowlarr", "mdi:magnify"), ("bazarr", "Bazarr", "mdi:subtitles-outline"),
        ("tautulli", "Tautulli", "mdi:chart-line"), ("seerr", "Seerr", "mdi:movie-search"), ("tdarr_web_ui", "Tdarr", "mdi:cog-transfer"),
        ("prismcast_web_ui", "PrismCast", "mdi:television-play"), ("homepage", "Homepage", "mdi:view-dashboard"),
        ("home_assistant", "Home Assistant", "mdi:home-assistant")]
def check(e, name, icon):
    return {"type": "custom:mushroom-template-card", "entity": e, "primary": name,
            "secondary": "{{ 'OK' if is_state(entity,'up') else states(entity) | capitalize }}", "icon": icon,
            "color": "{{ 'green' if is_state(entity,'up') else 'red' }}", "tap_action": {"action": "more-info"},
            "grid_options": {"columns": 6, "rows": 1}}
SAB = "sensor.192_168_1_242_"
server_popup = popup("#server", "Media server", "mdi:server", [
    {"type": "custom:bubble-card", "card_type": "separator", "name": "Box health", "icon": "mdi:heart-pulse"},
    *[check(kuma(e), n, i) for e, n, i in HEALTH if have(kuma(e))],
    {"type": "custom:bubble-card", "card_type": "separator", "name": "Apps", "icon": "mdi:apps"},
    *[check(kuma(e), n, i) for e, n, i in APPS if have(kuma(e))],
    {"type": "custom:bubble-card", "card_type": "separator", "name": "Downloads", "icon": "mdi:download"},
    {"type": "custom:bubble-card", "card_type": "button", "button_type": "state", "entity": SAB + "status", "name": "SABnzbd",
     "icon": "mdi:download", "grid_options": {"columns": "full"},
     "sub_button": [{"entity": SAB + "speed", "show_state": True, "show_icon": True, "icon": "mdi:speedometer", "show_background": False},
                    {"entity": SAB + "queue_count", "show_state": True, "icon": "mdi:tray-full", "show_background": False},
]},
    *[{"type": "custom:bubble-card", "card_type": "button", "button_type": "name", "name": n, "icon": i, "grid_options": {"columns": 6},
       "button_action": {"tap_action": {"action": "perform-action", "perform_action": "button.press", "target": {"entity_id": b},
                                         "confirmation": {"text": f"{n} all downloads?"}}}}
      for b, n, i in (("button.192_168_1_242_pause", "Pause", "mdi:pause"), ("button.192_168_1_242_resume", "Resume", "mdi:play"))],
    {"type": "custom:bubble-card", "card_type": "separator", "name": "Watching & coming up", "icon": "mdi:movie-open"},
    {"type": "custom:bubble-card", "card_type": "button", "button_type": "state", "entity": "sensor.tautulli_watching", "name": "Plex streams",
     "icon": "mdi:play-network", "grid_options": {"columns": 6}},
    {"type": "custom:bubble-card", "card_type": "button", "button_type": "state", "entity": "sensor.sonarr_upcoming", "name": "Upcoming",
     "icon": "mdi:calendar-clock", "grid_options": {"columns": 6}},
    {"type": "custom:bubble-card", "card_type": "calendar", "entities": [{"entity": "calendar.sonarr"}, {"entity": "calendar.radarr"}],
     "days": 7, "limit": 6, "grid_options": {"columns": "full"}},
])

# ---------- main page (Mushroom)
players = [e for _, _, _, devs in ROOMS for e, _, k in devs if k != "light" and have(e)]
playing_tpl = "{% set p = [" + ",".join(f"'{e}'" for e in players) + "] | select('is_state','playing') | list %}"
greeting = {"type": "custom:mushroom-title-card",
            "title": "{% set h = now().hour %}Good {{ 'morning' if h < 12 else 'afternoon' if h < 18 else 'evening' }}, user",
            "subtitle": "{{ now().strftime('%A, %B ') ~ now().day }}", "grid_options": {"columns": "full"}}
chips = {"type": "custom:mushroom-chips-card", "alignment": "start", "grid_options": {"columns": "full"}, "chips": [
    {"type": "weather", "entity": "weather.home", "show_conditions": True, "show_temperature": True},
    {"type": "template", "icon": "mdi:play-circle", "icon_color": "{{ 'amber' if p | count else 'disabled' }}",
     "content": playing_tpl + "{{ (p | count) ~ ' playing' if p | count else 'Nothing playing' }}"},
    {"type": "template", "icon": "mdi:plex", "icon_color": "{{ 'orange' if states('sensor.tautulli_watching') | int(0) else 'disabled' }}",
     "content": "{{ states('sensor.tautulli_watching') | int(0) }} on Plex", "tap_action": nav("#server")},
    {"type": "template", "icon": "{{ 'mdi:check-circle' if d | count == 0 else 'mdi:alert-circle' }}".replace("{{", down_tpl + "{{", 1),
     "icon_color": server_color, "content": down_tpl + "{{ 'Server OK' if d | count == 0 else (d | count) ~ ' down' }}", "tap_action": nav("#server")},
]}
now_playing = [{"type": "custom:mushroom-media-player-card", "entity": e, "use_media_info": True, "show_volume_level": True,
                "media_controls": ["play_pause_stop", "next"], "volume_controls": ["volume_set"], "fill_container": True,
                "visibility": [{"condition": "state", "entity": e, "state": "playing"}], "grid_options": {"columns": "full"}} for e in players]
server_card = {"type": "custom:mushroom-template-card", "primary": "Media server", "secondary": server_secondary, "icon": "mdi:server",
               "color": server_color, "tap_action": nav("#server"), "icon_tap_action": nav("#server"), "multiline_secondary": True,
               "grid_options": {"columns": "full"}}
home = {
  "title": "Home", "path": "home", "icon": "mdi:home", "type": "sections", "max_columns": 3, "dense_section_placement": True,
  "sections": [
    {"type": "grid", "column_span": 3, "cards": [greeting, chips]},
    {"type": "grid", "cards": [{"type": "heading", "heading": "Rooms", "heading_style": "subtitle"}] +
        [room_card(h, n, i, devs) for h, n, i, devs in ROOMS if any(have(e) for e, _, _ in devs)]},
    {"type": "grid", "cards": [{"type": "heading", "heading": "Now playing", "heading_style": "subtitle"},
        {"type": "custom:mushroom-template-card", "primary": "Nothing playing", "secondary": "Start something on a speaker or TV",
         "icon": "mdi:music-note-off", "color": "disabled",
         "visibility": [{"condition": "state", "entity": e, "state_not": "playing"} for e in players], "grid_options": {"columns": "full"}}]
        + now_playing},
    {"type": "grid", "cards": [{"type": "heading", "heading": "Media server", "heading_style": "subtitle"}, server_card,
        {"type": "heading", "heading": "Lists", "heading_style": "subtitle"},
        {"type": "custom:mushroom-template-card", "entity": "todo.shopping_list", "primary": "Shopping list",
         "secondary": "{{ states('todo.shopping_list') | int(0) }} item{{ '' if states('todo.shopping_list') | int(0) == 1 else 's' }}",
         "icon": "mdi:cart-outline", "color": "{{ 'blue' if states('todo.shopping_list') | int(0) else 'disabled' }}",
         "tap_action": nav("#lists"), "icon_tap_action": nav("#lists"), "grid_options": {"columns": "full"}}]},
    {"type": "grid", "cards": [popup(h, n, i, popup_cards(devs)) for h, n, i, devs in ROOMS] + [server_popup,
        popup("#lists", "Shopping list", "mdi:cart-outline", [{"type": "todo-list", "entity": "todo.shopping_list", "hide_completed": True, "grid_options": {"columns": "full"}}])]},
  ]}
dashes = ws({"type": "lovelace/dashboards/list"})[0]
if not any(d["url_path"] == URL for d in dashes):
    ws({"type": "lovelace/dashboards/create", "url_path": URL, "title": "Home", "icon": "mdi:home-heart", "show_in_sidebar": True, "require_admin": False, "mode": "storage"})
old = ws({"type": "lovelace/config", "url_path": URL})[0]
open("/root/home-hub-v1.json", "w").write(json.dumps(old, indent=1))   # previous version, for rollback
print("saved:", ws({"type": "lovelace/config/save", "url_path": URL, "config": {"title": "Home", "views": [home]}})[0])
# render every template once server-side to catch Jinja errors
tpls = []
def walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, str) and "{" in v and k in ("primary", "secondary", "color", "icon", "icon_color", "content", "title", "subtitle"): tpls.append(v)
            else: walk(v)
    elif isinstance(o, list): [walk(x) for x in o]
walk(home)
import urllib.request
T = next(l.strip() for l in open("/etc/media-server/ha-token") if len(l.strip()) > 100)
bad = 0
for t in tpls:
    t2 = t.replace("entity", "'sensor.plex_status'") if "is_state(entity" in t or "states(entity" in t else t
    r = urllib.request.Request("http://192.0.2.150/api/template", data=json.dumps({"template": t2}).encode(), method="POST",
                               headers={"Authorization": "Bearer " + T, "Content-Type": "application/json"})
    try: v = urllib.request.urlopen(r, timeout=10).read().decode()
    except urllib.error.HTTPError as e: bad += 1; print("TEMPLATE ERROR:", e.read()[:200], "|", t[:120])
print(f"templates: {len(tpls)} rendered, {bad} errors | checks counted: {len(ALL_CHECKS)} | players: {len(players)}")
