#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# NVIDIA options are now emitted only for matched NVIDIA display hardware by
# kyth-hardware-policy. Remove the former image-wide configuration.
rm -f /etc/modprobe.d/nvidia-kyth.conf
