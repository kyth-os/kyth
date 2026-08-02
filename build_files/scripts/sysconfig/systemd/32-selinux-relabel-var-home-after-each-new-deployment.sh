#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── SELinux: relabel /var/home after each new deployment ──────────────────────
# bootc/ostree relabels the OS tree (/usr, /etc) on every deployment, but /var
# is writable state — it is never touched. On enforcing systems, /var/home
# files with missing labels cause PAM and dbus-broker to be denied, making
# login impossible.
#
# Running restorecon -RF /var/home on every boot adds ~45s to startup. Instead,
# gate it on a per-deployment sentinel: only relabel when the booted deployment
# checksum (from /run/ostree-booted or `ostree admin status`) differs from the
# last one we relabeled for. After first boot of a new deployment, subsequent
# reboots skip it entirely. If a user needs to force a relabel, they can remove
# /var/lib/kyth/selinux-relabel-home.stamp.
write_config /usr/lib/systemd/system/kyth-selinux-relabel-home.service <<'RELABELEOF'
[Unit]
Description=SELinux relabel /var/home (once per deployment)
DefaultDependencies=no
After=local-fs.target
Before=sddm.service
ConditionSecurity=selinux

[Service]
Type=oneshot
ExecStart=/usr/libexec/kyth-selinux-relabel-home
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
RELABELEOF

install -d -m 0755 /usr/libexec
install -m 0755 /ctx/sysconfig/kyth-selinux-relabel-home /usr/libexec/kyth-selinux-relabel-home

systemctl enable kyth-selinux-relabel-home.service 2>/dev/null || true
