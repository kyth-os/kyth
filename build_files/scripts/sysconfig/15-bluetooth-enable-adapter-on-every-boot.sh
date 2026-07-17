#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Bluetooth — enable adapter on every boot ────────────────────────────────
# BlueZ ships with AutoEnable commented out (value is 'false' in modern versions).
# Replace any commented AutoEnable line with the enabled form; append to [Policy]
# if the line is missing entirely. AutoEnable handles newly-seen controllers, while
# kyth-bluetooth-enable.service corrects persisted rfkill / controller power state
# on every boot.
mkdir -p /etc/bluetooth
touch /etc/bluetooth/main.conf
sed -i -E 's/^[#[:space:]]*AutoEnable=.*/AutoEnable=true/' /etc/bluetooth/main.conf
grep -q '^AutoEnable=' /etc/bluetooth/main.conf ||
	printf '\n[Policy]\nAutoEnable=true\n' >>/etc/bluetooth/main.conf

# Udev rule: unblock Bluetooth the moment any rfkill device of type bluetooth
# appears. This covers HP WMI and other drivers (common on HP ZBook) that expose
# their rfkill device asynchronously — AFTER kyth-bluetooth-enable.service has
# already run at boot. Without this rule those adapters boot soft-blocked and
# nothing subsequently unblocks them until the user toggles Bluetooth manually.
mkdir -p /etc/udev/rules.d
cat >/etc/udev/rules.d/69-kyth-bluetooth.rules <<'BTUDEVEOF'
# Unblock Bluetooth immediately when any rfkill bluetooth device appears.
# Handles HP WMI and similar drivers that load their rfkill entry after the
# kyth-bluetooth-enable systemd service has already executed.
#
# Use %s{index} (the numeric rfkill index) rather than the type-wide
# "rfkill unblock bluetooth" to send RFKILL_OP_CHANGE to only this device.
# This avoids triggering shared-rfkill hardware (e.g. HP WMI combined
# wireless kill-switch) which would also unblock Wi-Fi and cause NM to
# re-enable Wi-Fi even if the user had intentionally turned it off.
ACTION=="add", SUBSYSTEM=="rfkill", ATTR{type}=="bluetooth", RUN+="/usr/sbin/rfkill unblock %s{index}"
BTUDEVEOF

cat >/usr/libexec/kyth-enable-bluetooth <<'BTENABLEEOF'
#!/usr/bin/bash
set -uo pipefail

# Clear any saved soft-block state that systemd-rfkill would restore on the
# next boot.  The files are named after the rfkill index (e.g. "platform-xxx:bluetooth").
# Removing them prevents systemd-rfkill from overriding our unblock on next boot.
find /var/lib/systemd/rfkill -name "*bluetooth*" -delete 2>/dev/null || true

# Snapshot Wi-Fi software state before unblocking Bluetooth. On systems with a
# shared hardware kill-switch (e.g. HP WMI), rfkill unblock bluetooth can also
# clear the Wi-Fi hard-block, which causes NetworkManager to re-enable Wi-Fi
# even if the user had intentionally disabled it last session.
_wifi_was_soft_blocked=0
if rfkill list wifi 2>/dev/null | grep -q 'Soft blocked: yes'; then
    _wifi_was_soft_blocked=1
fi

if command -v rfkill >/dev/null 2>&1; then
    rfkill unblock bluetooth >/dev/null 2>&1 || true
fi

# Restore Wi-Fi soft-block if it was user-disabled before we ran.
if [[ "${_wifi_was_soft_blocked}" -eq 1 ]]; then
    rfkill block wifi >/dev/null 2>&1 || true
fi

if command -v bluetoothctl >/dev/null 2>&1; then
    bluetoothctl power on >/dev/null 2>&1 || true
fi

exit 0
BTENABLEEOF
chmod 0755 /usr/libexec/kyth-enable-bluetooth

cat >/usr/lib/systemd/system/kyth-bluetooth-enable.service <<'BTENABLEUNITEOF'
[Unit]
Description=Enable Bluetooth adapters at boot
Documentation=https://github.com/mrtrick37/kyth
# Run after systemd-rfkill has restored saved state so we can override it.
After=bluetooth.service systemd-rfkill.service
Wants=bluetooth.service

[Service]
Type=oneshot
ExecStart=/usr/libexec/kyth-enable-bluetooth
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
BTENABLEUNITEOF

systemctl enable bluetooth.service 2>/dev/null || true
systemctl enable kyth-bluetooth-enable.service 2>/dev/null || true
systemctl enable cups-browsed.service 2>/dev/null || true
systemctl enable avahi-daemon.service 2>/dev/null || true
# input-remapper.service is enabled later in this script alongside rtkit-daemon
