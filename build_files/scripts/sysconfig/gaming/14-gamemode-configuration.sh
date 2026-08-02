#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── gamemode configuration ────────────────────────────────────────────────────
# Applied when a game calls gamemoderun or uses the gamemode SDL hook.
# renice/ioprio: game process gets higher CPU + I/O scheduling priority.
# gpu: switches AMD GPU to high-performance power profile during gameplay.
write_config /etc/gamemode.ini <<'GAMEMODEEOF'
[general]
renice = 10
ioprio = 0
# Inhibit screensaver during gameplay — prevents blanking during cutscenes/loads
inhibit_screensaver = 1
# Older ports may issue split locks. Relax the mitigation only while GameMode is
# active, then restore the secure system-wide default when the game exits.
disable_splitlock = 1
# Promote game threads to SCHED_FIFO via rtkit when conditions allow.
# 'auto' only engages when the system is not under memory pressure.
softrealtime = auto
# Switch to the gaming performance profile automatically when a game launches
# via GameMode, and restore the previous state on exit.
# kyth-performance-mode: saves current powerprofile + KWin blur/animation state,
# switches to performance power profile + reduced animations, then restores on exit.
# GameMode runs startscript/endscript via /bin/sh -c as the game user.
# DBUS_SESSION_BUS_ADDRESS may not be inherited (depends on how the game was
# launched), so we set it explicitly via the logind socket path as a fallback.
# unix:path=/run/user/UID/bus is guaranteed present for any logged-in user.
startscript=export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"; /usr/bin/kyth-performance-mode save && /usr/bin/kyth-performance-mode gaming
endscript=DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}" /usr/bin/kyth-performance-mode restore

[cpu]
park_cores = no
pin_cores = yes

[gpu]
apply_gpu_optimisations = accept-responsibility
amd_performance_level = high
nv_perf_level = 5
GAMEMODEEOF
