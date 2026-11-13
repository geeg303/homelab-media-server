#!/usr/bin/env bash
# reboot-after-round3 (user Nov 13: "Yes reboot after the check finishes").
# Waits for migrate-round3 to finish; ONLY if its verify total is 0 differences: apt upgrade + reboot.
# HA VM: libvirt-guests set to a clean shutdown (default 'suspend' can fail to restore with the USB Wi-Fi passthrough).
set -uo pipefail
LOG=/var/log/media-server/reboot-after-round3.log; mkdir -p /var/log/media-server
exec >> "$LOG" 2>&1
T=$(grep -m1 '^NTFY_TOPIC=' /opt/media/stacks/ops/.env | cut -d= -f2)
alert(){ curl -fsS -m 10 -H "Title: box maintenance" ${2:+-H "Priority: high"} -d "$1" "https://ntfy.sh/$T" >/dev/null || true; }
echo "=== $(date -Is) waiting for migrate-round3 to finish"
for i in $(seq 1 480); do systemctl is-active --quiet migrate-round3 || break; sleep 60; done
if systemctl is-active --quiet migrate-round3; then echo "still running after 8 h: no reboot"; alert "Reboot skipped: round 3 still running after 8 h" high; exit 1; fi
sleep 5
if ! grep -q 'ROUND3 VERIFY TOTAL differences=0 ' /var/log/migrate/round3-verify.log; then
  echo "verify total is not 0 (or missing): NO reboot"; grep 'ROUND3 VERIFY TOTAL' /var/log/migrate/round3-verify.log
  alert "Reboot skipped: round 3 verify did not report 0 differences. Check round3-verify.log" high; exit 1
fi
echo "$(date -Is) round 3 verified clean: $(grep 'ROUND3 VERIFY TOTAL' /var/log/migrate/round3-verify.log)"
# HA VM: shut down cleanly instead of managed-save
cp -a /etc/default/libvirt-guests /root/libvirt-guests.bak-20261113
grep -q '^ON_SHUTDOWN=' /etc/default/libvirt-guests && sed -i 's/^ON_SHUTDOWN=.*/ON_SHUTDOWN=shutdown/' /etc/default/libvirt-guests || echo 'ON_SHUTDOWN=shutdown' >> /etc/default/libvirt-guests
grep -E '^(ON_SHUTDOWN|SHUTDOWN_TIMEOUT|PARALLEL_SHUTDOWN)' /etc/default/libvirt-guests
# OS updates (no removals allowed)
export DEBIAN_FRONTEND=noninteractive
apt-get update -q || { alert "Reboot skipped: apt-get update failed" high; exit 1; }
if apt-get -s full-upgrade | grep -q '^Remv'; then MODE=upgrade; else MODE=full-upgrade; fi
echo "apt mode: $MODE"
apt-get -y -q -o Dpkg::Options::=--force-confold -o Dpkg::Options::=--force-confdef $MODE || { alert "Reboot skipped: apt $MODE failed, see $LOG" high; exit 1; }
echo "$(date -Is) updates installed; reboot-required: $( [ -f /var/run/reboot-required ] && echo yes || echo no)"
date -Is > /var/lib/media-server/reboot-after-round3.stamp
alert "Round 3 verified clean (0 differences). Updates installed; rebooting the box now (~5 min)."
sync; sleep 5
systemctl reboot
