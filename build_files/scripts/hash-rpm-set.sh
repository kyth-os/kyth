#!/usr/bin/env bash
# Content-hash for the RPM-set layer — fed to Dockerfile ARG RPM_SET_HASH.
# P2-7: build hash guard — content hash (sha256 of package fragments) busts
# the 2-3 GB dnf layer only when package content changes, not on mirror
# timestamp bumps. Do not add `date` or `dnf makecache` output to inputs.
# Hashes every file whose content busts the 2–3 GB dnf layer, so a mirror
# timestamp bump alone does not invalidate the BuildKit cache.
#
# Only lib/ helpers actually `source`d by packages-static.sh or a
# build_files/scripts/packages/*.sh fragment belong in lib_files below.
# Whole-directory hashing of lib/ was tried and dropped: it also covers
# branding/thirdparty/plymouth/sysconfig helpers this layer never loads,
# so e.g. editing dracut-retry.sh busted the 2-3 GB layer for no reason.
# Add a file here only when a packages fragment starts sourcing it.
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
lib_files=(
	"${repo_root}/build_files/scripts/lib/fragment-runner.sh"
	"${repo_root}/build_files/scripts/lib/packages-helpers.sh"
	"${repo_root}/build_files/scripts/lib/check-multilib.sh"
	"${repo_root}/build_files/scripts/lib/gaming-coprs.sh"
	"${repo_root}/build_files/scripts/lib/dnf-retry.sh"
	"${repo_root}/build_files/scripts/lib/fedora-kernel.sh"
)
# Hash packages-static.sh + every package fragment + the lib helpers above
hash_src="$(find "${repo_root}/build_files/scripts/packages-static.sh" \
	"${repo_root}/build_files/scripts/packages" \
	"${lib_files[@]}" \
	-type f -print0 2>/dev/null | sort -z | xargs -0 sha256sum 2>/dev/null | sha256sum | cut -d' ' -f1)"
echo "${hash_src}"
