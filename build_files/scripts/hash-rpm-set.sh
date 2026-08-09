#!/usr/bin/env bash
# Content-hash for the RPM-set layer — fed to Dockerfile ARG RPM_SET_HASH.
# P2-7: build hash guard — content hash (sha256 of package fragments) busts
# the 2-3 GB dnf layer only when package content changes, not on mirror
# timestamp bumps. Do not add `date` or `dnf makecache` output to inputs.
# Hashes every file whose content busts the 2–3 GB dnf layer, so a mirror
# timestamp bump alone does not invalidate the BuildKit cache.
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
# Hash packages-static.sh + every package fragment + helper lib deterministically
hash_src="$(find "${repo_root}/build_files/scripts/packages-static.sh" \
  "${repo_root}/build_files/scripts/packages" \
  "${repo_root}/build_files/scripts/lib" \
  -type f -print0 2>/dev/null | sort -z | xargs -0 sha256sum 2>/dev/null | sha256sum | cut -d' ' -f1)"
echo "${hash_src}"
