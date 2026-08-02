#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── Intel GPU kernel module options ─────────────────────────────────────────
# enable_guc=3: enables GuC firmware submission (command scheduling) and HuC
#   loading on Gen 9+ hardware. Without this, H.264/HEVC VA-API decode falls
#   back to software on many Intel iGPUs, and power management is degraded.
# enable_huc=2: forces HuC firmware load even when GuC submission is active.
#   Required on some Gen 9/10 parts where HuC would otherwise be skipped.
# These options are safe no-ops on Intel GPUs that use the xe driver (Arc /
#   Meteor Lake+), which manages GuC/HuC independently of i915.
write_config /etc/modprobe.d/i915-kyth.conf <<'I915EOF'
options i915 enable_guc=3 enable_huc=2
I915EOF
