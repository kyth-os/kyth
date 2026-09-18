#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── Bluetooth — enable adapter on boot unless the user blocked it ─────────────
# BlueZ ships with AutoEnable commented out (value is 'false' in modern versions).
# Ensure exactly one AutoEnable=true inside the [Policy] section, idempotently:
# never duplicate the section, never touch other sections, and drop stray
# AutoEnable lines that a previous run may have left outside [Policy].
# AutoEnable handles newly-seen controllers, while kyth-bluetooth-enable.service
# corrects persisted rfkill / controller power state on boot — but only when no
# explicit user block exists (see the unit's ExecCondition below).
mkdir -p /etc/bluetooth
touch /etc/bluetooth/main.conf
BT_CONF=/etc/bluetooth/main.conf
BT_TMP="$(mktemp)"
awk '
    /^\[.*\]/ {
        if (in_policy && !wrote) { print "AutoEnable=true"; wrote = 1 }
        in_policy = ($0 == "[Policy]")
        if (seen_policy && $0 == "[Policy]") { skip_section = 1 } else { skip_section = 0 }
        if ($0 == "[Policy]") { seen_policy = 1 }
        if (!skip_section) { print }
        next
    }
    skip_section { next }
    /^[#[:space:]]*AutoEnable[[:space:]]*=/ {
        if (in_policy && !wrote) { print "AutoEnable=true"; wrote = 1 }
        next
    }
    { print }
    END {
        if (!seen_policy) { print ""; print "[Policy]"; print "AutoEnable=true" }
        else if (in_policy && !wrote) { print "AutoEnable=true" }
    }
' "${BT_CONF}" >"${BT_TMP}"
cat "${BT_TMP}" >"${BT_CONF}"
rm -f "${BT_TMP}"

# NOTE: no udev RUN+="rfkill unblock" rule here on purpose. Unblocking on every
# adapter add event also undoes an explicit user block (rfkill block bluetooth),
# which systemd-rfkill.service faithfully restores at boot. BlueZ AutoEnable
# already powers newly-seen controllers; the boot service below covers
# persisted power state. A blanket unblock rule would fight them both.
rm -f /etc/udev/rules.d/69-kyth-bluetooth.rules

install -d -m 0755 /usr/libexec
# kyth-enable-bluetooth is a native binary (COPY layer); the retained shell
# source stays in the tree only as a rollback fixture.

write_config /usr/lib/systemd/system/kyth-bluetooth-enable.service <<'BTENABLEUNITEOF'
[Unit]
Description=Enable Bluetooth adapters at boot (unless user-blocked)
Documentation=https://github.com/kyth-os/kyth
After=bluetooth.service systemd-rfkill.service
Wants=bluetooth.service

[Service]
Type=oneshot
# Skip entirely when the user explicitly soft-blocked bluetooth: systemd-rfkill
# restores that block into the kernel before this unit runs. Without this guard
# the binary would delete the persisted state and power the radio back on
# against the user's choice. Missing rfkill/no adapter = run (best-effort).
ExecCondition=/bin/sh -c 'command -v rfkill >/dev/null 2>&1 || exit 0; ! rfkill list bluetooth 2>/dev/null | grep -q "Soft blocked: yes"'
ExecStart=/usr/libexec/kyth-enable-bluetooth
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
BTENABLEUNITEOF

systemctl enable bluetooth.service 2>/dev/null || true
systemctl enable kyth-bluetooth-enable.service 2>/dev/null || true
systemctl enable avahi-daemon.service 2>/dev/null || true
