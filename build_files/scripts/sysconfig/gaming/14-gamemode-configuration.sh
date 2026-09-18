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
# Split-lock mitigation stays at the secure system default while gaming.
# Relaxing it here widened the window to every process on the box for the whole
# game session, not just the game slice; titles that genuinely need legacy
# split-lock behavior opt in per-launch outside of GameMode. Do not set this
# back to 1 without scoping the relaxation to the game slice.
disable_splitlock = 0
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
pin_cores = no
# pin_cores is now owned by sched_arbiter (single writer). Default no when SCX is
# available; arbiter flips to yes only on BORE + explicit opt-in. Do not change
# this default without updating kyth_shared/sched_arbiter.py.

[gpu]
apply_gpu_optimisations = accept-responsibility
amd_performance_level = high
nv_perf_level = 5
GAMEMODEEOF

# Restore on crash: if GameMode (or the game session) dies before endscript
# runs, the saved pre-game power state would stick. This login-time user unit
# restores it once when a stale save exists; with no save file it exits quietly
# (kyth-performance-mode restore is a no-op without state, and the save lives
# under $XDG_RUNTIME_DIR, so a reboot already clears cross-boot staleness).
write_config /usr/lib/systemd/user/kyth-performance-restore.service <<'GAMERESTOREEOF'
[Unit]
Description=Restore pre-game power state left behind by a crashed session
After=default.target
# Per-user save path: $XDG_RUNTIME_DIR/kyth-performance-mode.state
ConditionPathExists=%t/kyth-performance-mode.state

[Service]
Type=oneshot
ExecStart=/usr/bin/kyth-performance-mode restore
RemainAfterExit=yes

[Install]
WantedBy=default.target
GAMERESTOREEOF

systemctl --global enable kyth-performance-restore.service 2>/dev/null || true
