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

cat >/usr/libexec/kyth-input-remapper-autoload <<'IRAUTOSTARTEOF'
#!/usr/bin/bash
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
install -m 0755 /ctx/sysconfig/kyth-fix-system-accounts /usr/libexec/kyth-fix-system-accounts
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

mkdir -p /etc/systemd/system/dbus-broker.service.d
cat >/etc/systemd/system/dbus-broker.service.d/10-kyth-no-audit.conf <<'DBUSBROKEREOF'
[Service]
ExecStart=
ExecStart=/usr/bin/dbus-broker-launch --scope system
DBUSBROKEREOF
