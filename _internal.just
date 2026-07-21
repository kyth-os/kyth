# ── Private helpers ──────────────────────────────────────────────────────────
# Imported by Justfile. Not intended for direct invocation.
import "_vars.just"

# sudoif bash function
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

# Find the first free TCP port at or after start_port (checked via `ss`).
[private]
_find-free-port start_port:
    #!/usr/bin/env bash
    set -euo pipefail
    port={{ start_port }}
    while grep -q ":${port}\b" <<< "$(ss -tunal)"; do
        port=$(( port + 1 ))
    done
    echo "${port}"

# Command: _rootful_load_image
# Description: Ensures the target image is available to the root Docker daemon.
[private]
_rootful_load_image $target_image=image_name $tag=default_tag:
    #!/usr/bin/bash
    set -eoux pipefail

    if [[ -n "${SUDO_USER:-}" || "${UID}" -eq "0" ]]; then
        echo "Already root or running under sudo; image is already accessible to the root Docker daemon."
        exit 0
    fi

    set +e
        resolved_tag=$(docker inspect --format '{{ "{{.RepoTags}}" }}' "${target_image}:${tag}" | jq -r '.[0]')
    return_code=$?
    set -e

        USER_IMG_ID=$(docker images --filter reference="${target_image}:${tag}" --format "'{{ '{{.ID}}' }}'")

    if [[ $return_code -eq 0 ]]; then
        ID=$(just sudoif docker images --filter reference="${target_image}:${tag}" --format "'{{ '{{.ID}}' }}'")
        if [[ "$ID" != "$USER_IMG_ID" ]]; then
            COPYTMP=$(mktemp -p /var/tmp -d -t _build_docker_scp.XXXXXXXXXX)
            just sudoif TMPDIR=${COPYTMP} docker image save "${target_image}:${tag}" | docker image load
            rm -rf "${COPYTMP}"
        fi
    else
        just sudoif docker pull "${target_image}:${tag}"
    fi

# Build a bootc bootable image using Bootc Image Builder (BIB)
[private]
_build-bib $target_image $tag $type $config: (_rootful_load_image target_image tag)
    #!/usr/bin/env bash
    set -euo pipefail

    args="--type ${type} "
    args+="--use-librepo=True "
    args+="--rootfs=btrfs "

    TMPDIR=${TMPDIR:-/var/tmp}
    BUILDTMP=$(mktemp -p "${TMPDIR}" -d -t _build-bib.XXXXXXXXXX)
    BUILDDIR=${PWD}

    REG_NAME="kyth-bib-registry-$$"
    _bib_cleanup() {
        docker stop "${REG_NAME}" 2>/dev/null || true
        sudo rm -rf "${BUILDTMP}" >/dev/null 2>&1 || true
    }
    trap _bib_cleanup EXIT

        KEY_MOUNT=""
        if [[ -f "${BUILDDIR}/RPM-GPG-KEY-terra43-mesa" ]]; then
            KEY_MOUNT="-v ${BUILDDIR}/RPM-GPG-KEY-terra43-mesa:/etc/pki/rpm-gpg/RPM-GPG-KEY-terra43-mesa:ro"
        elif [[ -d "${BUILDDIR}/pki/rpm-gpg" ]]; then
            KEY_MOUNT="-v ${BUILDDIR}/pki/rpm-gpg:/etc/pki/rpm-gpg:ro"
        fi

        PRODUCT_NAME="KythOS"
        PRODUCT_VERSION="44"
        set +e
        labels_json=$(docker inspect "${target_image}:${tag}" 2>/dev/null | jq -c '.[0].Config.Labels // {}' 2>/dev/null || true)
        set -e
        if [[ -n "${labels_json}" && "${labels_json}" != "null" ]]; then
            PRODUCT_NAME=$(echo "${labels_json}" | jq -r '."org.opencontainers.image.title" // empty' || true)
            PRODUCT_VERSION=$(echo "${labels_json}" | jq -r '."org.opencontainers.image.version" // empty' || true)
        fi

        args+="--log-level=debug "

        REG_PORT=$(just _find-free-port 5099)
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
    if sudo test -d "$BUILDTMP"; then
        for mf in $BUILDTMP/manifest*.json; do
            if sudo test -f "$mf"; then
                    sudo jq --arg pname "${PRODUCT_NAME}" --arg pver "${PRODUCT_VERSION}" \
                        '(.pipelines[]?.stages[]? |= ( if .type=="org.osbuild.lorax-script" then (.options.product.name = $pname) | (.options.product.version = $pver) | (.options.branding.release = ($pname + " " + $pver)) else . end ))' "$mf" > "$mf.tmp" || true
                    sudo mv -f "$mf.tmp" "$mf" || true
            fi
        done
    fi
    sudo mkdir -p output/previous-built-iso
    if sudo test -d output/previous-built-iso/1; then
        sudo rm -rf output/previous-built-iso/2 || true
        sudo mv output/previous-built-iso/1 output/previous-built-iso/2 || true
    fi
    if sudo test -d output/bootiso; then
        sudo mv output/bootiso output/previous-built-iso/1 || true
    fi

    sudo mv -f $BUILDTMP/* output/ || true
    if sudo test -f output/bootiso/install.iso; then
        sudo mv -f output/bootiso/install.iso output/bootiso/kyth-installer.iso || true
    fi
    sudo rmdir $BUILDTMP || true
    sudo chown -R $USER:$USER output/

    if sudo test -f output/bootiso/kyth-installer.iso; then
        ISO_PATH=$(readlink -f output/bootiso/kyth-installer.iso)
        echo "Produced ISO: ${ISO_PATH}"
    fi
