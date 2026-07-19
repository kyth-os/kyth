#!/bin/bash
# shellcheck shell=bash
# Thin orchestrator for domain sysconfig fragments.
# Fragments live in build_files/scripts/sysconfig/*.sh and are run in sorted order.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/lib/fragment-runner.sh"
run_fragments "sysconfig" "bash"
