#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Autostart log-noise guards ────────────────────────────────────────────────
# nvidia-settings ships an unconditional autostart entry that fails every
# login on AMD-only systems with "ERROR: NVIDIA driver is not loaded".
# Run it only when the NVIDIA kernel module is actually loaded.
install -d -m 0755 /usr/libexec
cat >/usr/libexec/kyth-nvidia-settings-autostart <<'NVAUTOSTARTEOF'
#!/usr/bin/bash
[ -e /sys/module/nvidia ] || exit 0
exec nvidia-settings -l
NVAUTOSTARTEOF
chmod 0755 /usr/libexec/kyth-nvidia-settings-autostart
if [ -f /etc/xdg/autostart/nvidia-settings-user.desktop ]; then
	sed -i 's|^Exec=.*|Exec=/usr/libexec/kyth-nvidia-settings-autostart|' /etc/xdg/autostart/nvidia-settings-user.desktop
fi

# input-remapper-control shells out to `systemd-analyze` without capturing
# stderr, which logs "Bootup is not yet finished" at error priority on every
# login that beats bootup completion. Wait for bootup quietly, then hand off
# to the original autoload command.
cat >/usr/libexec/kyth-input-remapper-autoload <<'IRAUTOSTARTEOF'
#!/usr/bin/bash
# Give up after ~10 min and hand off anyway — autoload has its own wait loop.
for _ in $(seq 1 120); do
	systemd-analyze time >/dev/null 2>&1 && break
	sleep 5
done
input-remapper-control --command stop-all && exec input-remapper-control --command autoload
IRAUTOSTARTEOF
chmod 0755 /usr/libexec/kyth-input-remapper-autoload
if [ -f /etc/xdg/autostart/input-remapper-autoload.desktop ]; then
	sed -i 's|^Exec=.*|Exec=/usr/libexec/kyth-input-remapper-autoload|' /etc/xdg/autostart/input-remapper-autoload.desktop
fi

# bootc/ostree images keep several package-owned system accounts in
# /usr/lib/passwd and /usr/lib/group, while booted installations and useradd
# operate against the mutable /etc databases. If the installed /etc lacks those
# accounts, dbus-broker cannot build its NSS cache and SDDM cannot resolve the
# sddm greeter user, leaving QEMU at a black cursor after X starts.
cat >/usr/lib/systemd/system/kyth-system-accounts.service <<'SYSACCOUNTUNITEOF'
[Unit]
Description=Ensure KythOS system accounts are visible in /etc
DefaultDependencies=no
After=local-fs.target
Before=dbus.socket dbus-broker.service sockets.target sddm.service

[Service]
Type=oneshot
ExecStart=/usr/libexec/kyth-fix-system-accounts
RemainAfterExit=yes

[Install]
WantedBy=sysinit.target
SYSACCOUNTUNITEOF

install -d -m 0755 /usr/libexec
cat >/usr/libexec/kyth-fix-system-accounts <<'SYSACCOUNTSCRIPTEOF'
#!/usr/bin/bash
set -euo pipefail

append_missing_name() {
    local src="$1"
    local dest="$2"
    local name

    [ -r "$src" ] || return 0
    touch "$dest"
    while IFS= read -r line || [ -n "$line" ]; do
        [ -n "$line" ] || continue
        name="${line%%:*}"
        [ -n "$name" ] || continue
        if ! grep -q "^${name}:" "$dest"; then
            printf '%s\n' "$line" >> "$dest"
        fi
    done < "$src"
}

ensure_group_line() {
    local name="$1"
    local line="$2"
    if ! grep -q "^${name}:" /etc/group; then
        printf '%s\n' "$line" >> /etc/group
    fi
}

ensure_passwd_line() {
    local name="$1"
    local line="$2"
    if ! grep -q "^${name}:" /etc/passwd; then
        printf '%s\n' "$line" >> /etc/passwd
    fi
    if [ -e /etc/shadow ] && ! grep -q "^${name}:" /etc/shadow; then
        printf '%s:!*:19700:0:99999:7:::\n' "$name" >> /etc/shadow
    fi
}

append_missing_name /usr/lib/group /etc/group
append_missing_name /usr/lib/passwd /etc/passwd

# SDDM is commonly created by package scriptlets into /etc rather than shipped
# in /usr/lib/passwd, so keep an explicit fallback for installed deployments.
ensure_group_line sddm "sddm:x:959:"
ensure_passwd_line sddm "sddm:x:959:959:SDDM Greeter Account:/var/lib/sddm:/usr/sbin/nologin"

chmod 0644 /etc/passwd /etc/group
if [ -e /etc/shadow ]; then
    chmod 0000 /etc/shadow 2>/dev/null || chmod 0600 /etc/shadow
fi
mkdir -p /var/lib/sddm
chown sddm:sddm /var/lib/sddm 2>/dev/null || true
if command -v restorecon >/dev/null 2>&1; then
    restorecon /etc/passwd /etc/group /etc/shadow /var/lib/sddm 2>/dev/null || true
fi
SYSACCOUNTSCRIPTEOF
chmod 0755 /usr/libexec/kyth-fix-system-accounts
systemctl enable kyth-system-accounts.service 2>/dev/null || true

mkdir -p /etc/asusd

cat >/usr/lib/systemd/system/kyth-dbus-runtime-dir.service <<'DBUSRUNDIREOF'
[Unit]
Description=Create D-Bus runtime directory
DefaultDependencies=no
Before=sockets.target dbus.socket
After=kyth-system-accounts.service local-fs.target
Requires=kyth-system-accounts.service

[Service]
Type=oneshot
ExecStart=/usr/bin/mkdir -p /run/dbus
ExecStart=/usr/bin/chmod 0755 /run/dbus

[Install]
WantedBy=sysinit.target
DBUSRUNDIREOF
systemctl enable kyth-dbus-runtime-dir.service 2>/dev/null || true

# The system bus is foundational for logind, polkit, NetworkManager, and SDDM.
# On local QEMU boots dbus-broker repeatedly failed before the greeter started;
# remove audit integration from broker launch so lack of usable audit plumbing
# cannot take down the desktop.
mkdir -p /etc/systemd/system/dbus-broker.service.d
cat >/etc/systemd/system/dbus-broker.service.d/10-kyth-no-audit.conf <<'DBUSBROKEREOF'
[Service]
ExecStart=
ExecStart=/usr/bin/dbus-broker-launch --scope system
DBUSBROKEREOF
