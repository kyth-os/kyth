# shellcheck shell=bash
# ── Gaming performance CLI tools ───────────────────────────────────────────────
install -m 0755 /ctx/game-performance /usr/bin/game-performance
install -m 0755 /ctx/kyth-gamescope /usr/bin/kyth-gamescope
install -m 0755 /ctx/kyth-performance-mode /usr/bin/kyth-performance-mode
install -m 0755 /ctx/kyth-scx /usr/bin/kyth-scx
install -m 0755 /ctx/kyth-nvme-tuning /usr/bin/kyth-nvme-tuning
install -m 0755 /ctx/zink-run /usr/bin/zink-run
install -m 0755 /ctx/low-latency-run /usr/bin/low-latency-run
# Sourced (not executed directly) by kyth-kerver and kyth-snappy-bench below.
install -m 0644 /ctx/kyth-perf-report-common.sh /usr/libexec/kyth-perf-report-common.sh
install -m 0755 /ctx/kyth-kerver /usr/bin/kyth-kerver
install -m 0755 /ctx/kyth-snappy-bench /usr/bin/kyth-snappy-bench
install -m 0755 /ctx/kyth-device-info /usr/bin/kyth-device-info
