# shellcheck shell=bash
# ── Print/Scan autopilot (ipp-usb + sane-airscan) ────────────────────────
# The native binary is installed from the hub-web-builder stage in Dockerfile.
# Keep the Python source fixture out of the final image.
# ipp-usb quirks + sane-airscan already via sysconfig; auto_add via print.toml
# stays cups-browsed purged (Avahi ipp everywhere only)
