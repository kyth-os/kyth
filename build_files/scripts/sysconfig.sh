#!/bin/bash
# Runtime-only post-upgrade wiring for KythOS.
# Static OS configuration is written by sysconfig-static.sh so those files are not
# overwritten after the static build layer has applied network hardening.

set -euo pipefail

# Install optional helpers when provided by build context.
if [[ -f /ctx/kyth-ai-dev ]]; then
	install -Dm0755 /ctx/kyth-ai-dev /usr/bin/kyth-ai-dev
fi

if [[ -f /ctx/kyth-game-boost ]]; then
	install -Dm0755 /ctx/kyth-game-boost /usr/bin/kyth-game-boost
	ln -sf /usr/bin/kyth-game-boost /usr/bin/game-performance
fi

if [[ -f /ctx/kyth-ntfs-repair ]]; then
	install -Dm0755 /ctx/kyth-ntfs-repair /usr/bin/kyth-ntfs-repair
fi

if [[ -f /ctx/kyth-shader-preheat ]]; then
	install -Dm0755 /ctx/kyth-shader-preheat /usr/bin/kyth-shader-preheat
fi

if [[ -f /ctx/kyth-health-check ]]; then
	install -Dm0755 /ctx/kyth-health-check /usr/bin/kyth-health-check
fi

# Repair accounts/groups that may be missing after layering package changes.
if [[ -x /usr/libexec/kyth-fix-system-accounts ]]; then
	/usr/libexec/kyth-fix-system-accounts || true
fi

for group in docker plugdev polkitd; do
	if ! grep -q "^${group}:" /etc/group && grep -q "^${group}:" /usr/lib/group; then
		grep "^${group}:" /usr/lib/group >>/etc/group
	fi
done

# Keep the display manager and graphical target explicit across upgrades.
mkdir -p /etc/systemd/system/graphical.target.wants
ln -sf /usr/lib/systemd/system/sddm.service /etc/systemd/system/display-manager.service
ln -sf /etc/systemd/system/display-manager.service /etc/systemd/system/graphical.target.wants/display-manager.service
ln -sf /usr/lib/systemd/system/graphical.target /etc/systemd/system/default.target

# Service masks/disables that are intentionally runtime-layer policy.
# NetworkManager-wait-online.service is deliberately NOT disabled here — it is
# enabled later in branding/31-ujust-recipes.sh (which runs after this script
# in the Dockerfile) so kyth-flathub-setup/kyth-default-flatpaks don't race DNS
# at boot. Do not re-add a disable for it here; the two would silently fight
# over the same unit depending on layer order.
systemctl mask systemd-remount-fs.service
systemctl disable packagekit.service 2>/dev/null || true
systemctl disable rpm-ostree-countme.timer 2>/dev/null || true
systemctl disable fedora-atomic-desktop-appstream-cache-refresh.service 2>/dev/null || true
systemctl disable serial-getty@ttyS0.service 2>/dev/null || true

mkdir -p /etc/systemd/user
ln -sf /dev/null /etc/systemd/user/plasma-discover-notifier.service

# Runtime services that should be enabled on the installed system.
systemctl enable rtkit-daemon.service 2>/dev/null || true
systemctl enable input-remapper.service 2>/dev/null || true
systemctl enable joycond.service 2>/dev/null || true
systemctl enable bluetooth.service 2>/dev/null || true
systemctl enable kyth-bluetooth-enable.service 2>/dev/null || true
systemctl enable cups-browsed.service 2>/dev/null || true
