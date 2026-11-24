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
# system disks: percent. Data disks: a full disk is normal in a mergerfs pool (minfreespace=100G keeps new files away),
# so alert only below 25 GB free; the pool itself alerts at 95% (Nov 15: disk5 holds 7.9 TB of TV at 99% by design).
while read -r pct mnt; do p=${pct%\%}; lim=90
  [ "$p" -ge "$lim" ] && bad="$bad $mnt ${p}% (limit ${lim}%);"
done < <(df --output=pcent,target / /scratch 2>/dev/null | tail -n +2)
while read -r avail mnt; do [ "$avail" -lt 25 ] && bad="$bad $mnt only ${avail} GB free (limit 25 GB);"
done < <(df -B1G --output=avail,target /mnt/disk* 2>/dev/null | tail -n +2)
p=$(df --output=pcent /data 2>/dev/null | tail -1 | tr -dc 0-9); [ -n "$p" ] && [ "$p" -ge 95 ] && bad="$bad /data pool ${p}% (limit 95%);"
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
    # link/cable error counter (attr 199): ntfy once per increase (user Nov 24), baseline per serial
    crc=$(echo "$out" | awk '$1==199{print $NF}'); bf="$STATE/crc-$s"
    if [ -n "$crc" ]; then
      if [ -f "$bf" ] && [ "$crc" -gt "$(cat "$bf")" ]; then
        mp=$(lsblk -no MOUNTPOINT "$d" 2>/dev/null | grep -m1 .)
        NT=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
        curl -fsS -m 10 -H "Title: box: cable/USB errors rising on ${mp:-$s}" -H "Priority: high" \
          -d "Drive $s (${mp:-not mounted}): link (CRC) errors went from $(cat "$bf") to $crc. The disk itself is fine; this points at the SATA/USB cable or the enclosure. Reseat or replace it if it keeps rising." \
          "https://ntfy.sh/$NT" >/dev/null || true
      fi
      echo "$crc" > "$bf"
    fi
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
for j in tdarr:tdarr selftest:selftest dash:disks eng:eng; do u=${j%%:*}-status; f=/opt/media/status/${j#*:}.json
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
# switches (USW Flex Mini, Nov 15): own Kuma push + /opt/media/status/unifi.json for the Homepage tiles
import os, time, subprocess
info = {"updated": time.strftime("%a %-I:%M %p"), "updated_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "devices": []}
for dv in get("/stat/device"):
    if dv.get("type") != "usw": continue
    n = dv.get("name") or dv.get("model"); up = dv.get("state") == 1
    ul = dv.get("uplink") or {}; ports = dv.get("port_table") or []
    errs = sum(int(p.get("rx_errors") or 0) + int(p.get("tx_errors") or 0) for p in ports)
    sp = lambda p: (("1G" if p.get("speed") == 1000 else f"{p.get('speed')}M") if p.get("up") else "–")
    ss = dv.get("system-stats") or {}; upt = int(dv.get("uptime") or 0)
    pg = subprocess.run(["ping", "-c1", "-W2", dv.get("ip") or "0.0.0.0"], capture_output=True, text=True).stdout
    m = __import__("re").search(r"time=([\d.]+)", pg)
    d = dict(name=n, model=dv.get("model"), ip=dv.get("ip"), state="online" if up else "OFFLINE",
             uptime=(f"{upt // 86400}d {upt % 86400 // 3600}h" if upt >= 86400 else f"{upt // 3600}h {upt % 3600 // 60}m"),
             uplink=((f"{ul.get('speed') / 1000:g} Gbps" if (ul.get("speed") or 0) >= 1000 else f"{ul.get('speed')} Mbps") if ul.get("up") else "DOWN"),
             uplink_to=f"router port {ul.get('uplink_remote_port')}",
             ports_up=f"{sum(1 for p in ports if p.get('up'))} of {len(ports)}",
             ports=" · ".join(f"P{p.get('port_idx')} {sp(p)}" + (" uplink" if p.get("is_uplink") else "") for p in ports),
             errors=errs, cpu=f"{float(ss.get('cpu') or 0):.0f}%", mem=f"{float(ss.get('mem') or 0):.0f}%",
             ping=(f"{float(m.group(1)):.0f} ms" if m else "no reply"),
             firmware=(dv.get("version") or "?") + (" (update available)" if dv.get("upgradable") else ""))
    info["devices"].append(d)
    bad2 = ([] if up else ["offline in UniFi"]) + ([] if ul.get("up") else ["uplink down"]) + \
           ([f"uplink only {ul.get('speed')} Mbps"] if ul.get("up") and (ul.get("speed") or 0) < 1000 else []) + ([] if m else ["no ping reply"])
    print(f"UniFi switch (Flex Mini)|{'down' if bad2 else 'up'}|" + ("; ".join(bad2) if bad2 else
          f"online {d['uptime']} · uplink {ul.get('speed')} Mbps · ports {d['ports_up']} up · {errs} port errors · ping {d['ping']}"))
if info["devices"]: info.update({f"sw_{k}": v for k, v in info["devices"][0].items()})
else: print("UniFi switch (Flex Mini)|down|switch not found in UniFi")
tmp = "/opt/media/status/unifi.json.tmp"
with open(tmp, "w") as f: __import__("json").dump(info, f, indent=1, ensure_ascii=False)
os.chmod(tmp, 0o644); os.replace(tmp, "/opt/media/status/unifi.json")
PY
)
fi
# --- push
while IFS=$'\t' read -r name tok; do [ -n "$name" ] && [ -n "${RES[$name]+x}" ] || continue
  st=${RES[$name]%%|*}; msg=${RES[$name]#*|}
  curl -fsS -m 8 -G "$KUMA/$tok" --data-urlencode "status=$st" --data-urlencode "msg=$msg" >/dev/null 2>&1 || true
done < "$CONF"
