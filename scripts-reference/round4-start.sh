#!/usr/bin/env bash
# round4-start: runs ONCE at boot after the clean-round-3 reboot (round4-after-reboot.service). Checks round 3 verify,
# keeps Tdarr paused, sets up the Migration tile for round 4 (sdb -> disk4, movies), starts migrate-round4 as its own unit.
set -uo pipefail
LOG=/var/log/migrate/round4-start.log; exec >> $LOG 2>&1
echo "=== $(date -Is) round4-start"
T=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
alert(){ curl -fsS -m 10 -H "Title: box migration R4" ${2:+-H "Priority: high"} -d "$1" "https://ntfy.sh/$T" >/dev/null || true; }
grep -q 'ROUND3 VERIFY TOTAL differences=0 ' /var/log/migrate/round3-verify.log || { alert "Round 4 NOT started: round 3 verify not clean" high; exit 1; }
[ -e /var/lib/media-server/round4.started ] && { echo "round 4 already started once"; exit 0; }
sleep 120   # let mounts, docker and the HA VM settle after the reboot
mountpoint -q /mnt/mig/sdb || { alert "Round 4 NOT started: /mnt/mig/sdb not mounted" high; exit 1; }
mountpoint -q /mnt/disk4 || { alert "Round 4 NOT started: /mnt/disk4 not mounted" high; exit 1; }
systemctl is-active --quiet migrate-round4 && { echo "already running"; exit 0; }
/usr/local/sbin/tdarr-workers set 0 0 || { alert "Round 4 NOT started: could not pause Tdarr" high; exit 1; }
for i in $(seq 1 90); do a=$(/usr/local/sbin/tdarr-workers active 2>/dev/null || echo 9); [ "$a" = 0 ] && break; sleep 60; done
echo "active transcodes now: ${a:-?} (after $i min)"
systemctl start tdarr-swap.service || true     # place the last encodes before copying starts
python3 - <<'PY'
import json, subprocess
p = "/etc/media-server/migration-rounds.json"; c = json.load(open(p))
used = sum(int(x) for x in subprocess.run("df -B1 --output=used /mnt/disk[0-9]* | tail -n +2", shell=True, capture_output=True, text=True).stdout.split())
c["4"] = {"label": "sdb → disk4 (WD 7SJ8JDXW) · movies", "total": 6.9e12, "format": "sdb → (your call)", "baseline": used,
          "sources": ["/mnt/mig/sdb/Movies"], "dest_shows": "/mnt/disk4/media/movies"}
c["5"] = {"label": "sde → disk5 (WD 7HJY59ZF)", "format": "sde → disk8"}
c["3"]["next"] = "round 4 running"
json.dump(c, open(p, "w"), ensure_ascii=False, indent=1)
print("migration-rounds.json: round 4 baseline", used)
PY
# own unit: a tmux started from a oneshot systemd-run unit is killed when that unit ends (Nov 12 bug)
touch /var/lib/media-server/round4.started
systemd-run --unit=migrate-round4 --collect -p Nice=5 /usr/local/sbin/migrate-round4
sleep 5; systemctl is-active --quiet migrate-round4 && echo "round4 runner started (unit migrate-round4)" || alert "Round 4 runner exited immediately — see /var/log/migrate/round4.log" high
