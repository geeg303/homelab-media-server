#!/usr/bin/env python3
# Create/refresh the "Home" Lovelace dashboard (sections views, built-in cards only). Idempotent. Run as root on the box.
import json, subprocess
def ws(*cmds):
    out = subprocess.run(["/usr/local/sbin/ha-ws", *[json.dumps(c) for c in cmds]], capture_output=True, text=True)
    if out.returncode: raise SystemExit(out.stderr[-400:])
    return [json.loads(l) for l in out.stdout.splitlines()]
URL = "home-hub"
st = {s["entity_id"]: s for s in ws({"type": "get_states"})[0]}
def have(e): return e in st
def tile(e, name=None, features=None, **kw):
    c = {"type": "tile", "entity": e, **kw}
    if name: c["name"] = name
    if features: c["features"] = features; c["features_position"] = "bottom"
    return c
def status(e, name, icon):
    up = [{"condition": "state", "entity": e, "state": "up"}]
    return [tile(e, name, icon=icon, color="green", state_content="state", visibility=up, grid_options={"columns": 6}),
            tile(e, name, icon="mdi:alert-circle", color="red", state_content="state",
                 visibility=[{"condition": "state", "entity": e, "state_not": "up"}], grid_options={"columns": 6})]
def heading(t, icon=None, badges=None):
    h = {"type": "heading", "heading": t, "heading_style": "title"}
    if icon: h["icon"] = icon
    if badges: h["badges"] = [{"type": "entity", "entity": b, "show_state": True, "show_icon": True} for b in badges if have(b)]
    return h
vol = [{"type": "media-player-volume-slider"}]
speakers = [("media_player.living_room_living_room", "Living Room"), ("media_player.main_bedroom_main_bedroom", "Main Bedroom"),
            ("media_player.five_five", "Five"), ("media_player.sonos_roam", "Roam")]
tvs = [("media_player.family_room_tv", "Family Room TV"), ("media_player.basement_ag_tv", "Basement TV"),
       ("media_player.bathroom_display", "Bathroom display")]
kuma = lambda n: f"sensor.{n}_status"
home = {
  "title": "Home", "path": "home", "icon": "mdi:home", "type": "sections", "max_columns": 4,
  "sections": [
    {"type": "grid", "cards": [heading("Weather", "mdi:weather-partly-cloudy"),
        {"type": "weather-forecast", "entity": "weather.home", "forecast_type": "daily", "show_current": True, "show_forecast": True, "grid_options": {"columns": "full"}}]},
    {"type": "grid", "cards": [heading("Speakers", "mdi:speaker-multiple")] +
        [tile(e, n, vol, grid_options={"columns": 12}) for e, n in speakers if have(e)]},
    {"type": "grid", "cards": [heading("TVs & displays", "mdi:television")] +
        [tile(e, n, None if e == "media_player.basement_ag_tv" else vol, grid_options={"columns": 12}) for e, n in tvs if have(e)]},
    {"type": "grid", "cards": [heading("Lights", "mdi:lightbulb-group"),
        tile("light.ring_light", "Ring Light", [{"type": "light-brightness"}], grid_options={"columns": 12}),
        heading("Lists", "mdi:format-list-checks"),
        {"type": "todo-list", "entity": "todo.shopping_list", "title": "Shopping list", "hide_completed": True, "grid_options": {"columns": "full"}}]},
  ]}
health = ["disk_space", "drive_health_smart", "all_10_drives_connected", "usb_watchdog", "quick_sync_gpu_no_hangs", "tailscale",
          "router_192_168_1_1", "internet_dns_lookup"]
health_names = ["Disk space", "Drive health", "All drives connected", "USB watchdog", "GPU", "Tailscale", "Router", "Internet"]
apps = [("plex", "Plex", "mdi:plex"), ("sonarr", "Sonarr", "mdi:television-classic"), ("radarr", "Radarr", "mdi:filmstrip"),
        ("sabnzbd", "SABnzbd", "mdi:download"), ("prowlarr", "Prowlarr", "mdi:magnify"), ("bazarr", "Bazarr", "mdi:subtitles-outline"),
        ("tautulli", "Tautulli", "mdi:chart-line"), ("seerr", "Seerr", "mdi:movie-search"), ("tdarr_web_ui", "Tdarr", "mdi:cog-transfer"),
        ("prismcast_web_ui", "PrismCast", "mdi:television-play"), ("homepage", "Homepage", "mdi:view-dashboard"),
        ("home_assistant", "Home Assistant", "mdi:home-assistant")]
srv = {
  "title": "Media server", "path": "server", "icon": "mdi:server", "type": "sections", "max_columns": 4,
  "badges": [{"type": "entity", "entity": kuma(g), "name": n, "show_name": True, "show_state": True, "show_icon": True,
              "color": "green", "visibility": [{"condition": "state", "entity": kuma(g), "state": "up"}]} for g, n in [("media_apps", "Apps"), ("infrastructure", "Network"), ("host_health", "Host"), ("storage_jobs", "Storage")] if have(kuma(g))],
  "sections": [
    {"type": "grid", "cards": [heading("Box health", "mdi:heart-pulse")] +
        [c for e, n in zip(health, health_names) if have(kuma(e)) for c in status(kuma(e), n, "mdi:check-circle-outline")]},
    {"type": "grid", "cards": [heading("Apps", "mdi:apps")] +
        [c for e, n, i in apps if have(kuma(e)) for c in status(kuma(e), n, i)]},
    {"type": "grid", "cards": [heading("Downloads", "mdi:download", badges=["sensor.192_168_1_242_status"]),
        tile("sensor.192_168_1_242_speed", "Speed", grid_options={"columns": 6}),
        tile("sensor.192_168_1_242_queue_count", "In queue", grid_options={"columns": 6}),
        tile("sensor.192_168_1_242_left_to_download", "Left", grid_options={"columns": 6}),
        tile("sensor.192_168_1_242_free_disk_space", "Free space", grid_options={"columns": 6}),
        tile("button.192_168_1_242_pause", "Pause", icon="mdi:pause", hide_state=True, grid_options={"columns": 6}),
        tile("button.192_168_1_242_resume", "Resume", icon="mdi:play", hide_state=True, grid_options={"columns": 6})]},
    {"type": "grid", "cards": [heading("Watching & coming up", "mdi:movie-open"),
        tile("sensor.tautulli_watching", "Streams now", icon="mdi:play-network", grid_options={"columns": 6}),
        tile("sensor.sonarr_upcoming", "Upcoming episodes", grid_options={"columns": 6}),
        {"type": "calendar", "entities": ["calendar.sonarr", "calendar.radarr"], "initial_view": "listWeek", "grid_options": {"columns": "full"}}]},
  ]}
srv["badges"] += [{"type": "entity", "entity": kuma(g), "name": n, "show_name": True, "show_state": True, "icon": "mdi:alert-circle", "color": "red",
                   "visibility": [{"condition": "state", "entity": kuma(g), "state_not": "up"}]} for g, n in [("media_apps", "Apps"), ("infrastructure", "Network"), ("host_health", "Host"), ("storage_jobs", "Storage")] if have(kuma(g))]
# fix tile "color" on non-light entities: only allowed via color key (fine), drop for safety on sensors without on/off states
for v in (srv,):
    for s in v["sections"]:
        for c in s["cards"]:
            if c.get("type") == "tile" and c.get("entity", "").startswith("sensor.") and c["entity"].endswith("_status"):
                c["state_content"] = "state"
dashes = ws({"type": "lovelace/dashboards/list"})[0]
if not any(d["url_path"] == URL for d in dashes):
    r = ws({"type": "lovelace/dashboards/create", "url_path": URL, "title": "Home", "icon": "mdi:home-heart", "show_in_sidebar": True, "require_admin": False, "mode": "storage"})[0]
    print("created dashboard:", "ERROR" not in r, r if "ERROR" in r else "")
r = ws({"type": "lovelace/config/save", "url_path": URL, "config": {"title": "Home", "views": [home, srv]}})[0]
print("saved config:", r)
back = ws({"type": "lovelace/config", "url_path": URL})[0]
cards = [c for v in back["views"] for s in v["sections"] for c in s["cards"]]
ents = [c["entity"] for c in cards if "entity" in c] + [e for c in cards for e in c.get("entities", [])]
missing = [e for e in ents if e not in st]
print("views:", [v["title"] for v in back["views"]], "| cards:", len(cards), "| entities:", len(ents), "| missing:", missing)
