#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/config-helpers.sh"

mkdir -p /etc/sysctl.d
cp /ctx/data/sysctl.d/99-kyth.conf /etc/sysctl.d/99-kyth.conf

write_line 'tcp_bbr' /etc/modules-load.d/bbr.conf
