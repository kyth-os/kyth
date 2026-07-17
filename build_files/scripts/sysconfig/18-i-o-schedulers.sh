#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── I/O schedulers ─────────────────────────────────────────────────────────
# Keep NVMe on kernel defaults. Testers can opt into the experimental KythOS
# profile with `ujust nvme-tuning kyth` and compare it against a clean reboot
# after `ujust nvme-tuning default`.
# 'mq-deadline' on SATA SSD — adds deadline fairness with minimal latency.
# 'bfq' on rotational — budget fair queuing prevents seek storms.
mkdir -p /etc/udev/rules.d
cat >/etc/udev/rules.d/60-ioschedulers.rules <<'IOEOF'
# SATA SSDs (non-rotational): deadline with low latency + 1 MB read-ahead
ACTION=="add|change", KERNEL=="sd[a-z]*", ATTR{queue/rotational}=="0", ATTR{queue/scheduler}="mq-deadline"
ACTION=="add|change", KERNEL=="sd[a-z]*", ATTR{queue/rotational}=="0", ATTR{queue/read_ahead_kb}="1024"
# HDDs: BFQ to avoid seek storms
ACTION=="add|change", KERNEL=="sd[a-z]*", ATTR{queue/rotational}=="1", ATTR{queue/scheduler}="bfq"
# VirtIO block (QEMU/KVM VMs): mq-deadline — BFQ can stall under heavy sequential I/O
ACTION=="add|change", KERNEL=="vd[a-z]*", ATTR{queue/scheduler}="mq-deadline"
IOEOF

