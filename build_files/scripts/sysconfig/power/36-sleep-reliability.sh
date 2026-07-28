#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/config-helpers.sh"

# ── Sleep reliability ─────────────────────────────────────────────────────────
# Hybrid sleep and suspend-then-hibernate are common causes of black screen on
# wake for gaming PCs: the NVRAM hibernation image doesn't survive a full power
# cycle on NVMe + proprietary GPU combinations, and the kernel's resume path
# can hang waiting for a swap partition that may not exist.
#
# AllowHibernation=no disables hibernation entirely; SuspendState=mem requests
# S3 (hardware-level suspend-to-RAM) rather than s2idle (CPU halt + PCIe active),
# which drains more power and is more prone to wake-on-USB spurious events.
# s2idle is still used as a fallback on systems that don't advertise S3 support.
write_config /etc/systemd/sleep.conf.d/kyth-sleep.conf <<'SLEEPEOF'
[Sleep]
AllowSuspend=yes
AllowHibernation=no
AllowHybridSleep=no
AllowSuspendThenHibernate=no
SuspendState=mem standby freeze
SLEEPEOF
