# shellcheck shell=bash
# ── VPN connect/status tools ────────────────────────────────────────────────────
install -m 0755 /ctx/kyth-vpn-connect/kyth-vpn-connect /usr/bin/kyth-vpn-connect
install -m 0644 /ctx/kyth-vpn-connect/kyth-vpn-connect.desktop \
	/usr/share/applications/kyth-vpn-connect.desktop
install -m 0755 /ctx/kyth-vpnc-script /usr/libexec/kyth-vpnc-script
install -m 0755 /ctx/kyth-vpn-status/kyth-vpn-status /usr/bin/kyth-vpn-status
