export image_name := env("IMAGE_NAME", "kyth") # output image name, usually same as repo name, change as needed
export default_tag := env("DEFAULT_TAG", "latest")
export bib_image := env("BIB_IMAGE", "quay.io/centos-bootc/bootc-image-builder:latest")

alias build-vm := build-qcow2
alias run-vm := run-vm-qcow2

[private]
default:
    @just --list

# Check Just Syntax
[group('Just')]
check:
    #!/usr/bin/bash
    find . -type f -name "*.just" | while read -r file; do
    	echo "Checking syntax: $file"
    	just --unstable --fmt --check -f $file
    done
    echo "Checking syntax: Justfile"
    just --unstable --fmt --check -f Justfile

# Check Dockerfile frontend/build rules without requiring the local kyth-base image.
[group('Build')]
check-dockerfile check_base_image="ghcr.io/ublue-os/kinoite-main:44":
    #!/usr/bin/env bash
    set -euo pipefail
    if ! id -nG | grep -qw docker; then
        exec sg docker -c "just check-dockerfile '{{ check_base_image }}'"
    fi
    docker buildx build --check \
        --build-arg BASE_IMAGE={{ check_base_image }} \
        .

# Run Python unit tests.
[group('Quality')]
test:
    python3 -m unittest discover -s tests

# Fix Just Syntax
[group('Just')]
fix:
    #!/usr/bin/bash
    find . -type f -name "*.just" | while read -r file; do
    	echo "Checking syntax: $file"
    	just --unstable --fmt -f $file
    done
    echo "Checking syntax: Justfile"
    just --unstable --fmt -f Justfile || { exit 1; }

# Clean Repo
[group('Utility')]
clean:
    #!/usr/bin/bash
    set -eoux pipefail
    rm -rf _build* *_build*
    rm -f previous.manifest.json
    rm -f changelog.md
    rm -f output.env
    rm -rf output

# Sudo Clean Repo
[group('Utility')]
[private]
sudo-clean:
    just sudoif just clean

# Show a disk-usage summary: Docker images, build cache, and output/ ISOs
[group('Utility')]
disk-usage:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "── Docker ────────────────────────────────────────────────────────────────"
    docker system df
    echo ""
    echo "── Output ISOs ───────────────────────────────────────────────────────────"
    find output -name "*.iso" -o -name "*.qcow2" -o -name "*.raw" 2>/dev/null \
        | sort | xargs -r du -sh 2>/dev/null || echo "(none)"
    echo ""
    echo "── /var/tmp kyth-live build dirs ─────────────────────────────────────────"
    find /var/tmp -maxdepth 1 \( -name "kyth-live.*" -o -name "kyth-titanoboa.*" \) -exec du -sh {} \; 2>/dev/null || echo "(none)"

# Set up a Kali Linux security toolbox via the shipped KythOS ujust recipe.
[group('Utility')]
setup-kali-box tools="headless":
    #!/usr/bin/env bash
    set -euo pipefail
    exec just --justfile build_files/just/kyth.just setup-kali-box "{{ tools }}"

# Export Kali Linux GUI apps via the shipped KythOS ujust recipe.
[group('Utility')]
export-kali-apps:
    #!/usr/bin/env bash
    set -euo pipefail
    exec just --justfile build_files/just/kyth.just export-kali-apps

# Refresh the auto-generated README project snapshot section.
[group('Utility')]
sync-readme:
    #!/usr/bin/env bash
    set -euo pipefail
    ./build_files/scripts/update-readme-snapshot.sh

# Install tracked git hooks for automatic README snapshot and commit message helpers.
[group('Utility')]
install-git-hooks:
    #!/usr/bin/env bash
    set -euo pipefail
    git config core.hooksPath .githooks
    chmod +x .githooks/pre-commit .githooks/pre-push .githooks/prepare-commit-msg build_files/scripts/update-readme-snapshot.sh
    echo "Git hooks installed via core.hooksPath=.githooks"

# Remove old output ISOs — keeps only the current live ISO and current BIB ISO.
# Deletes: output/previous-built-iso/, output/archive/, stale manifest backups.
[group('Utility')]
clean-output:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Cleaning stale output artefacts..."
    sudo rm -rf output/previous-built-iso output/archive 2>/dev/null || true
    sudo rm -f  output/manifest-iso.json.bak 2>/dev/null || true
    sudo chown -R "$(id -u):$(id -g)" output/ 2>/dev/null || true
    echo "Remaining output files:"
    find output -name "*.iso" -o -name "*.qcow2" -o -name "*.raw" 2>/dev/null \
        | sort | xargs -r du -sh 2>/dev/null || echo "(none)"

# Prune Docker build cache and dangling (unreferenced) image layers.
# Keeps named images such as localhost/kyth:latest and kyth-live:build.
# Run after a build to recover the reclaimable space shown in 'just disk-usage'.
[group('Utility')]
clean-docker:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Pruning Docker build cache..."
    docker builder prune -f
    echo ""
    echo "Pruning dangling image layers..."
    docker image prune -f
    echo ""
    docker system df

# Reclaim space specifically for live ISO dev loops.
# Removes stale kyth-live images/tags, prunes build cache/volumes,
# and deletes temporary VM disk and build directories.
[group('Utility')]
prune-live-dev:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "── Removing stale kyth-live images ──────────────────────────────────────"
    docker images \
        | awk 'NR>1 {print $1":"$2}' \
        | grep '^kyth-live:' \
        | xargs -r docker rmi -f || true

    echo ""
    echo "── Pruning Docker cache/volumes ──────────────────────────────────────────"
    docker builder prune -af || true
    docker image prune -af || true
    docker volume prune -f || true

    echo ""
    echo "── Removing stale VM/build temp artefacts ───────────────────────────────"
    find /tmp -maxdepth 1 -type f -name 'kyth-live-test.qcow2' -delete || true
    find /var/tmp -maxdepth 2 -type f -name 'kyth-live-test.qcow2' -delete || true
    find /tmp -maxdepth 1 -type d -name 'kyth-vm-share-*' -exec rm -rf {} + || true
    # kyth-titanoboa.* dirs are written by rootful podman — remove with sudo.
    sudo find /var/tmp -maxdepth 1 -type d \( -name 'kyth-live.*' -o -name 'kyth-titanoboa.*' \) -exec rm -rf {} + || true

    echo ""
    echo "── Post-cleanup summary ───────────────────────────────────────────────────"
    df -h /tmp /var || true
    docker system df || true

# Full local cleanup: stale outputs + Docker cache.
# Does NOT remove localhost/kyth:latest or named upstream/base images
# since those are needed to build.
[group('Utility')]
clean-all: clean-output clean-docker

# Nuclear purge: reclaim maximum disk space.
# Removes ALL _build* temp dirs, old ISOs, stale /var/tmp build dirs,
# dangling Docker/Podman image layers, and Docker build cache.
# Keeps: current output/bootiso, output/live-iso, and all named images.
[group('Utility')]
purge:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "── Stale _build* temp dirs in project root ───────────────────────────────"
    shopt -s nullglob
    build_dirs=( _build* )
    if [[ ${#build_dirs[@]} -gt 0 ]]; then
        sudo rm -rf "${build_dirs[@]}"
        printf '  removed: %s\n' "${build_dirs[@]}"
    else
        echo "  (none)"
    fi

    echo ""
    echo "── /var/tmp kyth-live.* / kyth-titanoboa.* build dirs ───────────────────"
    if sudo find /var/tmp -maxdepth 1 \( -name "kyth-live.*" -o -name "kyth-titanoboa.*" \) -print -exec rm -rf {} + 2>/dev/null | grep -q .; then
        echo "  Done"
    else
        echo "  (none)"
    fi

    echo ""
    echo "── Old output artefacts (previous-built-iso, archive, manifest backups) ──"
    sudo rm -rf output/previous-built-iso output/archive 2>/dev/null || true
    sudo rm -f  output/manifest-iso.json.bak 2>/dev/null || true
    sudo chown -R "$(id -u):$(id -g)" output/ 2>/dev/null || true
    echo "  Done"

    echo ""
    echo "── Docker build cache ────────────────────────────────────────────────────"
    docker builder prune -f

    echo ""
    echo "── Docker dangling image layers ──────────────────────────────────────────"
    docker image prune -f

    echo ""
    echo "── Podman dangling image layers ──────────────────────────────────────────"
    if command -v podman &>/dev/null; then
        podman image prune -f
    else
        echo "  (podman not found)"
    fi

    echo ""
    echo "── Result ────────────────────────────────────────────────────────────────"
    df -h "$(pwd)"

# Safely remove local build temp dirs and fix ownership of output/
[group('Utility')]
cleanup:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "This will remove any _build-bib.* directories in ${PWD} and fix ownership of output/."
    if [[ "${AUTO_CONFIRM:-}" != "true" ]]; then
        read -r -p "Proceed? [y/N]: " ans
        if [[ ! "${ans}" =~ ^[Yy]$ ]]; then
            echo "Aborted by user."; exit 1
        fi
    fi

    if ls _build-bib.* 1> /dev/null 2>&1; then
        echo "Removing _build-bib.*..."
        sudo rm -rf _build-bib.* || true
    else
        echo "No _build-bib.* directories found."
    fi

    if [ -d output ]; then
        echo "Fixing ownership of output/ to current user..."
        sudo chown -R "$(id -u):$(id -g)" output/ || true
    fi

    echo "Cleanup complete."

# sudoif bash function
[group('Utility')]
[private]
sudoif command *args:
    #!/usr/bin/bash
    function sudoif(){
        if [[ "${UID}" -eq 0 ]]; then
            "$@"
        elif [[ "$(command -v sudo)" && -n "${SSH_ASKPASS:-}" ]] && [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
            /usr/bin/sudo --askpass "$@" || exit 1
        elif [[ "$(command -v sudo)" ]]; then
            /usr/bin/sudo "$@" || exit 1
        else
            exit 1
        fi
    }
    sudoif {{ command }} {{ args }}

# Build the base image from build_base/.
# Override the upstream with: just build-base ghcr.io/ublue-os/kinoite-main:44 fedora
[group('Build')]
build-base base_image="ghcr.io/ublue-os/kinoite-main:44" kernel_flavor="fedora":
    #!/usr/bin/env bash
    # Ensure docker group is active in this session.
    # id -nG (no arg) reads the current process's live group list; id -nG "$USER"
    # reads /etc/group and would show docker even before the session is refreshed.
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
        # Non-fatal: cosign bundle format changes between versions can cause
        # spurious "empty key" failures even when the image is legitimate.
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

# Build the full KythOS image (packages → GE-Proton → upgrades → Mesa → thirdparty → sysconfig → Secure Boot → branding).
# Requires build-base to have run first.
# Uses --cache-from the CI registry cache if credentials are available (silently ignored if not).
#
# Secure Boot signing (optional):
#   Export MOK_KEY with the PEM private key contents, or point MOK_KEY_FILE at
#   the key file, before building:
#     export MOK_KEY_FILE=~/.config/kyth/secureboot/kyth-secureboot.key
#     # or: export MOK_KEY=$(cat ~/path/to/kyth-mok-PRIVATE.key)
# just build
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

    # Fetch GE-Proton and the five thirdparty tool versions in parallel so the
    # total wait is the slowest single request instead of the sum of all requests.
    # resolve-versions.sh is shared with CI (.github/workflows/build.yml).
    _ge_tmp=$(mktemp) _tp_tmp=$(mktemp)
    ( ./build_files/scripts/resolve-versions.sh ge-proton > "${_ge_tmp}" ) &
    ( ./build_files/scripts/resolve-versions.sh thirdparty-hash > "${_tp_tmp}" ) &
    wait
    GE_PROTON_VER=$(cat "${_ge_tmp}"); rm -f "${_ge_tmp}"
    THIRDPARTY_VERSIONS_HASH=$(cat "${_tp_tmp}"); rm -f "${_tp_tmp}"
    echo "GE-Proton: ${GE_PROTON_VER:-latest}"
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
        --build-arg GE_PROTON_VER="${GE_PROTON_VER}" \
        --build-arg THIRDPARTY_VERSIONS_HASH="${THIRDPARTY_VERSIONS_HASH}" \
        --build-arg BUILD_DATE="$(date +%Y-%m-%d)" \
        --build-arg SECUREBOOT_SIGNING_REQUESTED="${SECUREBOOT_SIGNING_REQUESTED}" \
        "${MOK_SECRET_ARG[@]}" \
        --cache-from "type=registry,ref=${REGISTRY}:buildcache-final-${CACHE_BRANCH}-fedora" \
        --tag localhost/kyth:latest \
        --load \
        .

# Command: _rootful_load_image
# Description: Ensures the target image is available to the root Docker daemon.
#              If already running as root/sudo, exits immediately (image is already accessible).
#              Otherwise, checks if the image exists in the user Docker store and, if so,
#              copies it to the root store via docker image save/load. Falls back to pulling
#              from the registry if the image is not found locally.
#
# Parameters:
#   $target_image - The name of the target image to be loaded or pulled.
#   $tag - The tag of the target image to be loaded or pulled. Default is 'default_tag'.

_rootful_load_image $target_image=image_name $tag=default_tag:
    #!/usr/bin/bash
    set -eoux pipefail

    # Check if already running as root or under sudo
    if [[ -n "${SUDO_USER:-}" || "${UID}" -eq "0" ]]; then
        echo "Already root or running under sudo; image is already accessible to the root Docker daemon."
        exit 0
    fi

    # Try to resolve the image tag using docker inspect
    set +e
        resolved_tag=$(docker inspect --format '{{ "{{.RepoTags}}" }}' "${target_image}:${tag}" | jq -r '.[0]')
    return_code=$?
    set -e

        USER_IMG_ID=$(docker images --filter reference="${target_image}:${tag}" --format "'{{ '{{.ID}}' }}'")

    if [[ $return_code -eq 0 ]]; then
        # If the image is found, load it into rootful docker
        ID=$(just sudoif docker images --filter reference="${target_image}:${tag}" --format "'{{ '{{.ID}}' }}'")
        if [[ "$ID" != "$USER_IMG_ID" ]]; then
            # If the image ID is not found or different from user, copy the image from user docker to root docker
            COPYTMP=$(mktemp -p /var/tmp -d -t _build_docker_scp.XXXXXXXXXX)
            just sudoif TMPDIR=${COPYTMP} docker image save "${target_image}:${tag}" | docker image load
            rm -rf "${COPYTMP}"
        fi
    else
        # If the image is not found, pull it from the repository
        just sudoif docker pull "${target_image}:${tag}"
    fi

# Build a bootc bootable image using Bootc Image Builder (BIB)
# Converts a container image to a bootable image
# Parameters:
#   target_image: The name of the image to build (ex. localhost/fedora)
#   tag: The tag of the image to build (ex. latest)
#   type: The type of image to build (ex. qcow2, raw, iso)
#   config: The configuration file to use for the build (default: disk_config/disk.toml)

# Example: just _rebuild-bib localhost/fedora latest qcow2 disk_config/disk.toml
_build-bib $target_image $tag $type $config: (_rootful_load_image target_image tag)
    #!/usr/bin/env bash
    set -euo pipefail

    args="--type ${type} "
    args+="--use-librepo=True "
    args+="--rootfs=btrfs "

    # Create build temp under $TMPDIR (fallback /var/tmp) so repository root isn't filled
    TMPDIR=${TMPDIR:-/var/tmp}
    BUILDTMP=$(mktemp -p "${TMPDIR}" -d -t _build-bib.XXXXXXXXXX)
    BUILDDIR=${PWD}

    # Single EXIT trap for all cleanup — bash keeps only the last EXIT trap, so
    # registering a second one later would silently drop the BUILDTMP cleanup.
    REG_NAME="kyth-bib-registry-$$"
    _bib_cleanup() {
        docker stop "${REG_NAME}" 2>/dev/null || true
        sudo rm -rf "${BUILDTMP}" >/dev/null 2>&1 || true
    }
    trap _bib_cleanup EXIT

        # Allow providing the repo GPG key(s) in the workspace so dnf inside the builder
        # can access file:///etc/pki/rpm-gpg/RPM-GPG-KEY-terra43-mesa (or other keys).
        KEY_MOUNT=""
        if [[ -f "${BUILDDIR}/RPM-GPG-KEY-terra43-mesa" ]]; then
            KEY_MOUNT="-v ${BUILDDIR}/RPM-GPG-KEY-terra43-mesa:/etc/pki/rpm-gpg/RPM-GPG-KEY-terra43-mesa:ro"
        elif [[ -d "${BUILDDIR}/pki/rpm-gpg" ]]; then
            KEY_MOUNT="-v ${BUILDDIR}/pki/rpm-gpg:/etc/pki/rpm-gpg:ro"
        fi

        # Attempt to extract product metadata from the image's OCI labels and pass
        # them to bootc/lorax so lorax receives a valid product.name/product.version.
        # Provide sensible defaults so installer UI shows KythOS even when labels
        # are missing from the base image.
        PRODUCT_NAME="KythOS"
        PRODUCT_VERSION="44"
        set +e
        labels_json=$(docker inspect "${target_image}:${tag}" 2>/dev/null | jq -c '.[0].Config.Labels // {}' 2>/dev/null || true)
        set -e
        if [[ -n "${labels_json}" && "${labels_json}" != "null" ]]; then
            PRODUCT_NAME=$(echo "${labels_json}" | jq -r '."org.opencontainers.image.title" // empty' || true)
            PRODUCT_VERSION=$(echo "${labels_json}" | jq -r '."org.opencontainers.image.version" // empty' || true)
        fi
        # Do not pass --version to bootc-image-builder (it treats --version as a boolean).
        # We patch generated manifest files below to set product/version when available.

        # Enable debug logging from bootc-image-builder to surface why lorax product/version are empty
        args+="--log-level=debug "

        # BIB needs to pull the image from a registry. Push to a temporary local
        # registry so BIB can reach it via --net=host without touching the image store.
        # Unique name + free-port scan so concurrent builds don't collide.
        REG_PORT=5099
        while grep -q ":${REG_PORT}\b" <<< "$(ss -tunal)"; do
            REG_PORT=$(( REG_PORT + 1 ))
        done
        docker run -d --rm --name "${REG_NAME}" \
            -p "127.0.0.1:${REG_PORT}:5000" docker.io/library/registry:2
        BIB_IMAGE_REF="localhost:${REG_PORT}/${target_image##*/}:${tag}"
        docker tag "${target_image}:${tag}" "${BIB_IMAGE_REF}"
        docker push "${BIB_IMAGE_REF}"

        mkdir -p "${BUILDTMP}/containers"
        sudo docker run \
            --rm \
            --privileged \
            --pull=newer \
            --net=host \
            --security-opt label=type:unconfined_t \
            $KEY_MOUNT \
            -v $(pwd)/${config}:/config.toml:ro \
            -v $BUILDTMP:/output \
            -v "${BUILDTMP}/containers:/var/lib/containers" \
            "${bib_image}" \
            ${args} \
            "${BIB_IMAGE_REF}"

        docker stop "${REG_NAME}" 2>/dev/null || true

    mkdir -p output
    # If bootc produced a manifest but lorax product/version are empty, patch them
    if sudo test -d "$BUILDTMP"; then
        for mf in $BUILDTMP/manifest*.json; do
            if sudo test -f "$mf"; then
                    # Run jq under sudo with variables expanded by the current shell to avoid complex shell-quoting.
                    sudo jq --arg pname "${PRODUCT_NAME}" --arg pver "${PRODUCT_VERSION}" \
                        '(.pipelines[]?.stages[]? |= ( if .type=="org.osbuild.lorax-script" then (.options.product.name = $pname) | (.options.product.version = $pver) | (.options.branding.release = ($pname + " " + $pver)) else . end ))' "$mf" > "$mf.tmp" || true
                    sudo mv -f "$mf.tmp" "$mf" || true
            fi
        done
    fi
    # Rotate previous builds: keep last two
    sudo mkdir -p output/previous-built-iso
    if sudo test -d output/previous-built-iso/1; then
        sudo rm -rf output/previous-built-iso/2 || true
        sudo mv output/previous-built-iso/1 output/previous-built-iso/2 || true
    fi
    if sudo test -d output/bootiso; then
        sudo mv output/bootiso output/previous-built-iso/1 || true
    fi

    # Move new build output into place
    sudo mv -f $BUILDTMP/* output/ || true
    # Rename standard install ISO to a consistent KythOS filename
    if sudo test -f output/bootiso/install.iso; then
        sudo mv -f output/bootiso/install.iso output/bootiso/kyth-installer.iso || true
    fi
    sudo rmdir $BUILDTMP || true
    sudo chown -R $USER:$USER output/

    # Print absolute path to produced ISO if present (helps CI and users find artifact)
    if sudo test -f output/bootiso/kyth-installer.iso; then
        ISO_PATH=$(readlink -f output/bootiso/kyth-installer.iso)
        echo "Produced ISO: ${ISO_PATH}"
    fi

# Build a QCOW2 virtual machine image
[group('Build Virtual Machine Image')]
build-qcow2 $target_image=("localhost/" + image_name) $tag=default_tag: && (_build-bib target_image tag "qcow2" "disk_config/disk.toml")

# Build a RAW virtual machine image
[group('Build Virtual Machine Image')]
build-raw $target_image=("localhost/" + image_name) $tag=default_tag: && (_build-bib target_image tag "raw" "disk_config/disk.toml")

# Build an ISO virtual machine image
[group('Build Virtual Machine Image')]
build-iso $target_image=("localhost/" + image_name) $tag=default_tag: && (_build-bib target_image tag "iso" "disk_config/iso.toml")

# Build a live ISO with the KythOS web installer. The live desktop is based on
# the same KythOS image that will be installed, then pulls that image from the
# registry at install time via bootc install to-disk.
# Build the live ISO from the given source tag.
# Pass source_tag to target a different branch: just build-live-iso testing
[group('Build Virtual Machine Image')]
build-live-iso source_tag="latest":
    #!/usr/bin/env bash
    set -euo pipefail
    SOURCE_TAG={{ source_tag }} bash build_files/build-live-iso.sh

# Rebuild the live ISO payload and assemble it with Titanoboa.
[group('Build Virtual Machine Image')]
rebuild-live-iso source_tag="latest":
    #!/usr/bin/env bash
    set -euo pipefail
    SOURCE_TAG={{ source_tag }} bash build_files/build-live-iso.sh

# Build a live ISO from localhost/kyth:latest for local QEMU testing.
[group('Build Virtual Machine Image')]
rebuild-live-iso-local:
    #!/usr/bin/env bash
    set -euo pipefail
    just build
    SOURCE_TAG=local INSTALLER_BASE_IMAGE=localhost/kyth:latest bash build_files/build-live-iso.sh

# Build the local embedded ISO and boot it in native QEMU with a fresh disk.
[group('Run Virtual Machine')]
run-live-iso-native-local:
    #!/usr/bin/env bash
    set -euo pipefail
    just rebuild-live-iso-local
    LIVE_ISO_VM_RESET=1 just run-live-iso-native local

# Boot the live ISO in a VM (BIOS, web UI at http://localhost:PORT).
# Uses the dedicated artifact name from build-live-iso.sh:
# output/live-iso/kyth-live-<tag>.iso
[group('Run Virtual Machine')]
run-live-iso source_tag="latest":
    #!/usr/bin/bash
    set -eoux pipefail

    image_file="output/live-iso/kyth-live-{{ source_tag }}.iso"
    if [[ ! -f "${image_file}" ]]; then
        just build-live-iso {{ source_tag }}
    fi

    port=8006
    while grep -q ":${port}" <<< $(ss -tunalp); do
        port=$(( port + 1 ))
    done
    echo "Using Port: ${port}"
    echo "Connect to http://localhost:${port}"

    (sleep 30 && xdg-open http://localhost:"$port") &
    docker run \
        --rm --privileged \
        --pull missing \
        --publish "127.0.0.1:${port}:8006" \
        --env "CPU_CORES=4" \
        --env "RAM_SIZE=8G" \
        --env "DISK_SIZE=64G" \
        --env "GPU=Y" \
        --device=/dev/kvm \
        --volume "${PWD}/${image_file}:/boot.iso" \
        docker.io/qemux/qemu

# Boot the live ISO directly in native QEMU (SPICE window, better clipboard).
# Useful when noVNC copy/paste is awkward while collecting installer logs.
[group('Run Virtual Machine')]
run-live-iso-native source_tag="latest":
    #!/usr/bin/bash
    set -eoux pipefail

    image_file="output/live-iso/kyth-live-{{ source_tag }}.iso"
    if [[ ! -f "${image_file}" ]]; then
        just build-live-iso {{ source_tag }}
    fi

    disk_dir="/var/tmp/kyth-vm-disks-${USER}"
    mkdir -p "${disk_dir}"
    disk_img="${disk_dir}/kyth-live-test.qcow2"
    ovmf_vars="${disk_dir}/ovmf_vars.fd"

    # Optional one-shot reset for a clean VM install target.
    if [[ "${LIVE_ISO_VM_RESET:-0}" == "1" ]]; then
        rm -f "${disk_img}" "${ovmf_vars}"
    fi

    # Fail fast before booting when host free space is too low for install writes.
    avail_bytes=$(df --output=avail -B1 "${disk_dir}" | tail -n 1 | tr -d '[:space:]')
    min_bytes=$((30 * 1024 * 1024 * 1024))
    if [[ "${avail_bytes}" -lt "${min_bytes}" ]]; then
        echo "Insufficient free space for live ISO VM disk writes on $(df --output=target "${disk_dir}" | tail -n 1)."
        echo "Need >= 30 GiB free, found $((avail_bytes / 1024 / 1024 / 1024)) GiB."
        echo "Run: just prune-live-dev"
        exit 1
    fi

    if [[ ! -f "${disk_img}" ]]; then
        qemu-img create -f qcow2 -o preallocation=metadata,lazy_refcounts=on "${disk_img}" 64G
    fi

    # UEFI firmware: bootc install to-disk writes an EFI System Partition and
    # calls efibootmgr to add a boot entry — OVMF gives QEMU a real UEFI
    # environment identical to bare AMD hardware.  The NVRAM file (ovmf_vars)
    # persists across QEMU sessions.  The QEMU devices below also give the
    # installed disk bootindex=1 and the live ISO bootindex=2, so a blank disk
    # falls through to the installer but an installed disk wins after reboot.
    # LIVE_ISO_VM_RESET=1 wipes both disk and NVRAM for a clean reinstall.
    # Install OVMF with: sudo dnf install edk2-ovmf
    _ovmf_args=()
    for _ovmf_code in \
        /usr/share/edk2/ovmf/OVMF_CODE.fd \
        /usr/share/OVMF/OVMF_CODE.fd; do
        if [[ -f "${_ovmf_code}" ]]; then
            if [[ ! -f "${ovmf_vars}" ]]; then
                _ovmf_tmpl="${_ovmf_code/CODE/VARS}"
                [[ -f "${_ovmf_tmpl}" ]] && cp "${_ovmf_tmpl}" "${ovmf_vars}"
            fi
            if [[ -f "${ovmf_vars}" ]]; then
                _ovmf_args=(
                    -drive "if=pflash,format=raw,unit=0,readonly=on,file=${_ovmf_code}"
                    -drive "if=pflash,format=raw,unit=1,file=${ovmf_vars}"
                )
                echo "==> UEFI boot: ${_ovmf_code}  NVRAM: ${ovmf_vars}"
            fi
            break
        fi
    done
    [[ ${#_ovmf_args[@]} -eq 0 ]] && echo "==> BIOS boot (install edk2-ovmf for UEFI)"

    # Host/guest shared folder for collecting logs from the VM.
    # Use /var/tmp consistently to avoid tmpfs quota issues seen under /tmp.
    share_dir="/var/tmp/kyth-vm-share-${USER}"
    mkdir -p "${share_dir}"
    serial_log="${share_dir}/qemu-serial.log"
    qemu_log="${share_dir}/qemu-debug.log"
    rm -f "${serial_log}" "${qemu_log}"
    echo "Host shared folder: ${share_dir}"
    echo "Serial log on host: ${serial_log}"
    echo "QEMU debug log on host: ${qemu_log}"
    echo "In VM, run: sudo mkdir -p /var/mnt/hostshare && sudo mount -t 9p -o trans=virtio,version=9p2000.L,cache=none hostshare /var/mnt/hostshare"

    _qemu_devices="$(qemu-system-x86_64 -device help 2>/dev/null || true)"
    if [[ "${_qemu_devices}" == *'name "qxl-vga"'* ]]; then
        _video_args=(-device qxl-vga)
        echo "==> QEMU video: qxl-vga"
    else
        _video_args=(-device virtio-vga)
        echo "==> QEMU video: virtio-vga (qxl-vga unavailable)"
    fi

    qemu-system-x86_64 \
        -enable-kvm \
        -cpu host \
        -smp 4 \
        -m 8G \
        -machine q35 \
        "${_ovmf_args[@]}" \
        -device ich9-ahci,id=ahci \
        -drive "if=none,id=liveiso,format=raw,media=cdrom,readonly=on,file=${image_file}" \
        -device ide-cd,bus=ahci.0,drive=liveiso,bootindex=2 \
        -drive "if=none,id=systemdisk,file=${disk_img},format=qcow2" \
        -device virtio-blk-pci,drive=systemdisk,bootindex=1 \
        "${_video_args[@]}" \
        -display none \
        -spice port=5931,disable-ticketing=on,disable-copy-paste=off,disable-agent-file-xfer=off \
        -device virtio-serial \
        -chardev spicevmc,id=vdagent,name=vdagent \
        -device virtserialport,chardev=vdagent,name=com.redhat.spice.0 \
        -device virtio-net-pci,netdev=net0 \
        -netdev user,id=net0,hostfwd=tcp::2223-:22 \
        -device virtio-rng-pci \
        -device qemu-xhci \
        -device usb-tablet \
        -d guest_errors \
        -serial "file:${serial_log}" \
        -D "${qemu_log}" \
        -virtfs local,path="${share_dir}",mount_tag=hostshare,security_model=mapped-xattr,id=hostshare \
        &
    QEMU_PID=$!
    sleep 2
    rv_cache="/var/tmp/kyth-remote-viewer-${USER}"
    mkdir -p "${rv_cache}"
    env XDG_CACHE_HOME="${rv_cache}" TMPDIR="/var/tmp" remote-viewer spice://localhost:5931 &
    wait "${QEMU_PID}"

# Alternate live ISO native run target that keeps legacy boot behavior (-no-reboot).
# Useful for A/B testing reboot-path issues against the reboot-friendly target above.
[group('Run Virtual Machine')]
run-live-iso-native-legacy source_tag="latest":
    #!/usr/bin/bash
    set -eoux pipefail

    image_file="output/live-iso/kyth-live-{{ source_tag }}.iso"
    if [[ ! -f "${image_file}" ]]; then
        just build-live-iso {{ source_tag }}
    fi

    disk_dir="/var/tmp/kyth-vm-disks-${USER}"
    mkdir -p "${disk_dir}"
    disk_img="${disk_dir}/kyth-live-test.qcow2"
    ovmf_vars="${disk_dir}/ovmf_vars.fd"

    if [[ "${LIVE_ISO_VM_RESET:-0}" == "1" ]]; then
        rm -f "${disk_img}" "${ovmf_vars}"
    fi

    avail_bytes=$(df --output=avail -B1 "${disk_dir}" | tail -n 1 | tr -d '[:space:]')
    min_bytes=$((30 * 1024 * 1024 * 1024))
    if [[ "${avail_bytes}" -lt "${min_bytes}" ]]; then
        echo "Insufficient free space for live ISO VM disk writes on $(df --output=target "${disk_dir}" | tail -n 1)."
        echo "Need >= 30 GiB free, found $((avail_bytes / 1024 / 1024 / 1024)) GiB."
        echo "Run: just prune-live-dev"
        exit 1
    fi

    if [[ ! -f "${disk_img}" ]]; then
        qemu-img create -f qcow2 -o preallocation=metadata,lazy_refcounts=on "${disk_img}" 64G
    fi

    _ovmf_args=()
    for _ovmf_code in \
        /usr/share/edk2/ovmf/OVMF_CODE.fd \
        /usr/share/OVMF/OVMF_CODE.fd; do
        if [[ -f "${_ovmf_code}" ]]; then
            if [[ ! -f "${ovmf_vars}" ]]; then
                _ovmf_tmpl="${_ovmf_code/CODE/VARS}"
                [[ -f "${_ovmf_tmpl}" ]] && cp "${_ovmf_tmpl}" "${ovmf_vars}"
            fi
            if [[ -f "${ovmf_vars}" ]]; then
                _ovmf_args=(
                    -drive "if=pflash,format=raw,unit=0,readonly=on,file=${_ovmf_code}"
                    -drive "if=pflash,format=raw,unit=1,file=${ovmf_vars}"
                )
                echo "==> UEFI boot: ${_ovmf_code}  NVRAM: ${ovmf_vars}"
            fi
            break
        fi
    done
    [[ ${#_ovmf_args[@]} -eq 0 ]] && echo "==> BIOS boot (install edk2-ovmf for UEFI)"

    share_dir="/var/tmp/kyth-vm-share-${USER}"
    mkdir -p "${share_dir}"
    serial_log="${share_dir}/qemu-serial.log"
    qemu_log="${share_dir}/qemu-debug.log"
    rm -f "${serial_log}" "${qemu_log}"
    echo "Host shared folder: ${share_dir}"
    echo "Serial log on host: ${serial_log}"
    echo "QEMU debug log on host: ${qemu_log}"
    echo "In VM, run: sudo mkdir -p /var/mnt/hostshare && sudo mount -t 9p -o trans=virtio,version=9p2000.L,cache=none hostshare /var/mnt/hostshare"

    _qemu_devices="$(qemu-system-x86_64 -device help 2>/dev/null || true)"
    if [[ "${_qemu_devices}" == *'name "qxl-vga"'* ]]; then
        _video_args=(-device qxl-vga)
        echo "==> QEMU video: qxl-vga"
    else
        _video_args=(-device virtio-vga)
        echo "==> QEMU video: virtio-vga (qxl-vga unavailable)"
    fi

    qemu-system-x86_64 \
        -enable-kvm \
        -cpu host \
        -smp 4 \
        -m 8G \
        -machine q35 \
        "${_ovmf_args[@]}" \
        -no-reboot \
        -no-shutdown \
        -cdrom "${image_file}" \
        -boot order=d \
        -drive file="${disk_img}",if=virtio,format=qcow2 \
        "${_video_args[@]}" \
        -display none \
        -spice port=5932,disable-ticketing=on,disable-copy-paste=off,disable-agent-file-xfer=off \
        -device virtio-serial \
        -chardev spicevmc,id=vdagent,name=vdagent \
        -device virtserialport,chardev=vdagent,name=com.redhat.spice.0 \
        -device virtio-net-pci,netdev=net0 \
        -netdev user,id=net0,hostfwd=tcp::2224-:22 \
        -device virtio-rng-pci \
        -device qemu-xhci \
        -device usb-tablet \
        -d guest_errors \
        -serial "file:${serial_log}" \
        -D "${qemu_log}" \
        -virtfs local,path="${share_dir}",mount_tag=hostshare,security_model=mapped-xattr,id=hostshare \
        &
    QEMU_PID=$!
    sleep 2
    rv_cache="/var/tmp/kyth-remote-viewer-${USER}"
    mkdir -p "${rv_cache}"
    env XDG_CACHE_HOME="${rv_cache}" TMPDIR="/var/tmp" remote-viewer spice://localhost:5932 &
    wait "${QEMU_PID}"

# Run a virtual machine with the specified image type and configuration
_run-vm $target_image $tag $type $config:
    #!/usr/bin/bash
    set -eoux pipefail

    # Determine the image file based on the type
    image_file="output/${type}/disk.${type}"
    if [[ $type == iso ]]; then
        image_file="output/bootiso/kyth-installer.iso"
    fi

    # Build the image if it does not exist
    if [[ ! -f "${image_file}" ]]; then
        just "build-${type}" "$target_image" "$tag"
    fi

    # Determine an available port to use
    port=8006
    while grep -q ":${port}" <<< $(ss -tunalp); do
        port=$(( port + 1 ))
    done
    echo "Using Port: ${port}"
    echo "Connect to http://localhost:${port}"

    # Set up the arguments for running the VM
    run_args=()
    run_args+=(--rm --privileged)
    run_args+=(--pull=newer)
    run_args+=(--publish "127.0.0.1:${port}:8006")
    run_args+=(--env "CPU_CORES=4")
    run_args+=(--env "RAM_SIZE=8G")
    run_args+=(--env "DISK_SIZE=64G")
    run_args+=(--env "TPM=Y")
    run_args+=(--env "GPU=Y")
    run_args+=(--device=/dev/kvm)
    run_args+=(--volume "${PWD}/${image_file}":"/boot.${type}")
    run_args+=(docker.io/qemux/qemu)

    # Run the VM and open the browser to connect
    (sleep 30 && xdg-open http://localhost:"$port") &
    docker run "${run_args[@]}"

# Run a virtual machine from a QCOW2 image
[group('Run Virtual Machine')]
run-vm-qcow2 $target_image=("localhost/" + image_name) $tag=default_tag: && (_run-vm target_image tag "qcow2" "disk_config/disk.toml")

# Run a virtual machine from a RAW image
[group('Run Virtual Machine')]
run-vm-raw $target_image=("localhost/" + image_name) $tag=default_tag: && (_run-vm target_image tag "raw" "disk_config/disk.toml")

# Run a virtual machine from an ISO
[group('Run Virtual Machine')]
run-vm-iso $target_image=("localhost/" + image_name) $tag=default_tag: && (_run-vm target_image tag "iso" "disk_config/iso.toml")

# Run a virtual machine using systemd-vmspawn
[group('Run Virtual Machine')]
spawn-vm rebuild="0" type="qcow2" ram="6G":
    #!/usr/bin/env bash

    set -euo pipefail

    [ "{{ rebuild }}" -eq 1 ] && echo "Rebuilding the ISO" && just build-vm {{ rebuild }} {{ type }}

    systemd-vmspawn \
      -M "bootc-image" \
      --console=gui \
      --cpus=2 \
      --ram=$(echo {{ ram }}| /usr/bin/numfmt --from=iec) \
      --network-user-mode \
      --vsock=false --pass-ssh-key=false \
      -i ./output/**/*.{{ type }}

# Runs shell check on all Bash scripts
lint:
    #!/usr/bin/env bash
    set -eoux pipefail
    # Check if shellcheck is installed
    if ! command -v shellcheck &> /dev/null; then
        echo "shellcheck could not be found. Please install it."
        exit 1
    fi
    # Run shellcheck on all Bash scripts
    /usr/bin/find . -iname "*.sh" -type f -exec shellcheck "{}" ';'

# Runs shfmt on all Bash scripts
format:
    #!/usr/bin/env bash
    set -eoux pipefail
    # Check if shfmt is installed
    if ! command -v shfmt &> /dev/null; then
        echo "shellcheck could not be found. Please install it."
        exit 1
    fi
    # Run shfmt on all Bash scripts
    /usr/bin/find . -iname "*.sh" -type f -exec shfmt --write "{}" ';'

# Preview the installer UI in your browser (no disk changes — safe for dev)
[group('Utility')]
preview-installer:
    #!/usr/bin/env python3
    import sys, threading, time
    sys.path.insert(0, "build_files/kyth-installer")
    from kyth_installer.server import Handler, _Server
    server = _Server(("127.0.0.1", 7777), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("Installer UI → http://127.0.0.1:7777  (Ctrl-C to stop)")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        pass
