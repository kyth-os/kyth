#!/bin/bash
# shellcheck shell=bash
# ── Updater signing trust anchor ─────────────────────────────────────────────
# Installs the KythOS updater signing public key(s) — the trust anchor
# the rclone and GE-Proton runtime updaters verify the signed update
# manifest against (docs/updater-signing.md). Ships as a placeholder
# with no key material until the real public key is generated offline
# and committed at /ctx/config/updater-signing-keys.asc; with the
# placeholder in place the updaters fail closed by design.
install -Dm 0644 /ctx/config/updater-signing-keys.asc \
	/usr/share/kyth/updater-signing-keys.asc
