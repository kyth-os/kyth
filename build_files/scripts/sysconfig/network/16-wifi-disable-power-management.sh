#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── WiFi — disable power management ──────────────────────────────────────────
# Linux WiFi power-save throttles the radio when idle, reducing signal
# sensitivity and causing apparent "weak signal" even close to the AP.
# NetworkManager powersave=2 disables it at the connection level (all adapters).
mkdir -p /etc/NetworkManager/conf.d
cat >/etc/NetworkManager/conf.d/wifi-powersave-off.conf <<'NMEOF'
[connection]
wifi.powersave = 2
NMEOF

mkdir -p /etc/NetworkManager/dispatcher.d
cat >/etc/NetworkManager/dispatcher.d/90-kyth-prefer-last-wifi <<'NMDISPEOF'
#!/usr/bin/env bash
set -u

action="${2:-${NM_DISPATCHER_ACTION:-}}"
case "${action}" in
    up) ;;
    *) exit 0 ;;
esac

command -v nmcli >/dev/null 2>&1 || exit 0

uuid="${CONNECTION_UUID:-}"
[[ -n "${uuid}" ]] || exit 0

type="$(nmcli -g connection.type connection show "${uuid}" 2>/dev/null || true)"
case "${type}" in
    802-11-wireless|wifi) ;;
    *) exit 0 ;;
esac

nmcli connection modify "${uuid}" \
    connection.autoconnect yes \
    connection.autoconnect-priority 100 >/dev/null 2>&1 || exit 0

while IFS=: read -r other_uuid other_type; do
    [[ -n "${other_uuid}" && "${other_uuid}" != "${uuid}" ]] || continue
    case "${other_type}" in
        802-11-wireless|wifi) ;;
        *) continue ;;
    esac

    autoconnect="$(nmcli -g connection.autoconnect connection show "${other_uuid}" 2>/dev/null || true)"
    [[ "${autoconnect}" == "yes" ]] || continue
    nmcli connection modify "${other_uuid}" connection.autoconnect no >/dev/null 2>&1 || true
done < <(nmcli -t -f UUID,TYPE connection show 2>/dev/null || true)
NMDISPEOF
chmod 0755 /etc/NetworkManager/dispatcher.d/90-kyth-prefer-last-wifi

install -d -m 0755 /usr/libexec
install -m 0755 /ctx/sysconfig/kyth-network-fallback /usr/libexec/kyth-network-fallback

mkdir -p /etc/xdg/autostart
cat >/etc/xdg/autostart/kyth-network-fallback.desktop <<'NETFALLBACKDESKTOPEOF'
[Desktop Entry]
Type=Application
Name=Kyth Network Fallback
Comment=Opens the network picker when no remembered network is available
Exec=/usr/libexec/kyth-network-fallback
Icon=network-wireless
OnlyShowIn=KDE;
X-KDE-autostart-after=panel
NoDisplay=true
NETFALLBACKDESKTOPEOF

cat >/etc/NetworkManager/dispatcher.d/80-kyth-wired-or-wireless <<'NMWIREDEOF'
#!/usr/bin/env bash
set -u

iface="${1:-${DEVICE_IFACE:-}}"
action="${2:-${NM_DISPATCHER_ACTION:-}}"
case "${action}" in
    up|down) ;;
    *) exit 0 ;;
esac

command -v nmcli >/dev/null 2>&1 || exit 0

uuid="${CONNECTION_UUID:-}"
[[ -n "${uuid}" ]] || exit 0

type="$(nmcli -g connection.type connection show "${uuid}" 2>/dev/null || true)"
[[ "${type}" == "802-3-ethernet" ]] || exit 0

stamp=/var/lib/kyth/wifi-off-for-wired

other_ethernet_active() {
    nmcli -t -f DEVICE,TYPE,STATE device status 2>/dev/null |
        awk -F: -v skip="${iface}" \
            '$1 != skip && $2 == "ethernet" && $3 == "connected" { found = 1 } END { exit !found }'
}

case "${action}" in
    up)
        if [[ "$(nmcli -g WIFI radio 2>/dev/null)" == "enabled" ]]; then
            mkdir -p /var/lib/kyth
            : >"${stamp}"
            nmcli radio wifi off >/dev/null 2>&1 || true
        fi
        ;;
    down)
        if [[ -e "${stamp}" ]] && ! other_ethernet_active; then
            rm -f "${stamp}"
            nmcli radio wifi on >/dev/null 2>&1 || true
        fi
        ;;
esac

exit 0
NMWIREDEOF
chmod 0755 /etc/NetworkManager/dispatcher.d/80-kyth-wired-or-wireless
