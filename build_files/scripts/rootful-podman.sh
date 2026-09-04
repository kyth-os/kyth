#!/usr/bin/env bash
# Run rootful Podman in a fresh cgroup namespace.
#
# Codex/Chromium desktop sessions can outlive their systemd scope. In that
# state Podman reads a cgroup.controllers path that no longer exists and a
# build can hang after COMMIT. A new cgroup namespace gives Podman a valid
# view without changing the host cgroup hierarchy.
set -euo pipefail

if ((EUID == 0)); then
	exec unshare --cgroup podman "$@"
fi

exec sudo --preserve-env=MOK_KEY unshare --cgroup podman "$@"
