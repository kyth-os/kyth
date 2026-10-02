#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/thirdparty-common.sh disable=SC1091
source "${SCRIPT_DIR}/lib/thirdparty-common.sh"
CURL_COMMON_ARGS+=(--max-time 3600)

# ── GE-Proton ────────────────────────────────────────────────────────────────
# Installed system-wide so Steam picks it up for all users without manual setup.
# Steam looks in /usr/share/steam/compatibilitytools.d/ in addition to ~/.steam.
# Custom rechunk metadata places this payload in its own published image layer,
# so a Proton refresh does not invalidate the full package or Kyth payload.
# NOTE: identifiers keep the historical `PROTON_CACHYOS_*` names (build arg,
# CI outputs, supply-chain labels) to avoid churning the Dockerfile/CI
# plumbing; the source of truth is GloriousEggroll/proton-ge-custom.
# x86_64 asset (not aarch64) — grep anchors on `x86_64.tar.gz`.
PROTON_CACHYOS_REPO_API="https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases"
PROTON_CACHYOS_VER="${PROTON_CACHYOS_VER:?PROTON_CACHYOS_VER must be an exact release tag}"
require_release_tag PROTON_CACHYOS_VER "${PROTON_CACHYOS_VER}"
TMPDIR_PC=$(mktemp -d)
trap 'rm -rf "${TMPDIR_PC}"' EXIT

release_api="${PROTON_CACHYOS_REPO_API}/tags/${PROTON_CACHYOS_VER}"

release_json="${TMPDIR_PC}/release.json"
if ! curl -fsSL "${CURL_COMMON_ARGS[@]}" "${CURL_AUTH_ARGS[@]}" "${release_api}" -o "${release_json}"; then
	echo "Failed to fetch GE-Proton release info from ${release_api}" >&2
	exit 1
fi

PROTON_CACHYOS_TARBALL_URL=$(
	grep -o 'https://[^"]*x86_64\.tar\.gz' "${release_json}" | head -n1
)

if [[ -z "${PROTON_CACHYOS_TARBALL_URL}" ]]; then
	echo "Failed to locate GE-Proton release assets from ${release_api}" >&2
	exit 1
fi

PROTON_CACHYOS_TARBALL=$(basename "${PROTON_CACHYOS_TARBALL_URL}")

mkdir -p /usr/share/steam/compatibilitytools.d
curl -fsSL "${CURL_COMMON_ARGS[@]}" "${PROTON_CACHYOS_TARBALL_URL}" \
	-o "${TMPDIR_PC}/${PROTON_CACHYOS_TARBALL}"

# Same verification path every other thirdparty installer uses (GitHub asset
# digest first, falling back to a sidecar checksum file — the .sha512sum this
# release publishes) instead of this script's own narrower sha512sum-only check.
verify_release_asset "${release_json}" "${TMPDIR_PC}/${PROTON_CACHYOS_TARBALL}" \
	"${PROTON_CACHYOS_TARBALL}" "${TMPDIR_PC}"

PROTON_EXTRACT_DIR="${TMPDIR_PC}/extracted"
safe_extract_tar "${TMPDIR_PC}/${PROTON_CACHYOS_TARBALL}" "${PROTON_EXTRACT_DIR}"
cp -a --no-preserve=ownership "${PROTON_EXTRACT_DIR}/." \
	/usr/share/steam/compatibilitytools.d/
