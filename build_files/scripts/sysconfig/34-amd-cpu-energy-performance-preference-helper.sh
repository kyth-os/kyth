#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── AMD CPU Energy Performance Preference helper ─────────────────────────────
# kyth-performance-mode calls this via sudo to set EPP on all CPU cores.
# On amd_pstate=active systems, EPP is the primary
# frequency/voltage scaling knob — more direct than powerprofilesctl alone.
# Valid values: performance, balance_performance, balance_power, power, default

install -m 0755 /dev/stdin /usr/bin/kyth-set-epp <<'EPPEOF'
#!/bin/bash
EPP="${1:-balance_performance}"
case "$EPP" in
    performance|balance_performance|balance_power|power|default) ;;
    *)
        echo "kyth-set-epp: invalid EPP value: ${EPP}" >&2
        echo "Valid values: performance, balance_performance, balance_power, power, default" >&2
        exit 1
        ;;
esac
changed=0
for f in /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference; do
    [[ -f "$f" ]] || continue
    echo "$EPP" > "$f" 2>/dev/null && changed=1 || true
done
[[ $changed -eq 1 ]] || echo "kyth-set-epp: no EPP sysfs nodes found (non-AMD or pstate inactive)" >&2
EPPEOF
