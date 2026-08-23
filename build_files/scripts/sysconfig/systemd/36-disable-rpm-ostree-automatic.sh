#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Disable rpm-ostree automatic staging ──────────────────────────────────────
# Kyth stages images through kyth-update-watcher / kyth-safe-upgrade (bootc +
# quarantine). Fedora/ublue also enable rpm-ostreed-automatic with
# AutomaticUpdatePolicy=stage. A manual `rpm-ostree update` (or a second
# automatic pull) then races the same daemon; rpm-ostreed often dies mid-OCI
# chunk fetch and clients see "Bus owner changed, aborting."
systemctl disable --now rpm-ostreed-automatic.timer 2>/dev/null || true
systemctl disable --now rpm-ostreed-automatic.service 2>/dev/null || true

conf=/etc/rpm-ostreed.conf
if [[ -f "${conf}" ]]; then
	if grep -q '^AutomaticUpdatePolicy=' "${conf}"; then
		sed -i 's/^AutomaticUpdatePolicy=.*/AutomaticUpdatePolicy=none/' "${conf}"
	elif grep -q '^\[Daemon\]' "${conf}"; then
		sed -i '/^\[Daemon\]/a AutomaticUpdatePolicy=none' "${conf}"
	else
		printf '\n[Daemon]\nAutomaticUpdatePolicy=none\n' >>"${conf}"
	fi
else
	printf '[Daemon]\nAutomaticUpdatePolicy=none\n' >"${conf}"
fi
