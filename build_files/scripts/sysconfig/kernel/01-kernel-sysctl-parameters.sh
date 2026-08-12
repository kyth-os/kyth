#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# sysctl is now owned by 00-sysctl-compose (consolidated generator).
# This fragment retains only the BBR module load; do not re-add sysctl writes here.
write_line 'tcp_bbr' /etc/modules-load.d/bbr.conf
