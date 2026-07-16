# shellcheck shell=bash
# ── Storage Sense ─────────────────────────────────────────────────────────────
# Automatic housekeeping: empty Recycle Bin items older than 30 days, drop unused
# Flatpak runtimes, vacuum the user journal. Opt-in: the timer ships disabled and
# System Hub -> Health Report has the on/off switch.
cat >/usr/bin/kyth-storage-sense <<'STORAGESENSEEOF'
#!/usr/bin/env bash
# KythOS Storage Sense — enable/disable from System Hub → Health Report.
set -uo pipefail

days=30
info_dir="${HOME}/.local/share/Trash/info"
files_dir="${HOME}/.local/share/Trash/files"
now=$(date +%s)

# Trash entries record their deletion time in .trashinfo (XDG trash spec);
# only entries older than the cutoff are removed, never the whole bin.
if [[ -d "${info_dir}" ]]; then
    for info in "${info_dir}"/*.trashinfo; do
        [[ -e "${info}" ]] || continue
        deleted=$(sed -n 's/^DeletionDate=//p' "${info}" | head -1)
        [[ -n "${deleted}" ]] || continue
        ts=$(date -d "${deleted}" +%s 2>/dev/null) || continue
        if (( now - ts > days * 86400 )); then
            name=$(basename "${info}" .trashinfo)
            rm -rf -- "${files_dir:?}/${name}" "${info}" 2>/dev/null || true
        fi
    done
fi

flatpak uninstall --unused -y --noninteractive >/dev/null 2>&1 || true
journalctl --user --vacuum-time=30d >/dev/null 2>&1 || true
STORAGESENSEEOF
chmod +x /usr/bin/kyth-storage-sense

cat >/usr/lib/systemd/user/kyth-storage-sense.service <<'STORAGESENSESVCEOF'
[Unit]
Description=KythOS Storage Sense cleanup

[Service]
Type=oneshot
ExecStart=/usr/bin/kyth-storage-sense
STORAGESENSESVCEOF

cat >/usr/lib/systemd/user/kyth-storage-sense.timer <<'STORAGESENSETIMEREOF'
[Unit]
Description=Weekly KythOS Storage Sense cleanup

[Timer]
OnCalendar=weekly
Persistent=true
RandomizedDelaySec=1h

[Install]
WantedBy=timers.target
STORAGESENSETIMEREOF

install -m 0755 /ctx/kyth-welcome/kyth-update-notifier /usr/bin/kyth-update-notifier
install -m 0644 /ctx/kyth-welcome/kyth-update-notifier.desktop \
	/usr/share/applications/kyth-update-notifier.desktop
# Autostart the notifier for new user accounts
mkdir -p /etc/skel/.config/autostart
install -m 0644 /ctx/kyth-welcome/kyth-update-notifier.desktop \
	/etc/skel/.config/autostart/kyth-update-notifier.desktop

# User-session confidence checks. These show friendly notifications and are
# version/deployment-gated so they do not nag on every login.
mkdir -p /etc/xdg/autostart
cat >/etc/xdg/autostart/kyth-post-update-check.desktop <<'POSTUPDATEAUTOSTARTEOF'
[Desktop Entry]
Type=Application
Name=KythOS Post-Update Check
Exec=/usr/bin/kyth-post-update-check --no-notify
NoDisplay=true
X-KDE-autostart-after=panel
POSTUPDATEAUTOSTARTEOF

cat >/etc/xdg/autostart/kyth-firstboot-app-status.desktop <<'APPSTATUSAUTOSTARTEOF'
[Desktop Entry]
Type=Application
Name=KythOS App Setup Status
Exec=/usr/bin/kyth-firstboot-app-status
NoDisplay=true
X-KDE-autostart-after=panel
APPSTATUSAUTOSTARTEOF

# Steam Flatpak writes game shortcuts inside its sandbox. Refresh host menu
# exports quietly at login so installed games appear under Games in KDE.
mkdir -p /etc/xdg/autostart
cat >/etc/xdg/autostart/kyth-steam-game-export.desktop <<'STEAMEXPORTAUTOSTARTEOF'
[Desktop Entry]
Type=Application
Name=KythOS Steam Game Menu Export
Exec=/usr/bin/kyth-steam-game-export
NoDisplay=true
X-KDE-autostart-after=panel
STEAMEXPORTAUTOSTARTEOF

# Import-smoke the helper during the build so syntax errors, missing Python
# dependencies, and top-level failures fail the image without running slow
# desktop and hardware probes inside the build container.
python3 -c '
import importlib.machinery, importlib.util, pathlib
path = pathlib.Path("/usr/bin/kyth-welcome")
loader = importlib.machinery.SourceFileLoader("kyth_welcome_smoke", str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)
'

install -m 0755 /ctx/game-performance /usr/bin/game-performance
install -m 0755 /ctx/kyth-gamescope /usr/bin/kyth-gamescope
install -m 0755 /ctx/kyth-performance-mode /usr/bin/kyth-performance-mode
install -m 0755 /ctx/kyth-scx /usr/bin/kyth-scx
install -m 0755 /ctx/kyth-nvme-tuning /usr/bin/kyth-nvme-tuning
install -m 0755 /ctx/zink-run /usr/bin/zink-run
install -m 0755 /ctx/low-latency-run /usr/bin/low-latency-run
install -m 0755 /ctx/kyth-kerver /usr/bin/kyth-kerver
install -m 0755 /ctx/kyth-device-info /usr/bin/kyth-device-info
install -m 0755 /ctx/kyth-smoke-check /usr/bin/kyth-smoke-check
install -m 0755 /ctx/kyth-post-update-check /usr/bin/kyth-post-update-check
install -m 0755 /ctx/kyth-firstboot-app-status /usr/bin/kyth-firstboot-app-status
install -m 0755 /ctx/kyth-controller-check /usr/bin/kyth-controller-check
install -m 0755 /ctx/kyth-resume-check /usr/bin/kyth-resume-check
install -m 0755 /ctx/kyth-nvidia-status /usr/bin/kyth-nvidia-status
install -m 0755 /ctx/kyth-creator-check /usr/bin/kyth-creator-check
install -m 0755 /ctx/kyth-davinci-install /usr/bin/kyth-davinci-install
install -m 0755 /ctx/kyth-widevine-install /usr/bin/kyth-widevine-install
install -m 0755 /ctx/kyth-duperemove /usr/bin/kyth-duperemove
install -m 0755 /ctx/kyth-distrobox-root-launch /usr/bin/kyth-distrobox-root-launch
install -m 0755 /ctx/kyth-local-bin-migrate /usr/bin/kyth-local-bin-migrate
install -m 0755 /ctx/kyth-nearby-share /usr/bin/kyth-nearby-share
install -m 0755 /ctx/kyth-setup-transfer /usr/bin/kyth-setup-transfer
install -m 0755 /ctx/kyth-dynamic-lock /usr/bin/kyth-dynamic-lock
install -m 0644 /ctx/kyth-duperemove.service /usr/lib/systemd/system/kyth-duperemove.service
install -m 0644 /ctx/kyth-duperemove.timer /usr/lib/systemd/system/kyth-duperemove.timer
install -m 0644 /ctx/kyth-local-bin-migrate.service /usr/lib/systemd/system/kyth-local-bin-migrate.service
install -m 0755 /ctx/kyth-topgrade-migrate /usr/bin/kyth-topgrade-migrate
install -m 0755 /ctx/kyth-vscode-wallet /usr/bin/kyth-vscode-wallet
mkdir -p /usr/lib/systemd/user /usr/lib/systemd/user/default.target.wants
install -m 0644 /ctx/kyth-dynamic-lock.service /usr/lib/systemd/user/kyth-dynamic-lock.service
cat >/usr/lib/systemd/user/kyth-browser-wallet-defaults.service <<'WALLETDEFAULTSEOF'
[Unit]
Description=Apply quiet VS Code and Brave wallet defaults
ConditionPathExists=!%h/.local/state/kyth/browser-wallet-defaults-v1

[Service]
Type=oneshot
ExecStart=/usr/bin/bash -c 'set -euo pipefail; /usr/bin/kyth-vscode-wallet; mkdir -p "${HOME}/.local/state/kyth"; touch "${HOME}/.local/state/kyth/browser-wallet-defaults-v1"'

[Install]
WantedBy=default.target
WALLETDEFAULTSEOF
ln -sf ../kyth-browser-wallet-defaults.service \
	/usr/lib/systemd/user/default.target.wants/kyth-browser-wallet-defaults.service
install -m 0644 /ctx/kyth-topgrade-migrate.service /usr/lib/systemd/system/kyth-topgrade-migrate.service
install -m 0755 /ctx/kyth-vpn-connect/kyth-vpn-connect /usr/bin/kyth-vpn-connect
install -m 0644 /ctx/kyth-vpn-connect/kyth-vpn-connect.desktop \
	/usr/share/applications/kyth-vpn-connect.desktop
install -m 0755 /ctx/kyth-vpnc-script /usr/libexec/kyth-vpnc-script
install -m 0755 /ctx/kyth-vpn-status/kyth-vpn-status /usr/bin/kyth-vpn-status
