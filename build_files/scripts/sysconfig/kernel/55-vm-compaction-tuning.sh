#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# Migrated to consolidated sysctl generator (00-sysctl-compose → base.toml).
# vm.extfrag_threshold now lives in build_files/config/sysctl/base.toml.
# Do not re-add sysctl writes here.
