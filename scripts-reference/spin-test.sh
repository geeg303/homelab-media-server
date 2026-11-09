#!/usr/bin/env bash
# sdb = drive default timer; sda = hdparm -S 242 (60 min). Latency >5 s on first uncached read = drive had spun down.
probe(){ s=$(date +%s.%N); gnudd if=/dev/$1 of=/dev/null bs=4k count=1 skip=$((RANDOM*100003+$2)) iflag=direct status=none; e=$(date +%s.%N); echo "$(date -Is) $1 idle=$3min latency=$(echo "$e - $s" | bc)s"; }
LOG=/var/log/spin-test.log
hdparm -S 242 /dev/sda >/dev/null
probe sda 1 0 >>$LOG; probe sdb 1 0 >>$LOG
sleep 900;  probe sdb 7 15 >>$LOG
sleep 1800; probe sda 9 45 >>$LOG
sleep 3900; probe sda 11 65 >>$LOG
echo "$(date -Is) done" >>$LOG
