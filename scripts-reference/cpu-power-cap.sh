#!/usr/bin/env bash
# cpu-power-cap: limit the i5-14500's package power (user, Nov 17: "do number 3 now").
# The OptiPlex Micro Plus 7020's fan stays at ~2,250 rpm under load, so at Dell's default 65 W / 154 W the CPU hits
# 100 °C within 3 minutes. Cap: long-term (PL1) 35 W, short-term (PL2) 65 W. Set on both RAPL interfaces (MSR and MMIO;
# the MMIO one can override the MSR one). Undo: systemctl disable --now cpu-power-cap.service && reboot (or write the
# defaults back: 65000000 / 154000000).
set -euo pipefail
PL1=${PL1_W:-35}; PL2=${PL2_W:-65}
for z in /sys/class/powercap/intel-rapl:0 /sys/class/powercap/intel-rapl-mmio:0; do
  [ -d "$z" ] || continue
  for c in 0 1; do
    n=$(cat "$z/constraint_${c}_name" 2>/dev/null || true)
    case "$n" in
      long_term)  echo $((PL1*1000000)) > "$z/constraint_${c}_power_limit_uw" ;;
      short_term) echo $((PL2*1000000)) > "$z/constraint_${c}_power_limit_uw" ;;
    esac
  done
  echo "$z: $(for c in 0 1; do printf '%s=%sW ' "$(cat $z/constraint_${c}_name)" $(( $(cat $z/constraint_${c}_power_limit_uw)/1000000 )); done)"
done
