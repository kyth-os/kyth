#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── Sleep reliability ─────────────────────────────────────────────────────────
# Hybrid sleep and suspend-then-hibernate are common causes of black screen on
# wake for gaming PCs: the NVRAM hibernation image doesn't survive a full power
# cycle on NVMe + proprietary GPU combinations, and the kernel's resume path
# can hang waiting for a swap partition that may not exist.
#
# AllowHibernation=no disables hibernation entirely; systemd tries
# SuspendState entries in order and uses the first supported. FA617NS host
# (TUF Gaming A16, 2026-08-20) advertises only [s2idle] (AMD Modern Standby,
# no S3) — so mem is not available and systemd falls through standby→freeze
# (s2idle). Listing mem first keeps S3 systems fast while preserving correct
# fallback to s2idle/Freeze on Phoenix/Raphael laptops without log spam.
write_config /etc/systemd/sleep.conf.d/kyth-sleep.conf <<'SLEEPEOF'
[Sleep]
AllowSuspend=yes
AllowHibernation=no
AllowHybridSleep=no
AllowSuspendThenHibernate=no
SuspendState=mem standby freeze
HibernateDelaySec=0
SLEEPEOF
