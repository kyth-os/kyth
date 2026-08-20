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

# systemd waits for dev-zram0.device via udev; the device appears only
# after udev processes the synthetic block uevent. On FA617NS the real
# root's systemd-udevd was not running for ~122s after switch-root, so
# the 10s->132s gap blocked swap.target and delayed graphical.target.
# Use a short fail-fast timeout (30s) and rely on early modprobe + initramfs
# (51-zram.sh) to guarantee the device exists. Do not extend to 180s —
# that only hides the race and makes boot 2m longer.
mkdir -p /etc/systemd/system/dev-zram0.device.d
cat > /etc/systemd/system/dev-zram0.device.d/10-timeout.conf <<'DEVTIMEOUT'
[Unit]
JobTimeoutSec=30
JobRunningTimeoutSec=30
DEVTIMEOUT

# Ensure zram uevent is tagged for systemd even when ID_FS probing is slow
# (amdgpu/nvme coldplug starved the worker on FA617NS). The block device
# already reports TAGS=:systemd: after ID_FS_TYPE=swap, but an explicit rule
# guarantees SYSTEMD_READY=1 before swap.target ordering.
write_config /usr/lib/udev/rules.d/99-kyth-zram.rules <<'ZRAMRULE'
KERNEL=="zram0", TAG+="systemd", ENV{SYSTEMD_READY}="1"
ZRAMRULE

# Async swap: zram swap should not block graphical boot. The generator
# creates dev-zram0.swap with Before=swap.target, and swap.target is
# otherwise required transitively by sysinit. Allow boot to proceed even
# if zram races; swap will still be activated within seconds when
# systemd-zram-setup finishes.
mkdir -p /etc/systemd/system/swap.target.d
cat > /etc/systemd/system/swap.target.d/10-kyth-async.conf <<'SWAPASYNC'
[Unit]
JobTimeoutSec=30
JobRunningTimeoutSec=30
SWAPASYNC

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
