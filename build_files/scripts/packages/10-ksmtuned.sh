#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# shellcheck source=../lib/packages-helpers.sh disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/../lib/packages-helpers.sh"

if ! is_enabled "${ENABLE_KSM:-0}"; then
	echo "KSM profile is disabled; skipping global memory deduplication."
	exit 0
fi

# ── ksmtuned memory deduplication ────────────────────────────────────────────
# Dynamically controls Kernel Samepage Merging (KSM) to merge duplicate memory
# pages, reducing RAM usage and memory footprint under multi-app/gaming workloads.
dnf5 install -y --skip-unavailable ksmtuned || true
if rpm -q ksmtuned >/dev/null 2>&1; then
	systemctl enable ksm.service ksmtuned.service 2>/dev/null || true
fi
