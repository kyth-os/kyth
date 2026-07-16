#!/bin/bash
set -euo pipefail

# shellcheck source=lib/curl-common.sh disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib/curl-common.sh"
CURL_COMMON_ARGS+=(--max-time 3600)

# ── Proton-CachyOS ───────────────────────────────────────────────────────────
# Installed system-wide so Steam picks it up for all users without manual setup.
# Steam looks in /usr/share/steam/compatibilitytools.d/ in addition to ~/.steam.
# This lives in its own image layer so Proton-CachyOS refreshes only re-download
# this layer (~700 MB), not the full 3+ GB package layer.
# Standard x86_64 build (not the _v3 microarch variant) to avoid crashing on
# CPUs without AVX2/BMI2/FMA.
PROTON_CACHYOS_REPO_API="https://api.github.com/repos/CachyOS/proton-cachyos/releases"
PROTON_CACHYOS_VER="${PROTON_CACHYOS_VER:-}"
TMPDIR_PC=$(mktemp -d)
trap 'rm -rf "${TMPDIR_PC}"' EXIT

if [[ -n "${PROTON_CACHYOS_VER}" ]]; then
	release_api="${PROTON_CACHYOS_REPO_API}/tags/${PROTON_CACHYOS_VER}"
else
	release_api="${PROTON_CACHYOS_REPO_API}/latest"
fi

release_json="${TMPDIR_PC}/release.json"
if ! curl -fsSL "${CURL_COMMON_ARGS[@]}" "${CURL_AUTH_ARGS[@]}" "${release_api}" -o "${release_json}"; then
	echo "Failed to fetch Proton-CachyOS release info from ${release_api}" >&2
	exit 1
fi

PROTON_CACHYOS_TARBALL_URL=$(
	grep -o 'https://[^"]*x86_64\.tar\.xz' "${release_json}" | head -n1
)
PROTON_CACHYOS_SHA512_URL=$(
	grep -o 'https://[^"]*x86_64\.sha512sum' "${release_json}" | head -n1
)

if [[ -z "${PROTON_CACHYOS_TARBALL_URL}" || -z "${PROTON_CACHYOS_SHA512_URL}" ]]; then
	echo "Failed to locate Proton-CachyOS release assets from ${release_api}" >&2
	exit 1
fi

PROTON_CACHYOS_TARBALL=$(basename "${PROTON_CACHYOS_TARBALL_URL}")
PROTON_CACHYOS_SHA512=$(basename "${PROTON_CACHYOS_SHA512_URL}")

mkdir -p /usr/share/steam/compatibilitytools.d
curl -fsSL "${CURL_COMMON_ARGS[@]}" "${PROTON_CACHYOS_TARBALL_URL}" \
	-o "${TMPDIR_PC}/${PROTON_CACHYOS_TARBALL}"
curl -fsSL "${CURL_COMMON_ARGS[@]}" "${PROTON_CACHYOS_SHA512_URL}" \
	-o "${TMPDIR_PC}/${PROTON_CACHYOS_SHA512}"

(
	cd "${TMPDIR_PC}"
	sha512sum -c "${PROTON_CACHYOS_SHA512}"
)

tar -xJf "${TMPDIR_PC}/${PROTON_CACHYOS_TARBALL}" -C /usr/share/steam/compatibilitytools.d/
