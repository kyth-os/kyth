# ── Build recipes ────────────────────────────────────────────────────────────
# Imported by Justfile. Requires _internal.just for _build-bib and _rootful_load_image.
import "_vars.just"
import "_internal.just"

# Build the base image from build_base/.
[group('Build')]
build-base base_image="ghcr.io/ublue-os/kinoite-main:44" kernel_flavor="fedora":
    #!/usr/bin/env bash
    if ! id -nG | grep -qw docker; then
        if ! id -nG "$USER" | grep -qw docker; then
            echo "Adding $USER to docker group (requires sudo)..."
            sudo usermod -aG docker "$USER"
        fi
        echo "Activating docker group for this session via sg — re-running..."
        exec sg docker -c "just build-base '{{ base_image }}' '{{ kernel_flavor }}'"
    fi

    if command -v cosign &>/dev/null; then
        echo "Verifying base image signature with cosign..."
        cosign verify \
            --certificate-oidc-issuer=https://token.actions.githubusercontent.com \
            --certificate-identity-regexp='^https://github\.com/ublue-os/main/' \
            {{ base_image }} \
            || echo "WARNING: cosign verification failed — proceeding without signature check."
    else
        echo "WARNING: cosign not found — skipping signature verification."
    fi
    echo "Refreshing upstream base image {{ base_image }}..."
    docker pull {{ base_image }}
    CACHYOS_KERNEL_VER=unused
    if [[ "{{ kernel_flavor }}" != "fedora" ]]; then
        CACHYOS_KERNEL_VER=$(./build_files/scripts/resolve-versions.sh cachyos-kernel)
    fi
    echo "CachyOS kernel: ${CACHYOS_KERNEL_VER}"
    echo "Kernel flavor: {{ kernel_flavor }}"
    docker build \
        --build-arg BASE_IMAGE={{ base_image }} \
        --build-arg KYTH_KERNEL_FLAVOR="{{ kernel_flavor }}" \
        --build-arg CACHYOS_KERNEL_VER="${CACHYOS_KERNEL_VER}" \
        --tag localhost/kyth-base:stable \
        build_base/

# Build the full KythOS image.
[group('Build')]
build: build-base
    #!/usr/bin/env bash
    set -euo pipefail
    if ! id -nG | grep -qw docker; then
        exec sg docker -c "just build"
    fi
    REGISTRY="${REGISTRY:-ghcr.io/mrtrick37/kyth}"
    BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
    CACHE_BRANCH=$([ "${BRANCH}" = "testing" ] && echo "testing" || echo "main")

    THIRDPARTY_VERSIONS_HASH=$(./build_files/scripts/resolve-versions.sh thirdparty-hash)
    echo "Thirdparty hash: ${THIRDPARTY_VERSIONS_HASH}"
    MOK_SECRET_ARG=()
    SECUREBOOT_SIGNING_REQUESTED=0
    if [[ -n "${MOK_KEY_FILE:-}" && ! -f "${MOK_KEY_FILE}" ]]; then
        echo "ERROR: MOK_KEY_FILE is set but does not exist: ${MOK_KEY_FILE}" >&2
        exit 1
    fi
    if [[ -n "${MOK_KEY:-}" || -n "${MOK_KEY_FILE:-}" ]]; then
        echo "Secure Boot: MOK key set — vmlinuz will be signed"
        if [[ -n "${MOK_KEY_FILE:-}" ]]; then
            MOK_SECRET_ARG=(--secret "id=mok_key,src=${MOK_KEY_FILE}")
        else
            MOK_SECRET_ARG=(--secret id=mok_key,env=MOK_KEY)
        fi
        SECUREBOOT_SIGNING_REQUESTED=1
    else
        echo "Secure Boot: MOK key not set — signing skipped (set MOK_KEY_FILE to enable)"
    fi
    docker buildx build \
        --build-arg ENABLE_ANANICY="${ENABLE_ANANICY:-1}" \
        --build-arg ENABLE_SCX="${ENABLE_SCX:-1}" \
        --build-arg THIRDPARTY_VERSIONS_HASH="${THIRDPARTY_VERSIONS_HASH}" \
        --build-arg BUILD_DATE="$(date +%Y-%m-%d)" \
        --build-arg SECUREBOOT_SIGNING_REQUESTED="${SECUREBOOT_SIGNING_REQUESTED}" \
        "${MOK_SECRET_ARG[@]}" \
        --cache-from "type=registry,ref=${REGISTRY}:buildcache-final-${CACHE_BRANCH}-fedora" \
        --tag localhost/kyth:latest \
        --load \
        .

# Build a QCOW2 virtual machine image
[group('Build Virtual Machine Image')]
build-qcow2 $target_image=("localhost/" + image_name) $tag=default_tag: && (_build-bib target_image tag "qcow2" "disk_config/disk.toml")

# Build a RAW virtual machine image
[group('Build Virtual Machine Image')]
build-raw $target_image=("localhost/" + image_name) $tag=default_tag: && (_build-bib target_image tag "raw" "disk_config/disk.toml")

# Build an ISO virtual machine image
[group('Build Virtual Machine Image')]
build-iso $target_image=("localhost/" + image_name) $tag=default_tag: && (_build-bib target_image tag "iso" "disk_config/iso.toml")

# Build a live ISO with the KythOS web installer.
[group('Build Virtual Machine Image')]
build-live-iso source_tag="latest":
    #!/usr/bin/env bash
    set -euo pipefail
    SOURCE_TAG={{ source_tag }} bash build_files/build-live-iso.sh

# Identical to build-live-iso — build_files/build-live-iso.sh always does a
# full rebuild, there's no separate incremental path. Kept as its own recipe
# name for discoverability ("rebuild" reads more naturally once a live ISO
# already exists); delegates so there's only one real implementation.
# Rebuild the live ISO payload and assemble it with Titanoboa.
[group('Build Virtual Machine Image')]
rebuild-live-iso source_tag="latest": (build-live-iso source_tag)

# Build a live ISO from localhost/kyth:latest for local QEMU testing.
[group('Build Virtual Machine Image')]
rebuild-live-iso-local:
    #!/usr/bin/env bash
    set -euo pipefail
    just build
    SOURCE_TAG=local INSTALLER_BASE_IMAGE=localhost/kyth:latest bash build_files/build-live-iso.sh
