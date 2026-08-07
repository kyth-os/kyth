# shellcheck shell=bash
# ── Print/Scan autopilot (ipp-usb + sane-airscan) ────────────────────────
install -m 0755 /ctx/kyth-print-check /usr/bin/kyth-print-check
# ipp-usb quirks + sane-airscan already via sysconfig; auto_add via print.toml
# stays cups-browsed purged (Avahi ipp everywhere only)
