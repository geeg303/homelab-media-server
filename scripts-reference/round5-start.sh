#!/usr/bin/env bash
# round5-start (user Nov 14: "2. Yes" = start round 5 automatically when round 4 verifies with 0 differences).
# Waits for migrate-round4 to finish; only on 'ROUND4 VERIFY TOTAL differences=0': pool branches disk4 back to RW,
# disk5 + disk6 to NC (round 5 writes there), Migration tile for round 5, then migrate-round5 as its own unit.
set -uo pipefail
LOG=/var/log/migrate/round5-start.log; exec >> $LOG 2>&1
echo "=== $(date -Is) round5-start: waiting for migrate-round4"
T=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
alert(){ curl -fsS -m 10 -H "Title: box migration R5" ${2:+-H "Priority: high"} -d "$1" "https://ntfy.sh/$T" >/dev/null || true; }
for i in $(seq 1 2880); do systemctl is-active --quiet migrate-round4 || break; sleep 60; done
systemctl is-active --quiet migrate-round4 && { alert "Round 5 NOT started: round 4 still running after 48 h" high; exit 1; }
sleep 10
if ! grep -q 'ROUND4 VERIFY TOTAL differences=0 ' /var/log/migrate/round4-verify.log; then
  echo "round 4 verify not clean: $(grep 'ROUND4 VERIFY TOTAL' /var/log/migrate/round4-verify.log)"
  alert "Round 5 NOT started: round 4 verify did not report 0 differences. sdb untouched; see round4-verify.log" high; exit 1
fi
echo "round 4 clean: $(grep 'ROUND4 VERIFY TOTAL' /var/log/migrate/round4-verify.log)"
[ -e /var/lib/media-server/round5.started ] && { echo "round 5 already started once"; exit 0; }
for m in /mnt/mig/sde /mnt/disk5 /mnt/disk6 /data; do mountpoint -q $m || { alert "Round 5 NOT started: $m not mounted" high; exit 1; }; done
/usr/local/sbin/tdarr-workers set 0 0 || { alert "Round 5 NOT started: could not pause Tdarr" high; exit 1; }
# pool: disk4 takes new files again, disk5/disk6 don't (live via mergerfs xattr + fstab for the next boot)
B=/mnt/disk1:/mnt/disk2:/mnt/disk3:/mnt/disk4:/mnt/disk5=NC:/mnt/disk6=NC
python3 -c "import os,sys; os.setxattr('/data/.mergerfs','user.mergerfs.branches',sys.argv[1].encode()); print('branches:', os.getxattr('/data/.mergerfs','user.mergerfs.branches').decode())" "$B" || { alert "Round 5 NOT started: could not change pool branches" high; exit 1; }
cp -a /etc/fstab /etc/fstab.bak-$(date +%Y%m%d-%H%M)-r5
sed -i 's#^/mnt/disk1:/mnt/disk2:/mnt/disk3:/mnt/disk4=NC:/mnt/disk5:/mnt/disk6  /data #/mnt/disk1:/mnt/disk2:/mnt/disk3:/mnt/disk4:/mnt/disk5=NC:/mnt/disk6=NC  /data #; s#^\# mergerfs pool (Nov 13). disk4=NC: round 4.*#\# mergerfs pool. disk5+disk6=NC while round 5 (sde -> disk5, review -> disk6) writes there; drop =NC after round 5.#' /etc/fstab
grep -n 'fuse.mergerfs' /etc/fstab | cut -c1-120; systemctl daemon-reload
python3 - <<'PY'
import json, subprocess
p = "/etc/media-server/migration-rounds.json"; c = json.load(open(p))
used = sum(int(x) for x in subprocess.run("df -B1 --output=used /mnt/disk[0-9]* | tail -n +2", shell=True, capture_output=True, text=True).stdout.split())
c["5"] = {"label": "sde → disk5 (WD 7HJY59ZF) · TV", "total": 7.954e12, "format": "sde → (your call)", "baseline": used,
          "sources": ["/mnt/mig/sde/TV Shows"], "dest_shows": "/mnt/disk5/media/tv"}
c.setdefault("4", {})["next"] = "round 5 running"
json.dump(c, open(p, "w"), ensure_ascii=False, indent=1)
print("migration-rounds.json: round 5 baseline", used)
PY
touch /var/lib/media-server/round5.started
systemd-run --unit=migrate-round5 --collect -p Nice=5 /usr/local/sbin/migrate-round5
sleep 5; systemctl is-active --quiet migrate-round5 && echo "round5 runner started (unit migrate-round5)" || alert "Round 5 runner exited immediately, see /var/log/migrate/round5.log" high
