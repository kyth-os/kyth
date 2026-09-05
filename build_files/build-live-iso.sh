#!/usr/bin/env bash
# Build a KythOS live payload and delegate ISO assembly to Titanoboa, matching
# Bazzite's live ISO path.

set -euo pipefail

SOURCE_TAG="${SOURCE_TAG:-latest}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${KYTH_ISO_OUTPUT:-${REPO_ROOT}/output/live-iso}"
BASE_IMAGE="${INSTALLER_BASE_IMAGE:-ghcr.io/kyth-os/kyth:${SOURCE_TAG}}"
INSTALL_SOURCE_IMAGE="${BASE_IMAGE}"
LIVE_TAG="${KYTH_LIVE_TAG:-localhost/kyth-live:${SOURCE_TAG}}"
TITANOBOA_REF="7737f4748458252ac827dca14b3d6dd09298472a"
TITANOBOA_DIR="${TITANOBOA_DIR:-${XDG_CACHE_HOME:-${HOME}/.cache}/kyth/titanoboa}"

for cmd in git podman sudo unshare; do
	command -v "${cmd}" >/dev/null || {
		echo "ERROR: missing required command: ${cmd}" >&2
		exit 1
	}
done

ROOTFUL_PODMAN="${REPO_ROOT}/build_files/scripts/rootful-podman.sh"
mkdir -p "${OUTPUT_DIR}"
build_volume_args=()
INSTALLER_BUILD_HASH="${INSTALLER_BUILD_HASH:-$(sha256sum \
	installer/build.sh \
	build_files/kyth_shared/kyth_shared/vm_acceptance.py \
	build_files/kyth-vm-acceptance.service | sha256sum | awk '{print $1}')}"

if [[ "${BASE_IMAGE}" == localhost/* ]] &&
	! "${ROOTFUL_PODMAN}" image exists "${BASE_IMAGE}" &&
	command -v docker >/dev/null &&
	docker image inspect "${BASE_IMAGE}" >/dev/null 2>&1; then
	echo "==> Importing Docker image into rootful Podman: ${BASE_IMAGE}"
	docker save "${BASE_IMAGE}" | "${ROOTFUL_PODMAN}" load
fi

# The live VM cannot access the host's local image storage, so the installer
# builder embeds the local image into the ISO through the OCI layout.  Keep the
# public registry reference as the update target, but never publish a local
# test image as a side effect of a local ISO build.
if [[ "${BASE_IMAGE}" == localhost/* ]]; then
	if ! "${ROOTFUL_PODMAN}" image exists "${BASE_IMAGE}"; then
		echo "ERROR: local installer image is unavailable to Podman: ${BASE_IMAGE}" >&2
		exit 1
	fi
	LOCAL_IMAGE_DIR="${OUTPUT_DIR}/.kyth-installer-image"
	mkdir -p "${LOCAL_IMAGE_DIR}"
	if [[ -n "${CONTAINER_ID:-}" ]] && command -v distrobox-host-exec >/dev/null 2>&1; then
		SKOPEO=(distrobox-host-exec skopeo)
	else
		SKOPEO=(skopeo)
	fi
	echo "==> Exporting ${BASE_IMAGE} to a local OCI layout for the installer builder"
	"${SKOPEO[@]}" copy --retry-times 3 \
		"containers-storage:${BASE_IMAGE}" \
		"oci:${LOCAL_IMAGE_DIR}:latest"
	# Podman build containers have their own containers-storage namespace. Mount
	# the exported layout into the build and use the OCI transport from there.
	INSTALL_SOURCE_IMAGE="oci:/src/kyth-installer-image:latest"
	build_volume_args+=(--volume "${LOCAL_IMAGE_DIR}:/src/kyth-installer-image:ro")
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
"${ROOTFUL_PODMAN}" build \
	"${pull_flag[@]}" \
	--cap-add SYS_ADMIN \
	--security-opt label=disable \
	--network host \
	"${build_volume_args[@]}" \
	--build-arg "BASE_IMAGE=${BASE_IMAGE}" \
	--build-arg "INSTALL_SOURCE_IMAGE=${INSTALL_SOURCE_IMAGE}" \
	--build-arg "INSTALLER_BUILD_HASH=${INSTALLER_BUILD_HASH}" \
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

# The build runs through host-user Podman when this checkout is inside
# Distrobox. /tmp and /var/tmp are container-local there, so a temporary
# directory under the shared checkout is visible to the host Podman mount.
WORK="$(mktemp -d -p "${OUTPUT_DIR}" kyth-titanoboa.XXXXXXXXXX)"
# Rootful podman writes root-owned files into ${WORK} — an unprivileged rm
# would fail silently and leak multi-GB dirs in /var/tmp.
trap 'sudo rm -rf "${WORK}"' EXIT

echo "==> Assembling ISO with Titanoboa"
"${ROOTFUL_PODMAN}" run --rm -i \
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
