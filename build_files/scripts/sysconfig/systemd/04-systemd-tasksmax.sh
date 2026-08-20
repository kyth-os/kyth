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
mkdir -p /etc/systemd/system/user.slice.d
cat > /etc/systemd/system/user.slice.d/10-tasksmax.conf <<'USERSLICE'
[Slice]
TasksMax=80%
USERSLICE
