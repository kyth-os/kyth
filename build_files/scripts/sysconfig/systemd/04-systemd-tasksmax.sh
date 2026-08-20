#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── Systemd TasksMax hardening ───────────────────────────────────────────
# Logs show 89× pthread_create: Resource temporarily unavailable at 17:03,
# causing Brave/Edge zygotes to fail to fork and systemd to fail to spawn
# drkonqi (Failed to spawn executor: Resource temporarily unavailable).
# The global pid_max is 4M and threads-max ~119k, but the per-cgroup
# TasksMax default (33% of threads-max ≈ 12k threads per user slice) is
# exhausted by the burst of Chromium renderer processes + flatpak portals +
# kdeconnect + xdg-portal all forking simultaneously. Raising DefaultTasksMax
# and the user slice limit prevents the desktop stall that looks like
# "applications won't open" while keeping a bound to catch fork bombs.

# Raise system-wide default from 33% to 80% of threads-max (~95k).
write_config /etc/systemd/system.conf.d/10-kyth-tasksmax.conf <<'TASKSMAX'
[Manager]
DefaultTasksMax=80%
TASKSMAX

write_config /etc/systemd/user.conf.d/10-kyth-tasksmax.conf <<'USERTASKSMAX'
[Manager]
DefaultTasksMax=80%
USERTASKSMAX

# Explicitly lift the user slice which was the bottleneck in the 17:03 burst.
# Host FA617NS (2026-08-20) showed fork rejected for every browser:
#   app.slice pids.max=512 pids.current=508 (code-insiders 310 threads alone)
#   Brave: pthread_create Resource temporarily unavailable -> FATAL BrowserThread:IO
#   Edge/cobalt, flatpak-portal g_task_thread_pool_init failed similarly.
# System DefaultTasksMax=80% raised user.slice to 95791 but user manager
# DefaultTasksMax=80% did not apply to the per-session app.slice (still 512
# — compiled default for F44 user sessions). Need explicit drop-ins for
# app.slice/session.slice/background.slice.
write_config /etc/systemd/system/user.slice.d/10-tasksmax.conf <<'USERSLICE'
[Slice]
TasksMax=80%
USERSLICE

# Lift app.slice/session.slice/background.slice which run browsers and portals.
# app.slice hosts all Flatpak browsers (Brave/Edge) + Code + Discover;
# session.slice hosts KWin/plasmashell; background.slice hosts xdg-portal.
# Without these, DefaultTasksMax from user.conf alone leaves app.slice at 512.
write_config /etc/systemd/user/app.slice.d/10-kyth-tasksmax.conf <<'APPSLICE'
[Slice]
TasksMax=80%
APPSLICE

write_config /etc/systemd/user/session.slice.d/10-kyth-tasksmax.conf <<'SESSSLICE'
[Slice]
TasksMax=80%
SESSSLICE

write_config /etc/systemd/user/background.slice.d/10-kyth-tasksmax.conf <<'BGSLICE'
[Slice]
TasksMax=80%
BGSLICE

# Also cover system-level user@.service delegation: ensure the delegated
# cgroup does not clamp app.slice via the 512 fallback on old images that
# upgraded via ostree without user daemon-reexec.
write_config /etc/systemd/system/user@.service.d/10-kyth-tasksmax.conf <<'USERSVC'
[Service]
TasksMax=80%
USERSVC
