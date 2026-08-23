#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── NTSYNC ───────────────────────────────────────────────────────────
# Custom kernels may ship ntsync. The udev rule gives the 'users' group access
# to /dev/ntsync so Wine/Proton can use NT synchronization primitives when the
# module is available.
write_line 'ntsync' /usr/lib/modules-load.d/kyth-ntsync.conf
write_line 'KERNEL=="ntsync", GROUP="users", MODE="0660"' /usr/lib/udev/rules.d/99-ntsync.rules

# zram-size: tuned for 16GB ASUS TUF FA617NS (2026-08-20 host trace:
# 10.76s Add device -> 132.83s Found device = 122s udevd stall, zram 7.4G
# with zstd). Use 50% RAM capped at 8G (matches Fedora zram-generator-defaults
# and memory_tune.py low-tier) to reduce mkswap pressure on 16GB APUs where
# VRAM shares system RAM. Use lz4 for faster init on APU; memory_tune.py
# overrides compression at runtime for high-RAM hosts if needed.
# swap-priority=100 ensures zram is always chosen over any disk swap.
write_config /etc/systemd/zram-generator.conf <<'ZRAMEOF'
[zram0]
zram-size = min(ram * 0.5, 8192)
compression-algorithm = lz4
swap-priority = 100
ZRAMEOF

# zram swap is owned by kyth-zram-swap.service (51-zram.sh). Do not
# attach JobTimeoutSec to dev-zram0.device or swap.target — that is
# what listed a 30s timeout as a failed boot unit. The generator is
# stubbed and the udev device/swap units are masked there.

# TUF FA617NS has no Thunderbolt dock; boltd probing hit 2s timeout at
# 17:41:09 during the same udev stall window. Masking is too aggressive;
# reduce its settle impact via udev timeout tuning.
mkdir -p /etc/systemd/system/systemd-udev-trigger.service.d
cat > /etc/systemd/system/systemd-udev-trigger.service.d/10-kyth-timeout.conf <<'UDEVTRIG'
[Service]
TimeoutStartSec=30
UDEVTRIG

# Host trace showed systemd-udevd was Deactivated at 17:39:00 initrd-cleanup
# and not restarted until 17:41:04 — the exact 122s window that blocked
# dev-zram0.device. Ensure ordering: any kyth first-boot service that runs
# After=local-fs.target must not delay sysinit/udevd. Pin udevd to start
# before kyth-boot-splash-initramfs and greenboot.
mkdir -p /etc/systemd/system/systemd-udevd.service.d
cat > /etc/systemd/system/systemd-udevd.service.d/10-kyth-early.conf <<'UDEVDEARLY'
[Unit]
Before=kyth-boot-splash-initramfs.service greenboot-set-rollback-trigger.service kyth-selinux-relabel-home.service
UDEVDEARLY
