# shellcheck shell=bash
# ── Print/Scan autopilot (driverless IPP Everywhere via cups + Avahi) ────
# The native binary is installed from the hub-web-builder stage in Dockerfile.
# Keep the Python source fixture out of the final image.
# Printing here is driverless IPP Everywhere over Avahi/mDNS (cups-browsed
# stays purged — it was the 2024 CUPS RCE vector on UDP 631). This fragment
# deliberately does NOT claim ipp-usb / sane-airscan support: neither package
# nor their units ship in this image, so advertising USB-quirks/airscan config
# would promise hardware that cannot work. If those stacks are added later,
# this fragment must grow their real units first.
systemctl enable cups.service 2>/dev/null || true
systemctl enable avahi-daemon.service 2>/dev/null || true
# auto_add via print.toml stays cups-browsed purged (Avahi ipp everywhere only)
