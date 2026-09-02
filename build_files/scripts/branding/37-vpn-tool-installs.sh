# shellcheck shell=bash
# ── VPN connect/status tools ────────────────────────────────────────────────────
# VPN profiles, openconnect, and SAML are owned by the native Tauri Hub.
# Keep only the fixed openconnect helper script used by the Rust command.
install -m 0755 /ctx/kyth-vpnc-script /usr/libexec/kyth-vpnc-script
