#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── WiFi power management — on by default, off on AC or while gaming ──────────
# Blanket powersave=off trades battery for latency on every machine, including
# laptops on battery where the radio is the biggest idle drain. Default to
# powersave on (3); the dispatcher below turns the radio's power_save off while
# on AC power or while a game runs, and back on otherwise.
write_config /etc/NetworkManager/conf.d/wifi-powersave-off.conf <<'NMEOF'
[connection]
# 3 = enable powersave (battery-friendly default). Scoped off on AC / gaming
# by 99-kyth-wifi-powersave (dispatcher.d) — do not force 2 here.
wifi.powersave = 3
NMEOF

# ── WiFi MAC privacy + connectivity pin ────────────────────────────────────
# Stable per-network randomized MACs (not the permanent hardware address, not
# a rotating one that breaks captive-portal/MAC-allowlist reauth):
# wifi.cloned-mac-address=stable + ipv6.addr-gen-mode=stable-privacy. An
# explicit operator override (/etc/kyth/wifi-mac.conf with
# KYTH_WIFI_MAC=permanent|random) still wins via the dispatcher below.
write_config /etc/NetworkManager/conf.d/wifi-mac-privacy.conf <<'NMEOF'
[device]
wifi.scan-rand-mac-address=yes

[connection]
wifi.cloned-mac-address=stable
ethernet.cloned-mac-address=stable
ipv6.addr-gen-mode=stable-privacy
NMEOF

# Pin the connectivity-check URI so NM upgrades cannot silently move it.
# Fedora default, written explicitly: hotspot.txt with a 300 s interval.
write_config /etc/NetworkManager/conf.d/connectivity-pinned.conf <<'NMEOF'
[connectivity]
uri=http://fedoraproject.org/static/hotspot.txt
interval=300
NMEOF

write_config /etc/NetworkManager/dispatcher.d/99-kyth-wifi-powersave 0755 <<'NMPSEOF'
#!/usr/bin/env bash
# kyth wifi powersave scope: power_save off on AC or while gaming, on otherwise.
set -u

iface="${1:-${DEVICE_IFACE:-}}"
action="${2:-${NM_DISPATCHER_ACTION:-}}"
case "${action}" in
    up|connectivity-change) ;;
    *) exit 0 ;;
esac
[[ -n "${iface}" ]] || exit 0
command -v iw >/dev/null 2>&1 || exit 0
[[ -d "/sys/class/net/${iface}/wireless" || -d "/sys/class/net/${iface}/phy80211" ]] || exit 0

# Explicit operator override wins: /etc/kyth/wifi-powersave.conf with
# KYTH_WIFI_POWERSAVE=off|on.
if [[ -f /etc/kyth/wifi-powersave.conf ]]; then
    # shellcheck disable=SC1091
    source /etc/kyth/wifi-powersave.conf
    case "${KYTH_WIFI_POWERSAVE:-}" in
        off) iw dev "${iface}" set power_save off >/dev/null 2>&1 || true; exit 0 ;;
        on) iw dev "${iface}" set power_save on >/dev/null 2>&1 || true; exit 0 ;;
    esac
fi

# Gaming opts out of powersave: kyth-game-launch marks /run/kyth/gaming-hint.
if [[ -f /run/kyth/gaming-hint ]]; then
    iw dev "${iface}" set power_save off >/dev/null 2>&1 || true
    exit 0
fi

# On AC power the latency win is free; on battery keep the radio throttled.
on_ac=1
for psu in /sys/class/power_supply/AC* /sys/class/power_supply/ADP*; do
    [[ -f "${psu}/online" ]] || continue
    [[ "$(cat "${psu}/online" 2>/dev/null)" == "1" ]] || on_ac=0
done
if [[ "${on_ac}" -eq 1 ]]; then
    iw dev "${iface}" set power_save off >/dev/null 2>&1 || true
else
    iw dev "${iface}" set power_save on >/dev/null 2>&1 || true
fi
NMPSEOF

write_config /etc/NetworkManager/dispatcher.d/90-kyth-prefer-last-wifi 0755 <<'NMDISPEOF'
#!/usr/bin/env bash
# Prefer the just-connected wifi network by raising its autoconnect priority.
# Never touches other profiles: disabling their autoconnect stranded users
# whose remembered home/work networks stopped reconnecting after one travel SSID.
# The boost is CAPPED at +10 and never lowers an existing higher priority:
# an uncapped 100 permanently outranked every manually-prioritized network
# (office > home) after one travel connection.
# Explicit operator override wins: /etc/kyth/wifi-mac.conf with
# KYTH_WIFI_MAC=permanent|random forces that cloned-mac-address instead.
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

if [[ -f /etc/kyth/wifi-mac.conf ]]; then
    # shellcheck disable=SC1091
    source /etc/kyth/wifi-mac.conf
    case "${KYTH_WIFI_MAC:-}" in
        permanent|random)
            nmcli connection modify "${uuid}" \
                wifi.cloned-mac-address "${KYTH_WIFI_MAC}" >/dev/null 2>&1 || true
            ;;
    esac
fi

current="$(nmcli -g connection.autoconnect-priority connection show "${uuid}" 2>/dev/null || echo 0)"
[[ "${current}" =~ ^-?[0-9]+$ ]] || current=0
if [[ "${current}" -lt 10 ]]; then
    nmcli connection modify "${uuid}" \
        connection.autoconnect yes \
        connection.autoconnect-priority 10 >/dev/null 2>&1 || exit 0
fi
NMDISPEOF

install -d -m 0755 /usr/libexec
# kyth-network-fallback is a native binary (COPY layer); the retained shell
# source stays in the tree only as a rollback fixture.

write_config /etc/xdg/autostart/kyth-network-fallback.desktop <<'NETFALLBACKDESKTOPEOF'
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

write_config /etc/NetworkManager/dispatcher.d/80-kyth-wired-or-wireless 0755 <<'NMWIREDEOF'
#!/usr/bin/env bash
# Keep the legacy dispatcher installed as a no-op so systems upgrading from
# older KythOS releases stop persisting NetworkManager's Wi-Fi radio as off.
# Ethernet and Wi-Fi can remain active together; users control the radio.
exit 0
NMWIREDEOF
