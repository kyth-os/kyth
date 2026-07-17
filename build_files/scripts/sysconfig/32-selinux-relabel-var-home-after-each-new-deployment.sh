#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

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
cat >/usr/lib/systemd/system/kyth-selinux-relabel-home.service <<'RELABELEOF'
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
cat >/usr/libexec/kyth-selinux-relabel-home <<'SCRIPTEOF'
#!/usr/bin/bash
# Relabel /var/home only once per ostree/bootc deployment.
# Keyed on the booted deployment checksum so a fresh deployment triggers one
# relabel, then all subsequent reboots of the same deployment skip it.
set -euo pipefail

STAMP_DIR=/var/lib/kyth
STAMP_FILE="${STAMP_DIR}/selinux-relabel-home.stamp"

# Derive a stable deployment identifier. Prefer `ostree admin status --json`
# if available; fall back to parsing the booted checksum from plain output;
# finally fall back to the kernel cmdline ostree= argument.
deployment_id=""
if command -v ostree >/dev/null 2>&1; then
    deployment_id="$(ostree admin status 2>/dev/null \
        | awk '/^\* /{print $2" "$3; exit}')"
fi
if [ -z "$deployment_id" ] && [ -r /proc/cmdline ]; then
    deployment_id="$(tr ' ' '\n' < /proc/cmdline | grep '^ostree=' || true)"
fi
# Last-resort fingerprint: mtime of the active deployment root.
if [ -z "$deployment_id" ]; then
    deployment_id="fallback-$(stat -c %Y /usr 2>/dev/null || echo 0)"
fi

if [ -r "$STAMP_FILE" ] && [ "$(cat "$STAMP_FILE")" = "$deployment_id" ]; then
    echo "kyth-selinux-relabel-home: already relabeled for this deployment, skipping"
    exit 0
fi

echo "kyth-selinux-relabel-home: relabeling /var/home for deployment ${deployment_id}"
/sbin/restorecon -RF /var/home

mkdir -p "$STAMP_DIR"
printf '%s' "$deployment_id" > "$STAMP_FILE"
SCRIPTEOF
chmod 0755 /usr/libexec/kyth-selinux-relabel-home

systemctl enable kyth-selinux-relabel-home.service 2>/dev/null || true

