#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── WiFi driver tweaks ───────────────────────────────────────────────────────
write_config /etc/modprobe.d/cfg80211-kyth.conf <<'CFG80211EOF'
options cfg80211 ieee80211_regdom=US
CFG80211EOF

# MT7921/MT7925 PCIe (MediaTek Filogic): disable Active State Power Management.
# ASPM puts the PCIe device into a low-power state it may not reliably wake
# from, causing sudden disconnects, intermittent scan results, and sometimes
# requiring a driver reload or reboot. mt7925e (Wi-Fi 7 parts, e.g. HP ZBook)
# is a separate module from mt7921e and needs its own options line.
write_config /etc/modprobe.d/mt7921-kyth.conf <<'MT76EOF'
options mt7921e disable_aspm=1
options mt7925e disable_aspm=1
MT76EOF

# iwlwifi/iwlmvm (Intel Wi-Fi): keep the radio in CAM/active mode and disable
# U-APSD. Several Intel AX-class adapters, including HP EliteBook CNVio parts,
# can scan successfully but fail or stall during WPA association when firmware
# power-save enters the handshake. Keep Bluetooth coexistence enabled; it is
# the safer default for mixed 2.4 GHz Wi-Fi plus Bluetooth office environments.
write_config /etc/modprobe.d/iwlwifi-kyth.conf <<'IWLEOF'
options iwlwifi power_save=0 uapsd_disable=3 bt_coex_active=1
IWLEOF

write_config /etc/modprobe.d/iwlmvm-kyth.conf <<'IWLMVMEOF'
options iwlmvm power_scheme=1
IWLMVMEOF

# btusb (USB Bluetooth, incl. MediaTek MT7922/MT7925 combo radios): disable
# USB autosuspend. The CachyOS kernel builds btusb with autosuspend enabled,
# which suspends the adapter after 2 s idle. USB remote wakeup is unreliable
# on these parts, so a suspended adapter misses traffic from low-bandwidth BLE
# peripherals — mice silently drop every few minutes and only reconnect on
# user input, and reconnect after boot/login is slow for the same reason.
write_config /etc/modprobe.d/btusb-kyth.conf <<'BTUSBEOF'
options btusb enable_autosuspend=0
BTUSBEOF
