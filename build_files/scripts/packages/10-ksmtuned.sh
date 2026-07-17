#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── ksmtuned memory deduplication ────────────────────────────────────────────
# Dynamically controls Kernel Samepage Merging (KSM) to merge duplicate memory
# pages, reducing RAM usage and memory footprint under multi-app/gaming workloads.
dnf5 install -y --skip-unavailable ksmtuned || true
if rpm -q ksmtuned >/dev/null 2>&1; then
	systemctl enable ksm.service ksmtuned.service 2>/dev/null || true
fi
