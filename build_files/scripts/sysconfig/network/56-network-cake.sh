#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# Migrated to consolidated sysctl generator (00-sysctl-compose → network.toml).
# CAKE qdisc now lives in build_files/config/sysctl/network.toml — single owner.
# Do not re-add sysctl writes here.
