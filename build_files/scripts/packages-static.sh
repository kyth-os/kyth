#!/bin/bash
# shellcheck shell=bash
# Thin orchestrator for domain package-install fragments.
# Fragments live in build_files/scripts/packages/*.sh and are run in sorted order.
#
# Keep downloads in Docker's /var/cache mount to speed up later rebuilds.
# bootc maps persistent /var defaults through /usr/share/factory/var, so the
# final Dockerfile stage explicitly removes any libdnf5 metadata copied there.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/lib/fragment-runner.sh"
run_fragments "packages" "bash"
