#!/usr/bin/env bash
# Build a KythOS live payload and delegate ISO assembly to Titanoboa, matching
# Bazzite's live ISO path.

set -euo pipefail

SOURCE_TAG="${SOURCE_TAG:-latest}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${KYTH_ISO_OUTPUT:-${REPO_ROOT}/output/live-iso}"
BASE_IMAGE="${INSTALLER_BASE_IMAGE:-ghcr.io/mrtrick37/kyth:${SOURCE_TAG}}"
INSTALL_SOURCE_IMAGE="${BASE_IMAGE}"
LIVE_TAG="${KYTH_LIVE_TAG:-localhost/kyth-live:${SOURCE_TAG}}"
TITANOBOA_REF="7737f4748458252ac827dca14b3d6dd09298472a"
TITANOBOA_DIR="${TITANOBOA_DIR:-${XDG_CACHE_HOME:-${HOME}/.cache}/kyth/titanoboa}"

for cmd in git podman sudo; do
	command -v "${cmd}" >/dev/null || {
		echo "ERROR: missing required command: ${cmd}" >&2
		exit 1
	}
done

if [[ "${BASE_IMAGE}" == localhost/* ]] &&
	! sudo podman image exists "${BASE_IMAGE}" &&
	command -v docker >/dev/null &&
	docker image inspect "${BASE_IMAGE}" >/dev/null 2>&1; then
	echo "==> Importing Docker image into rootful Podman: ${BASE_IMAGE}"
	docker save "${BASE_IMAGE}" | sudo podman load
fi

# installer/build.sh always bakes KYTH_SOURCE_IMAGE=ghcr.io/mrtrick37/kyth:${SOURCE_TAG}
# into the live ISO, regardless of where the live payload itself was built from.
# The booted live VM is a separate environment with no access to this host's
# local image storage, so a local BASE_IMAGE must be published under that exact
# ref or the installer's `bootc install` will fail with "manifest unknown".
#
# Pushed with `docker`, not `podman`: this image shares many blobs with the
# public ghcr.io/ublue-os/kinoite-main base it's built FROM, and podman's push
# reproducibly fails those blobs with "trying to reuse blob ... 403 Forbidden"
# — a cross-repository blob-mount that GHCR rejects and podman doesn't fall
# back from. `docker push` uploads them directly and does not hit this.
if [[ "${BASE_IMAGE}" == localhost/* ]] && command -v docker >/dev/null; then
	GHCR_REF="ghcr.io/mrtrick37/kyth:${SOURCE_TAG}"
	echo "==> Publishing local build to ${GHCR_REF} so the installer can fetch it from inside the live VM"
	docker tag "${BASE_IMAGE}" "${GHCR_REF}"
	docker push "${GHCR_REF}"
	INSTALL_SOURCE_IMAGE="${GHCR_REF}"
fi

echo "==> Fetching Titanoboa (background) and building KythOS live payload (foreground) in parallel"

# Titanoboa fetch is independent of the podman build — run it in the background.
_titanoboa_ok="/tmp/kyth-titanoboa-ok.$$"
(
	if [[ ! -d "${TITANOBOA_DIR}/.git" ]]; then
		echo "==> Initializing Titanoboa cache"
		mkdir -p "$(dirname "${TITANOBOA_DIR}")"
		git init "${TITANOBOA_DIR}"
		git -C "${TITANOBOA_DIR}" remote add origin https://github.com/Zeglius/titanoboa.git
	fi
	if ! git -C "${TITANOBOA_DIR}" cat-file -e "${TITANOBOA_REF}^{commit}" 2>/dev/null; then
		echo "==> Fetching Titanoboa ${TITANOBOA_REF}"
		git -C "${TITANOBOA_DIR}" fetch --depth 1 origin "${TITANOBOA_REF}"
	fi
	if [[ "$(git -C "${TITANOBOA_DIR}" rev-parse HEAD 2>/dev/null || true)" != "${TITANOBOA_REF}" ]]; then
		echo "==> Checking out Titanoboa ${TITANOBOA_REF}"
		git -C "${TITANOBOA_DIR}" checkout --detach "${TITANOBOA_REF}"
	fi
	touch "${_titanoboa_ok}"
) &

# --pull=newer: re-fetch the base image when the registry has a newer digest.
# Without it, a stale cached ${BASE_IMAGE} layer is silently reused, so a rebuild
# after CI publishes fresh bits produces an ISO from the old OS. Skipped for
# localhost/* images, which are loaded from Docker above and have no registry.
echo "==> Building KythOS live payload from ${BASE_IMAGE}"
pull_flag=(--pull=newer)
[[ "${BASE_IMAGE}" == localhost/* ]] && pull_flag=()
sudo podman build \
	"${pull_flag[@]}" \
	--cap-add SYS_ADMIN \
	--security-opt label=disable \
	--network host \
	--build-arg "BASE_IMAGE=${BASE_IMAGE}" \
	--build-arg "INSTALL_SOURCE_IMAGE=${INSTALL_SOURCE_IMAGE}" \
	--build-arg "SOURCE_TAG=${SOURCE_TAG}" \
	--tag "${LIVE_TAG}" \
	-f installer/Containerfile \
	"${REPO_ROOT}"

wait
if [[ ! -f "${_titanoboa_ok}" ]]; then
	echo "ERROR: Titanoboa fetch failed" >&2
	exit 1
fi
rm -f "${_titanoboa_ok}"

mkdir -p "${OUTPUT_DIR}"
WORK="$(mktemp -d -p "${TMPDIR:-/var/tmp}" kyth-titanoboa.XXXXXXXXXX)"
# Rootful podman writes root-owned files into ${WORK} — an unprivileged rm
# would fail silently and leak multi-GB dirs in /var/tmp.
trap 'sudo rm -rf "${WORK}"' EXIT

echo "==> Assembling ISO with Titanoboa"
sudo podman run --rm -i \
	--network host \
	--cap-add sys_admin --security-opt label=disable \
	-v "${TITANOBOA_DIR}/build_iso.sh:/src/build_iso.sh:ro" \
	--mount type=image,source="${LIVE_TAG}",dst=/rootfs \
	-v "${WORK}:/output" \
	quay.io/fedora/fedora:44 /src/build_iso.sh
mv "${WORK}/KYTHOS-44-LIVE.iso" "${OUTPUT_DIR}/kyth-live-${SOURCE_TAG}.iso"
sudo chown "$(id -u):$(id -g)" "${OUTPUT_DIR}/kyth-live-${SOURCE_TAG}.iso"
test -r "${OUTPUT_DIR}/kyth-live-${SOURCE_TAG}.iso"
test -w "${OUTPUT_DIR}/kyth-live-${SOURCE_TAG}.iso"
echo "==> KythOS live ISO ready: ${OUTPUT_DIR}/kyth-live-${SOURCE_TAG}.iso"
