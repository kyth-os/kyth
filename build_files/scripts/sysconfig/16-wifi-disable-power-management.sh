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

# Reconnect only to the last Wi-Fi network that connected successfully. Merely
# raising autoconnect-priority is not enough: when the last network is out of
# range NetworkManager silently activates the next known profile, and when
# several known networks overlap it may still pick the wrong one — the user
# then has to disconnect and reconnect by hand after every reboot. So on each
# successful Wi-Fi activation this dispatcher makes that profile the *only*
# autoconnect candidate and disables autoconnect on every other Wi-Fi profile.
# Boot therefore either restores the last network or connects to nothing, in
# which case kyth-network-fallback (below) shows the network picker at login.
# Manually connecting to any network makes it the new remembered one — that is
# also why the connected profile gets autoconnect forced back to "yes" here.
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

# Login-time fallback for the dispatcher above: if the remembered network is
# not in range the machine boots with no connection at all (other profiles
# have autoconnect disabled on purpose). Rather than leave the user staring at
# an offline desktop, wait for NetworkManager to settle and, if a Wi-Fi
# adapter is present with the radio on but nothing connected, open the Plasma
# network applet as a window so a network can be picked in one click.
install -d -m 0755 /usr/libexec
cat >/usr/libexec/kyth-network-fallback <<'NETFALLBACKEOF'
#!/usr/bin/env bash
set -u

command -v nmcli >/dev/null 2>&1 || exit 0

# Only meaningful on machines with a Wi-Fi adapter.
nmcli -t -f TYPE device status 2>/dev/null | grep -qx wifi || exit 0

# Give NetworkManager up to ~45 s to autoconnect; leave quietly the moment a
# real (wired or wireless) connection is up. Loopback reports "connected
# (externally)" so only exact ethernet/wifi "connected" states count.
connected() {
    nmcli -t -f TYPE,STATE device status 2>/dev/null |
        awk -F: '($1 == "ethernet" || $1 == "wifi") && $2 == "connected" { found = 1 } END { exit !found }'
}
connecting() {
    nmcli -t -f TYPE,STATE device status 2>/dev/null |
        awk -F: '$2 ~ /^connecting/ { found = 1 } END { exit !found }'
}

for ((i = 0; i < 22; i++)); do
    connected && exit 0
    sleep 2
done

# An activation still in flight means NetworkManager has a candidate; do not
# pop a picker over an attempt that is about to succeed.
connecting && exit 0

# Radio deliberately off (rfkill / user toggle / wired-wins dispatcher) — do
# not nag.
[[ "$(nmcli -g WIFI radio 2>/dev/null)" == "enabled" ]] || exit 0

if command -v plasmawindowed >/dev/null 2>&1; then
    exec plasmawindowed org.kde.plasma.networkmanagement
elif command -v kcmshell6 >/dev/null 2>&1; then
    exec kcmshell6 kcm_networkmanagement
fi
exit 0
NETFALLBACKEOF
chmod 0755 /usr/libexec/kyth-network-fallback

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

# Wired wins: turn the Wi-Fi radio off while any wired connection is active,
# and back on when the last one goes away. Without this NetworkManager
# activates every device with an autoconnect profile, so a docked laptop
# associates to Wi-Fi (DHCP lease, radio airtime) even though all traffic
# uses the wire. The stamp file records that *we* disabled the radio, so we
# never surprise-enable Wi-Fi the user had turned off themselves; it lives in
# /var/lib so a reboot while docked still restores Wi-Fi on later undock.
# Known trade-off: plugging in ethernet stops a running Wi-Fi hotspot.
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

# True if any ethernet device other than the one this event is about is
# still activated (multi-NIC / dock plus built-in port).
other_ethernet_active() {
    nmcli -t -f DEVICE,TYPE,STATE device status 2>/dev/null |
        awk -F: -v skip="${iface}" \
            '$1 != skip && $2 == "ethernet" && $3 == "connected" { found = 1 } END { exit !found }'
}

case "${action}" in
    up)
        # Only stamp when the radio was on — if the user already had Wi-Fi
        # off, leave it off after the wire goes away too.
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

