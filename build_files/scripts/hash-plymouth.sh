#!/usr/bin/env bash
set -euo pipefail
# Hash plymouth/branding inputs for layer cache gating
# Usage: ./build_files/scripts/hash-plymouth.sh
# Output: sha256 of plymouth + branding files
root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
# shellcheck disable=SC2046
sha256sum \
  "$root/build_files/plymouth/"* \
  "$root/build_files/branding/kyth-logo-transparent.svg" \
  "$root/build_files/branding/transparent-watermark.svg" \
  "$root/build_files/scripts/plymouth-setup.sh" \
  "$root/build_base/plymouth/kyth-plymouth-configure" 2>/dev/null | sha256sum | cut -d' ' -f1
