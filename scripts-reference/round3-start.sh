#!/usr/bin/env bash
# round3-start: run after wd-format-batch succeeded. Pauses Tdarr (user: pause during rounds 3-5), lets running encodes finish
# and get swapped in, sets up the Migration tile for round 3, then starts migrate-round3 in tmux session "round3".
set -uo pipefail
LOG=/var/log/migrate/round3-start.log; exec >> $LOG 2>&1
echo "=== $(date -Is) round3-start"
T=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
alert(){ curl -fsS -m 10 -H "Title: box migration R3" ${2:+-H "Priority: high"} -d "$1" "https://ntfy.sh/$T" >/dev/null || true; }
[ -e /var/lib/media-server/wd-format.done ] || { echo "format not done"; alert "Round 3 NOT started: WD format not complete" high; exit 1; }
mountpoint -q /mnt/disk3 || { alert "Round 3 NOT started: /mnt/disk3 not mounted" high; exit 1; }
tmux has-session -t round3 2>/dev/null && { echo "already running"; exit 0; }
/usr/local/sbin/tdarr-workers set 0 0 || { alert "Round 3 NOT started: could not pause Tdarr" high; exit 1; }
for i in $(seq 1 90); do a=$(/usr/local/sbin/tdarr-workers active 2>/dev/null || echo 9); [ "$a" = 0 ] && break; sleep 60; done
echo "active transcodes now: ${a:-?} (after $i min)"
systemctl start tdarr-swap.service || true     # place the last encodes before copying starts
python3 - <<'PY'
import json, subprocess
p = "/etc/media-server/migration-rounds.json"; c = json.load(open(p))
used = sum(int(x) for x in subprocess.run("df -B1 --output=used /mnt/disk[0-9]* | tail -n +2", shell=True, capture_output=True, text=True).stdout.split())
c["3"] = {"label": "sdd → disk3 (WD SERIAL-WD1)", "total": 7.349e12, "format": "sdd → disk7", "baseline": used,
          "sources": ["/mnt/mig/sdd/TV Shows", "/mnt/mig/sdd/_from_sdc/TV Shows"], "dest_shows": "/mnt/disk3/media/tv"}
c["2"]["next"] = "round 3 running"
json.dump(c, open(p, "w"), ensure_ascii=False, indent=1)
print("migration-rounds.json: round 3 baseline", used)
PY
tmux new-session -d -s round3 /usr/local/sbin/migrate-round3
sleep 5; tmux has-session -t round3 && echo "round3 started in tmux" || alert "Round 3 runner exited immediately — see /var/log/migrate/round3.log" high
