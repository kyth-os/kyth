#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Sudoers: passwordless safe upgrade/firmware operations ────────────────────
# kyth-safe-upgrade applies quarantine/ring policy before bootc stages an image;
# channel switching goes through a fixed-operation wrapper. A reboot is always
# required to activate either operation. fwupdmgr operations are similarly safe
# (refresh = metadata fetch; get-updates/update = firmware staging).
# Allowing these without a password lets KythOS update flows run without a
# mid-stream sudo prompt that breaks the terminal flow.
# The 0440 mode (owner+group read, no write) is required by sudo's NOPASSWD check.
install -m 0440 /dev/stdin /etc/sudoers.d/kyth-upgrade <<'SUDOEOF'
# KythOS: wheel group may run safe update/firmware commands without a password.
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-safe-upgrade
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-bootc-guard status
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-bootc-guard switch-latest
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-bootc-guard switch-testing
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-bootc-guard switch-latest-cachy
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-bootc-guard switch-testing-cachy
%wheel ALL=(root) NOPASSWD: /usr/bin/fwupdmgr refresh
%wheel ALL=(root) NOPASSWD: /usr/bin/fwupdmgr update
%wheel ALL=(root) NOPASSWD: /usr/bin/fwupdmgr update --assume-yes --no-reboot-check
%wheel ALL=(root) NOPASSWD: /usr/bin/fwupdmgr get-updates
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-set-epp performance
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-set-epp balance_performance
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-set-epp balance_power
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-set-epp power
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-set-epp default
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-rclone-update
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set rusty
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set lavd
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set bpfland
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set flash
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set tickless
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set chaos
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set layered
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set rlfifo
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set scx_rusty
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set scx_lavd
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set scx_bpfland
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set scx_flash
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set scx_tickless
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set scx_chaos
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set scx_layered
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx set scx_rlfifo
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx restart
%wheel ALL=(root) NOPASSWD: /usr/bin/kyth-scx stop
%wheel ALL=(root) NOPASSWD: /usr/bin/systemctl start kyth-flathub-setup.service
%wheel ALL=(root) NOPASSWD: /usr/bin/systemctl start kyth-default-flatpaks.service
%wheel ALL=(root) NOPASSWD: /usr/bin/systemctl restart kyth-default-flatpaks.service
# Rootful Podman/Distrobox operations deliberately require normal sudo
# authentication. Even narrowly named podman subcommands can execute arbitrary
# commands as container root and expose host bind mounts or container secrets.
SUDOEOF
