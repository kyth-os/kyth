#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

is_enabled() {
	case "${1,,}" in
	1 | true | yes | on) return 0 ;;
	*) return 1 ;;
	esac
}

# ── system76-scheduler ────────────────────────────────────────────────────────
# Dynamically adjusts CFS nice values and I/O priority based on which window
# is focused and whether a game is running.  Gives a noticeable responsiveness
# boost during gaming without requiring per-app configuration.
if dnf5 repoquery --available system76-scheduler 2>/dev/null | grep -q .; then
	dnf5 install -y --skip-unavailable system76-scheduler || true
	if rpm -q system76-scheduler >/dev/null 2>&1; then
		systemctl enable com.system76.Scheduler 2>/dev/null || true
	fi
else
	echo "system76-scheduler is unavailable in configured repos; skipping."
fi

# ── ananicy-cpp process priority rules ───────────────────────────────────────
# Applies static per-process CPU/I/O priorities (browser, game launchers,
# compilers, etc.) to smooth desktop responsiveness under mixed load.
if is_enabled "${ENABLE_ANANICY:-1}"; then
	if dnf5 repoquery --available ananicy-cpp 2>/dev/null | grep -q .; then
		dnf5 install -y --skip-unavailable \
			ananicy-cpp \
			ananicy-cpp-rules \
			ananicy-cpp-rules-git || true
		if rpm -q ananicy-cpp >/dev/null 2>&1; then
			systemctl enable ananicy-cpp.service 2>/dev/null || true
		fi
	else
		echo "ananicy-cpp is unavailable in configured repos; skipping."
	fi
else
	echo "ENABLE_ANANICY is off; skipping ananicy-cpp install."
fi
