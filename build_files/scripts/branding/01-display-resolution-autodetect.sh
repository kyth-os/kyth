# shellcheck shell=bash
# ── Display / resolution auto-detection ──────────────────────────────────────
# First-login autostart: run kscreen-doctor to set all outputs to their
# preferred (auto) mode.  Works for both hardware and VMs.  Removes itself
# so it only fires once per user.
write_config /etc/skel/.config/autostart/kyth-set-resolution.desktop <<'RESEOF'
[Desktop Entry]
Type=Application
Name=KythOS: Set display resolution
Exec=/usr/bin/kyth-set-resolution
X-KDE-autostart-after=panel
Hidden=false
NoDisplay=true
RESEOF

install -m 0755 /ctx/kyth-set-resolution /usr/bin/kyth-set-resolution

write_kyth_os_release() {
	local target=$1
	write_config "${target}" <<'EOF'
NAME="KythOS"
PRETTY_NAME="KythOS 44"
ID=kythos
VERSION="44"
VERSION_ID="44"
ANSI_COLOR="0;34"
LOGO=kyth
HOME_URL="https://github.com/kyth-os/kyth"
SUPPORT_URL="https://github.com/kyth-os/kyth/discussions"
BUG_REPORT_URL="https://github.com/kyth-os/kyth/issues"
EOF
}

write_kyth_os_release /usr/lib/os-release
rm -f /etc/os-release
write_kyth_os_release /etc/os-release
