#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# shellcheck source=../lib/check-multilib.sh disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/../lib/check-multilib.sh"

# Report-only sweep of the full package set installed above — see
# scan_multilib_orphans in lib/check-multilib.sh. Numbered last so it runs
# after every other package fragment has landed its packages.
scan_multilib_orphans
