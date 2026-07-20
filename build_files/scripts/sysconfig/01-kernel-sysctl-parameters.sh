#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

mkdir -p /etc/sysctl.d
cp /ctx/data/sysctl.d/99-kyth.conf /etc/sysctl.d/99-kyth.conf

echo 'tcp_bbr' >/etc/modules-load.d/bbr.conf
