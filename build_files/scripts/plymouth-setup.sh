#!/bin/bash
# Plymouth boot splash setup — runs as a standalone Dockerfile layer so Docker
# can cache the expensive dracut rebuild independently of the daily branding layer.
# Source files are COPY'd from the build context to /tmp/kyth-plymouth/ and
# /tmp/kyth-branding/ before this script is called.

set -euo pipefail

PLYMOUTH_THEME_DIR=/usr/share/plymouth/themes/kyth
mkdir -p "${PLYMOUTH_THEME_DIR}"

rsvg-convert -w 256 /tmp/kyth-branding/kyth-logo-transparent.svg \
	-o "${PLYMOUTH_THEME_DIR}/kyth-logo.png"
install -m 0644 /tmp/kyth-plymouth/kyth.plymouth "${PLYMOUTH_THEME_DIR}/"
install -m 0644 /tmp/kyth-plymouth/kyth.script "${PLYMOUTH_THEME_DIR}/"

# Replace Fedora watermarks in every Plymouth fallback theme with transparent
# assets. This guard is installed permanently and rerun after later package
# transactions because dnf upgrades can restore upstream theme files.
install -Dm0755 /tmp/kyth-plymouth-configure \
	/usr/libexec/kyth-plymouth-configure
install -Dm0755 /tmp/plymouth-branding-guard.sh \
	/usr/libexec/kyth-plymouth-branding-guard
/usr/libexec/kyth-plymouth-branding-guard \
	/tmp/kyth-branding/transparent-watermark.svg

plymouth-set-default-theme kyth
