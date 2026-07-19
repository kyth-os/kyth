#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Sudoers: passwordless safe upgrade/firmware operations ────────────────────
# bootc upgrade/switch stages a new image but does not modify the running system —
# a reboot is always required to activate it. fwupdmgr operations are similarly
# safe (refresh = metadata fetch; get-updates/update = firmware staging).
# Allowing these without a password lets KythOS update flows run without a
# mid-stream sudo prompt that breaks the terminal flow.
# The 0440 mode (owner+group read, no write) is required by sudo's NOPASSWD check.
install -m 0440 /dev/stdin /etc/sudoers.d/kyth-upgrade <<'SUDOEOF'
# KythOS: wheel group may run safe update/firmware commands without a password.
%wheel ALL=(root) NOPASSWD: /usr/bin/bootc upgrade
%wheel ALL=(root) NOPASSWD: /usr/bin/bootc switch ghcr.io/mrtrick37/kyth\:*
%wheel ALL=(root) NOPASSWD: /usr/bin/fwupdmgr refresh
%wheel ALL=(root) NOPASSWD: /usr/bin/fwupdmgr update
%wheel ALL=(root) NOPASSWD: /usr/bin/fwupdmgr get-updates
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-set-epp *
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-rclone-update
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set *
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx restart
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx stop
%wheel ALL=(root) NOPASSWD: /usr/bin/systemctl start kyth-flathub-setup.service
%wheel ALL=(root) NOPASSWD: /usr/bin/systemctl start kyth-default-flatpaks.service
%wheel ALL=(root) NOPASSWD: /usr/bin/systemctl restart kyth-default-flatpaks.service
# distrobox enter --root internally calls "sudo podman exec/start/inspect" to
# manage rootful containers.  From a KDE app launcher (no TTY) sudo cannot
# prompt for a password, so GUI apps like zenmap would silently fail.
# Granting blanket podman access here is equivalent to the user's existing
# full sudo access — it only removes the interactive prompt for GUI launches.
%wheel ALL=(root) NOPASSWD: /usr/bin/podman
SUDOEOF
