# shellcheck shell=bash
# ── Misc maintenance/utility tools ─────────────────────────────────────────────
install -m 0755 /ctx/kyth-davinci-install /usr/bin/kyth-davinci-install
install -m 0755 /ctx/kyth-widevine-install /usr/bin/kyth-widevine-install
install -m 0755 /ctx/kyth-duperemove /usr/bin/kyth-duperemove
install -m 0755 /ctx/kyth-distrobox-root-launch /usr/bin/kyth-distrobox-root-launch
install -m 0755 /ctx/kyth-local-bin-migrate /usr/bin/kyth-local-bin-migrate
install -m 0755 /ctx/kyth-nearby-share /usr/bin/kyth-nearby-share
install -m 0755 /ctx/kyth-setup-transfer /usr/bin/kyth-setup-transfer
install -m 0755 /ctx/kyth-dynamic-lock /usr/bin/kyth-dynamic-lock
# kyth-duperemove.service/.timer and kyth-local-bin-migrate.service are
# installed in branding/31-ujust-recipes.sh instead, right before the
# `systemctl enable` calls that need them to already exist.
install -m 0755 /ctx/kyth-full-update /usr/bin/kyth-full-update
install -m 0755 /ctx/kyth-scx-loader /usr/bin/scx_loader
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
