#!/bin/bash
# shellcheck shell=bash
# Thin orchestrator for domain package-install fragments.
# Fragments live in build_files/scripts/packages/*.sh and are run in sorted order.
#
# Keep downloads in Docker's /var/cache mount to speed up later rebuilds.
# bootc maps persistent /var defaults through /usr/share/factory/var, so the
# final Dockerfile stage explicitly removes any libdnf5 metadata copied there.
set -euo pipefail

# When executed from the container build (bound at /ctx/packages-static.sh),
# fragments are mounted alongside at /ctx/packages/. In the repo checkout they
# sit next to this file under scripts/packages/.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "${HERE}/packages" ]]; then
	FRAG_DIR="${HERE}/packages"
elif [[ -d /ctx/packages ]]; then
	FRAG_DIR=/ctx/packages
else
	echo "package fragments not found (looked in ${HERE}/packages and /ctx/packages)" >&2
	exit 1
fi

shopt -s nullglob
fragments=("${FRAG_DIR}"/*.sh)
if ((${#fragments[@]} == 0)); then
	echo "No package fragments in ${FRAG_DIR}" >&2
	exit 1
fi

for frag in "${fragments[@]}"; do
	# shellcheck disable=SC1090
	bash "${frag}"
done
