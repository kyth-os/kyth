# ── Build recipes ────────────────────────────────────────────────────────────
# Imported by Justfile. Requires _internal.just for _build-bib and _rootful_load_image.
import "_vars.just"
import "_internal.just"

# Uses podman, not docker: CI's build.yml has its own independent docker
# buildx pipeline and never calls these recipes, so this file only has to
# work for local dev — and kyth ships podman, not docker, on the built OS
# itself. Runs rootful (sudo) so the result lands directly in the same
# containers-storage `bootc switch` reads (see `switch-local`), with no
# rootless->rootful copy step needed afterward. The GHA/registry buildx
# cache flags are dropped: podman/buildah's cache-from/cache-to take a
# plain image reference, not BuildKit's `type=X,key=value` descriptor
# syntax, and BuildKit's registry cache format isn't buildah-readable
# anyway — local podman still reuses its own layer cache across repeated
# runs, just not CI's remote one.

# Build the base image from build_base/.
[group('Build')]
build-base base_image=default_base_image kernel_flavor="fedora" enable_nvidia="0":
    #!/usr/bin/env bash
    set -euo pipefail
    PODMAN="sudo --preserve-env=MOK_KEY podman"

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
    if ! ${PODMAN} image exists {{ base_image }}; then
        echo "Refreshing upstream base image {{ base_image }}..."
        ${PODMAN} pull {{ base_image }}
    fi
    CACHYOS_KERNEL_VER=unused
    if [[ "{{ kernel_flavor }}" != "fedora" ]]; then
        CACHYOS_KERNEL_VER=$(python3 ./build_files/scripts/resolve-versions.py cachyos-kernel)
    fi
    echo "CachyOS kernel: ${CACHYOS_KERNEL_VER}"
    echo "Kernel flavor: {{ kernel_flavor }}"
    echo "Enable NVIDIA: {{ enable_nvidia }}"
    ${PODMAN} build \
        --build-arg BASE_IMAGE={{ base_image }} \
        --build-arg KYTH_KERNEL_FLAVOR="{{ kernel_flavor }}" \
        --build-arg CACHYOS_KERNEL_VER="${CACHYOS_KERNEL_VER}" \
        --build-arg ENABLE_NVIDIA="{{ enable_nvidia }}" \
        --tag localhost/kyth-base:stable \
        build_base/
    if [[ "{{ enable_nvidia }}" == "1" ]]; then
        ${PODMAN} tag localhost/kyth-base:stable localhost/kyth-base:stable-nvidia
        echo "Tagged localhost/kyth-base:stable-nvidia"
    fi

# Build the full KythOS image. See build-base for why this is podman, not docker.
[group('Build')]
build: build-base
    #!/usr/bin/env bash
    set -euo pipefail
    PODMAN="sudo --preserve-env=MOK_KEY podman"

    PROTON_CACHYOS_VER=$(python3 ./build_files/scripts/resolve-versions.py proton-cachyos)
    [[ -n "${PROTON_CACHYOS_VER}" ]] || { echo "Unable to pin Proton-CachyOS" >&2; exit 1; }
    UMU_VERSION=$(python3 ./build_files/scripts/resolve-versions.py thirdparty-versions)
    THIRDPARTY_VERSIONS_HASH=$(printf '%s' "${UMU_VERSION}" | sha256sum | cut -c1-16)
    echo "Pinned third-party release: umu=${UMU_VERSION}"
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
    ${PODMAN} build \
        --build-arg ENABLE_SCX="${ENABLE_SCX:-0}" \
        --build-arg ENABLE_GAMING_PERIPHERALS="${ENABLE_GAMING_PERIPHERALS:-0}" \
        --build-arg ENABLE_VIRTUALIZATION_HOST="${ENABLE_VIRTUALIZATION_HOST:-0}" \
        --build-arg ENABLE_KSM="${ENABLE_KSM:-0}" \
        --build-arg PROTON_CACHYOS_VER="${PROTON_CACHYOS_VER}" \
        --build-arg UMU_VERSION="${UMU_VERSION}" \
        --build-arg THIRDPARTY_VERSIONS_HASH="${THIRDPARTY_VERSIONS_HASH}" \
        --build-arg RPM_SET_HASH="$(./build_files/scripts/hash-rpm-set.sh)" \
        --build-arg SYSCONFIG_HASH="$(./build_files/scripts/hash-sysconfig.sh)" \
        --build-arg GAMING_VERSIONS_HASH="$(./build_files/scripts/hash-gaming-versions.sh --print)" \
        --build-arg BUILD_DATE="$(date +%Y-%m-%d)" \
        --build-arg SECUREBOOT_SIGNING_REQUESTED="${SECUREBOOT_SIGNING_REQUESTED}" \
        "${MOK_SECRET_ARG[@]}" \
        --tag localhost/kyth:latest \
        .

# Entirely local — no registry/CI round-trip. Requires a reboot afterward to
# actually boot into it; `bootc rollback` undoes it if something's wrong.

# Switch the running deployment to the image `build` just produced.
[group('Build')]
switch-local tag="latest":
    #!/usr/bin/env bash
    set -euo pipefail
    if ! sudo podman image exists localhost/kyth:{{ tag }}; then
        echo "localhost/kyth:{{ tag }} not found in root's container storage — run 'just build' first." >&2
        exit 1
    fi
    sudo bootc switch --transport containers-storage localhost/kyth:{{ tag }}
    echo
    echo "Staged. Reboot to apply: sudo systemctl reboot"
    echo "To go back to the tracked channel later: sudo bootc switch ghcr.io/mrtrick37/kyth:testing"

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
