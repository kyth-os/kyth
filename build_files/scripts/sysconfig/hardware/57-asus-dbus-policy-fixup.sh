#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── ASUS D-Bus policy fixup ───────────────────────────────────────────────────
# asusctl/supergfxctl are opt-in (ujust install-asus-tools), layered at runtime
# rather than baked into the base image, so their D-Bus policy files don't
# exist yet when this build-time fragment runs. asusd/supergfxd ship policy
# files hardcoded to group="sudo" (an Ubuntu/Pop!_OS convention); Fedora's
# admin group is "wheel", not "sudo", so dbus-broker rejects that policy line
# outright on every boot:
#   Invalid group-name in .../asusd.conf +9: group="sudo"
# Ship a boot-time oneshot that rewrites the policy files if/when they show up
# after a layered install + reboot, mirroring kyth-system-accounts.service's
# "repair after layering" pattern. A no-op on systems without ASUS hardware.
write_config /usr/libexec/kyth-fix-asus-dbus-policy 0755 <<'ASUSDBUSFIXEOF'
#!/usr/bin/bash
set -euo pipefail
for dbus_policy in \
	/usr/share/dbus-1/system.d/asusd.conf \
	/etc/dbus-1/system.d/org.supergfxctl.Daemon.conf; do
	[[ -f "${dbus_policy}" ]] && sed -i 's/group="sudo"/group="wheel"/' "${dbus_policy}"
done
ASUSDBUSFIXEOF

write_config /usr/lib/systemd/system/kyth-asus-dbus-policy-fixup.service <<'ASUSDBUSUNITEOF'
[Unit]
Description=Rewrite asusd/supergfxd D-Bus policy group for Fedora
DefaultDependencies=no
Before=dbus.socket dbus-broker.service sockets.target

[Service]
Type=oneshot
ExecStart=/usr/libexec/kyth-fix-asus-dbus-policy
RemainAfterExit=yes

[Install]
WantedBy=sysinit.target
ASUSDBUSUNITEOF
systemctl enable kyth-asus-dbus-policy-fixup.service 2>/dev/null || true
