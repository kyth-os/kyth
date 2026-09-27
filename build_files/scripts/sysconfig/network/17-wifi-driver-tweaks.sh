#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── WiFi regulatory domain — derived from the system timezone, not hardcoded ──
# A baked-in ieee80211_regdom=US is wrong for every non-US user (wrong channels
# / tx-power). The timezone chosen at install/first-boot is the best offline
# proxy for country: kyth-wifi-regdom maps it to an ISO-3166 code and applies
# it with `iw reg set` before NetworkManager starts. Unknown zones fall back
# to US (the previous behavior) rather than failing closed.
rm -f /etc/modprobe.d/cfg80211-kyth.conf

install -m 0755 /dev/stdin /usr/libexec/kyth-wifi-regdom <<'REGDOMEOF'
#!/bin/bash
# kyth-wifi-regdom — set the wireless regdom from the system timezone.
set -euo pipefail
command -v iw >/dev/null 2>&1 || exit 0

zone="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
if [[ -z "${zone}" && -L /etc/localtime ]]; then
    # /etc/localtime -> ../usr/share/zoneinfo/Area/City
    zone="$(readlink /etc/localtime | sed -n 's#.*/zoneinfo/##p')"
fi

cc="US"
case "${zone}" in
    America/New_York|America/Detroit|America/Chicago|America/Denver|America/Los_Angeles|America/Anchorage|Pacific/Honolulu|US/*) cc="US" ;;
    America/Toronto|America/Vancouver|America/Montreal|America/Halifax|Canada/*) cc="CA" ;;
    America/Mexico_City|America/Cancun|America/Tijuana|Mexico/*) cc="MX" ;;
    America/Sao_Paulo|America/Fortaleza|America/Manaus) cc="BR" ;;
    America/Buenos_Aires) cc="AR" ;;
    America/Santiago) cc="CL" ;;
    America/Bogota) cc="CO" ;;
    America/Lima) cc="PE" ;;
    America/Caracas|America/La_Paz|America/Asuncion|America/Montevideo|America/Guayaquil) cc="VE" ;;
    Europe/London) cc="GB" ;;
    Europe/Dublin) cc="IE" ;;
    Europe/Berlin) cc="DE" ;;
    Europe/Paris) cc="FR" ;;
    Europe/Rome) cc="IT" ;;
    Europe/Madrid) cc="ES" ;;
    Europe/Amsterdam) cc="NL" ;;
    Europe/Brussels) cc="BE" ;;
    Europe/Vienna) cc="AT" ;;
    Europe/Zurich) cc="CH" ;;
    Europe/Warsaw|Europe/Krakow) cc="PL" ;;
    Europe/Prague) cc="CZ" ;;
    Europe/Stockholm) cc="SE" ;;
    Europe/Oslo) cc="NO" ;;
    Europe/Helsinki) cc="FI" ;;
    Europe/Copenhagen) cc="DK" ;;
    Europe/Lisbon) cc="PT" ;;
    Europe/Athens) cc="GR" ;;
    Asia/Tokyo|Asia/Osaka) cc="JP" ;;
    Asia/Seoul) cc="KR" ;;
    Asia/Shanghai|Asia/Beijing|Asia/Chongqing) cc="CN" ;;
    Asia/Hong_Kong) cc="HK" ;;
    Asia/Taipei) cc="TW" ;;
    Asia/Singapore) cc="SG" ;;
    Asia/Kuala_Lumpur) cc="MY" ;;
    Asia/Bangkok) cc="TH" ;;
    Asia/Jakarta) cc="ID" ;;
    Asia/Manila) cc="PH" ;;
    Asia/Kolkata|Asia/Delhi|Asia/Mumbai) cc="IN" ;;
    Asia/Dubai) cc="AE" ;;
    Asia/Riyadh) cc="SA" ;;
    Asia/Tel_Aviv|Asia/Jerusalem) cc="IL" ;;
    Asia/Istanbul|Europe/Istanbul) cc="TR" ;;
    Australia/Sydney|Australia/Melbourne|Australia/Brisbane|Australia/Perth|Australia/*) cc="AU" ;;
    Pacific/Auckland) cc="NZ" ;;
    Africa/Cairo) cc="EG" ;;
    Africa/Johannesburg|Africa/*) cc="ZA" ;;
esac
# Explicit opt-out/override.
if [[ -f /etc/kyth/wifi-regdom.conf ]]; then
    # shellcheck disable=SC1091
    source /etc/kyth/wifi-regdom.conf
    cc="${KYTH_REGDOM:-${cc}}"
fi
if [[ "${cc}" =~ ^[A-Z]{2}$ ]]; then
    iw reg set "${cc}" >/dev/null 2>&1 || true
fi
REGDOMEOF

write_config /usr/lib/systemd/system/kyth-wifi-regdom.service <<'REGDOMEOF2'
[Unit]
Description=Set WiFi regulatory domain from system timezone
Before=NetworkManager.service
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/libexec/kyth-wifi-regdom
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
REGDOMEOF2

systemctl enable kyth-wifi-regdom.service 2>/dev/null || true

# Adapter workarounds are device/driver matched at boot by the hardware policy.
# Keep only the universal regulatory default in the immutable image and remove
# legacy broad overrides during image upgrades.
rm -f \
	/etc/modprobe.d/mt7921-kyth.conf \
	/etc/modprobe.d/iwlwifi-kyth.conf \
	/etc/modprobe.d/iwlmvm-kyth.conf \
	/etc/modprobe.d/btusb-kyth.conf
