#!/usr/bin/env bash
# host-health-push: host-level checks (Nov 11: + status tiles fresh, usb-watchdog) pushed to Uptime Kuma every 5 min (Nov 11). Config: /etc/media-server/host-health-push.conf
# ("<monitor name>\t<push token>" per line, mode 600). Each check pushes status=up, or status=down with the reason; Kuma alerts via ntfy.
set -u
CONF=/etc/media-server/host-health-push.conf; [ -f "$CONF" ] || exit 0
KUMA=http://127.0.0.1:3001/api/push
STATE=/var/lib/media-server/host-health; mkdir -p "$STATE"
EXPECT="SERIAL-DISK2 SERIAL-SDB SERIAL-DISK1 SERIAL-SDD SERIAL-SDE SERIAL-WD1 7SJ8JDXW 7HJY59ZF 7HJY82BF 7HK2YR2H"
declare -A RES
# --- disk space
bad=""
while read -r pct mnt; do p=${pct%\%}; lim=97; case "$mnt" in /|/scratch) lim=90;; esac
  [ "$p" -ge "$lim" ] && bad="$bad $mnt ${p}% (limit ${lim}%);"
done < <(df --output=pcent,target / /scratch /mnt/disk* 2>/dev/null | tail -n +2)
RES["Disk space"]=${bad:+down|$bad}; RES["Disk space"]=${RES["Disk space"]:-up|all under limits}
# --- drives connected
miss=""; for s in $EXPECT; do ls /dev/disk/by-id/ata-*_"$s" >/dev/null 2>&1 || miss="$miss $s"; done
RES["All 10 drives connected"]=${miss:+down|missing:$miss}; RES["All 10 drives connected"]=${RES["All 10 drives connected"]:-up|10/10 present}
# --- SMART every 30 min (cached in between)
if [ ! -f "$STATE/smart" ] || [ $(( $(date +%s) - $(stat -c %Y "$STATE/smart") )) -ge 1700 ]; then
  sb=""
  for s in $EXPECT; do d=$(ls /dev/disk/by-id/ata-*_"$s" 2>/dev/null | head -1); [ -n "$d" ] || continue
    out=$(smartctl -d sat -H -A "$d" 2>/dev/null)
    echo "$out" | grep -q "PASSED" || sb="$sb $s health-not-PASSED;"
    pend=$(echo "$out" | awk '$1==197{print $NF}'); unc=$(echo "$out" | awk '$1==198{print $NF}')
    [ "${pend:-0}" != 0 ] && sb="$sb $s pending=$pend;"; [ "${unc:-0}" != 0 ] && sb="$sb $s uncorrectable=$unc;"
  done
  if [ -n "$sb" ]; then echo "down|$sb" > "$STATE/smart"; else echo "up|10 drives healthy" > "$STATE/smart"; fi
fi
RES["Drive health (SMART)"]=$(cat "$STATE/smart")
# --- Tailscale
ts=$(tailscale status --json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('BackendState',''))" 2>/dev/null)
[ "$ts" = Running ] && RES["Tailscale"]="up|Running" || RES["Tailscale"]="down|BackendState=${ts:-unreachable}"
# --- GPU hangs
h=$(journalctl -k --since "-10 min" --no-pager 2>/dev/null | grep -c "GPU HANG")
[ "$h" = 0 ] && RES["Quick Sync GPU (no hangs)"]="up|no hangs" || RES["Quick Sync GPU (no hangs)"]="down|$h GPU HANG messages in 10 min"
# --- Tdarr swap
systemctl is-failed --quiet tdarr-swap.service && RES["Tdarr swap job"]="down|tdarr-swap.service failed" || RES["Tdarr swap job"]="up|ok"
# --- dashboard status tiles fresh (only jobs whose timer is enabled)
st=""
for j in tdarr:tdarr migration:migration selftest:selftest dash:disks eng:eng; do u=${j%%:*}-status; f=/opt/media/status/${j#*:}.json
  systemctl is-enabled --quiet "$u.timer" 2>/dev/null || continue
  systemctl is-failed --quiet "$u.service" && { st="$st $u failed;"; continue; }
  [ -f "$f" ] || { st="$st ${f##*/} missing;"; continue; }
  age=$(( $(date +%s) - $(stat -c %Y "$f") )); [ "$age" -gt 600 ] && st="$st ${f##*/} $((age/60)) min old;"
done
RES["Status tiles up to date"]=${st:+down|$st}; RES["Status tiles up to date"]=${RES["Status tiles up to date"]:-up|all fresh}
# --- usb watchdog
systemctl is-active --quiet usb-watchdog.service && RES["USB watchdog"]="up|running" || RES["USB watchdog"]="down|usb-watchdog.service $(systemctl is-active usb-watchdog.service)"
# --- UniFi (read-only Network API key, line 3 of /etc/media-server/unifi-creds)
if [ -f /etc/media-server/unifi-creds ]; then
  while IFS='|' read -r name st msg; do [ -n "$name" ] && RES["$name"]="$st|$msg"; done < <(python3 - <<'PY' 2>/dev/null || echo "UniFi internet (WAN)|down|health script failed"
import json, ssl, urllib.request
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
key = [l.strip() for l in open("/etc/media-server/unifi-creds") if l.strip()][2]
def get(p):
    r = urllib.request.Request("https://192.0.2.1/proxy/network/api/s/default" + p, headers={"X-API-KEY": key, "Accept": "application/json"})
    return json.loads(urllib.request.urlopen(r, context=ctx, timeout=10).read())["data"]
try:
    h = {x["subsystem"]: x for x in get("/stat/health")}
except Exception as e:
    for n in ("UniFi internet (WAN)", "UniFi Wi-Fi", "UniFi router health"): print(f"{n}|down|UniFi API unreachable: {type(e).__name__}")
    raise SystemExit
w, www, wl = h.get("wan", {}), h.get("www", {}), h.get("wlan", {})
lat = www.get("latency")
ok = w.get("status") == "ok" and www.get("status") == "ok"
print(f"UniFi internet (WAN)|{'up' if ok else 'down'}|wan {w.get('status')} · internet {www.get('status')}" + (f" · {lat} ms" if lat is not None else ""))
print(f"UniFi Wi-Fi|{'up' if wl.get('status') == 'ok' else 'down'}|wifi {wl.get('status')} · {wl.get('num_user', '?')} clients · {wl.get('num_ap', '?')} AP")
bad = []
for dv in get("/stat/device"):
    n = dv.get("name") or dv.get("model")
    if dv.get("state") != 1: bad.append(f"{n} offline")
    ss = dv.get("system-stats", {}); cpu, mem = float(ss.get("cpu", 0) or 0), float(ss.get("mem", 0) or 0)
    if cpu >= 90: bad.append(f"{n} CPU {cpu:.0f}%")
    if mem >= 90: bad.append(f"{n} memory {mem:.0f}%")
    for t in dv.get("temperatures", []) or []:
        if float(t.get("value", 0)) >= 85: bad.append(f"{n} {t.get('name')} {t.get('value')}°C")
print(f"UniFi router health|{'down' if bad else 'up'}|" + ("; ".join(bad) if bad else "all UniFi devices healthy"))
PY
)
fi
# --- push
while IFS=$'\t' read -r name tok; do [ -n "$name" ] && [ -n "${RES[$name]+x}" ] || continue
  st=${RES[$name]%%|*}; msg=${RES[$name]#*|}
  curl -fsS -m 8 -G "$KUMA/$tok" --data-urlencode "status=$st" --data-urlencode "msg=$msg" >/dev/null 2>&1 || true
done < "$CONF"
