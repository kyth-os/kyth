#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

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

write_config /etc/udev/rules.d/69-kyth-bluetooth.rules <<'BTUDEVEOF'
ACTION=="add", SUBSYSTEM=="rfkill", ATTR{type}=="bluetooth", RUN+="/usr/sbin/rfkill unblock %s{index}"
BTUDEVEOF

install -d -m 0755 /usr/libexec
install -m 0755 /ctx/sysconfig/kyth-enable-bluetooth /usr/libexec/kyth-enable-bluetooth

write_config /usr/lib/systemd/system/kyth-bluetooth-enable.service <<'BTENABLEUNITEOF'
[Unit]
Description=Enable Bluetooth adapters at boot
Documentation=https://github.com/kyth-os/kyth
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
systemctl enable avahi-daemon.service 2>/dev/null || true
