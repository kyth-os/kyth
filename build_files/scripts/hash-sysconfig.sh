#!/usr/bin/env bash
# Content-hash for the sysconfig-static layer — fed to Dockerfile ARG SYSCONFIG_HASH.
# Hashes every file whose content busts the static sysconfig layer, so a
# daily dnf upgrade does not invalidate the post-upgrade wiring when only
# packages changed.
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
hash_src="$(find "${repo_root}/build_files/scripts/sysconfig-static.sh" \
  "${repo_root}/build_files/scripts/sysconfig" \
  "${repo_root}/build_files/data" \
  "${repo_root}/src/kyth_shared" \
  "${repo_root}/build_files/kyth_shared" \
  -type f -print0 2>/dev/null | sort -z | xargs -0 sha256sum 2>/dev/null | sha256sum | cut -d' ' -f1)"
echo "${hash_src}"
