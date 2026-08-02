#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# GPU options are now emitted only when an AMD display device matches the
# versioned hardware policy. Remove the former image-wide configuration.
rm -f /etc/modprobe.d/amdgpu-kyth.conf
