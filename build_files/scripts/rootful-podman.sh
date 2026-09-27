#!/usr/bin/env bash
# Run rootful Podman in a fresh cgroup namespace.
#
# Codex/Chromium desktop sessions can outlive their systemd scope. In that
# state Podman reads a cgroup.controllers path that no longer exists and a
# build can hang after COMMIT. A new cgroup namespace gives Podman a valid
# view without changing the host cgroup hierarchy.
set -euo pipefail

# The development checkout is commonly run from inside kyth-ai-dev, a
# Distrobox container.  Its nested cgroup mount is read-only and contains the
# outer Chromium scope, so Podman cannot inspect the cgroup controllers even
# when the container user is root.  Delegate to the host user's Podman in that
# case; the host has the real cgroup hierarchy and the same bind-mounted
# checkout.  Keep this before the rootful path because sudo inside Distrobox
# only grants container-root, not host-root.
if [[ -n "${CONTAINER_ID:-}" || -x /run/host/usr/bin/distrobox-host-exec ]] &&
	command -v distrobox-host-exec >/dev/null 2>&1; then
	host_xdg_runtime_dir="${KYTH_HOST_XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
	exec distrobox-host-exec env "XDG_RUNTIME_DIR=${host_xdg_runtime_dir}" podman "$@"
fi

if ((EUID == 0)); then
	exec unshare --cgroup podman "$@"
fi

exec sudo --preserve-env=MOK_KEY unshare --cgroup podman "$@"
