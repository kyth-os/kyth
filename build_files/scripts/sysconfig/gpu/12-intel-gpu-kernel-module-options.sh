#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# Intel options are now emitted only for matched i915 display hardware by the
# versioned hardware policy. Remove the former image-wide configuration.
rm -f /etc/modprobe.d/i915-kyth.conf
