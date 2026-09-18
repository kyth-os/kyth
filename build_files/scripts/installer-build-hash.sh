#!/usr/bin/env bash
# Print the cache-busting hash for the live ISO installer payload.
#
# Covers the full installer-web and shared-rs source trees plus every live
# image input the payload build consumes, so any change to the shipped
# installer or its helpers invalidates the container layer cache. Shared by
# build_files/build-live-iso.sh and .github/workflows/build-live-iso.yml —
# keep the path list here, not in both callers.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

git ls-files -z \
	installer/Containerfile \
	installer/build.sh \
	installer/iso.yaml \
	installer/calamares \
	src/kyth-installer-web \
	src/kyth-shared-rs \
	build_files/exe-handler-apps.json \
	build_files/kyth-launch-installer \
	build_files/kyth-installerd.service \
	build_files/kyth-vm-acceptance.service \
	build_files/kyth_shared/kyth_shared/vm_acceptance.py \
	| sort -z \
	| xargs -0 -r sh -c '
		for f in "$@"; do
			# The installer-web node_modules entry is a tracked symlink
			# into the hub web tree (never shipped: the Containerfile
			# removes it before npm ci). Hash link targets by name so
			# directory links cannot break the hash and file changes
			# still flow through their real tracked paths.
			if [ -L "$f" ]; then
				printf "link %s -> %s\n" "$f" "$(readlink "$f")"
			elif [ -f "$f" ]; then
				sha256sum "$f"
			fi
		done' _ \
	| sha256sum \
	| awk '{print $1}'
