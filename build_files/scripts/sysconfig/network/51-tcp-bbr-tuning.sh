#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# Migrated to consolidated sysctl generator (00-sysctl-compose → network.toml).
# Do not re-add sysctl writes here — see build_files/config/sysctl/network.toml.
