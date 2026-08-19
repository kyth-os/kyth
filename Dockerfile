
ARG BASE_IMAGE=localhost/kyth-base:stable

# Base Image
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# Override upstream OCI labels so downstream tooling (lorax/bootc) sees KythOS product metadata
LABEL org.opencontainers.image.title="KythOS"
LABEL org.opencontainers.image.version="44"
LABEL org.opencontainers.image.description="KythOS — atomic gaming and dev workstation built on Fedora Kinoite"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/mrtrick37/kyth"
LABEL org.opencontainers.image.documentation="https://github.com/mrtrick37/kyth"
LABEL org.osbuild.product="KythOS"
LABEL org.osbuild.version="44"
LABEL org.osbuild.branding.release="KythOS 44"

### MODIFICATIONS
# Fedora 44 ships scx_rusty 0.5.4, whose pre-upstream sched_ext BPF ABI is
# incompatible with the kernel 7.1 interface. Keep SCX opt-in until KythOS
# ships a scheduler build coordinated with its CachyOS kernel.
ARG ENABLE_SCX=0
ARG ENABLE_MESA_GIT=0
ARG ENABLE_GAMING_PERIPHERALS=0
ARG ENABLE_VIRTUALIZATION_HOST=0
ARG ENABLE_KSM=0
ARG GAMING_VERSIONS_HASH=unset
LABEL org.kyth.profile.gaming-peripherals="${ENABLE_GAMING_PERIPHERALS}"
LABEL org.kyth.profile.virtualization-host="${ENABLE_VIRTUALIZATION_HOST}"
LABEL org.kyth.profile.ksm="${ENABLE_KSM}"
LABEL org.kyth.gaming-versions="${GAMING_VERSIONS_HASH}"

# Build cache boundary: all RPM package installs (~2-3 GB). This layer selects
# the package set and is source-hash/base-image cached. The date-busted upgrade
# layer later refreshes every installed RPM plus the coordinated kernel stack.
ARG RPM_SET_HASH=unset
# Published layer boundaries are defined later by legacy-rechunk metadata.
RUN --mount=type=bind,source=build_files/kyth_shared,target=/ctx/kyth_shared \
    --mount=type=bind,source=build_files/config,target=/ctx/config \
    --mount=type=bind,source=build_files/scripts/packages-static.sh,target=/ctx/packages-static.sh \
    --mount=type=bind,source=build_files/scripts/packages,target=/ctx/packages \
    --mount=type=bind,source=build_files/scripts/lib,target=/ctx/lib \
    --mount=type=bind,source=build_files/RPM-GPG-KEY-microsoft,target=/ctx/RPM-GPG-KEY-microsoft \
    --mount=type=bind,source=build_files/RPM-GPG-KEY-google-antigravity,target=/ctx/RPM-GPG-KEY-google-antigravity \
    --mount=type=cache,id=kyth-var-cache,target=/var/cache \
    --mount=type=cache,id=kyth-var-log,target=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    : "cache-bust:rpm=${RPM_SET_HASH}" && \
    PYTHONPATH="/ctx/kyth_shared" \
    ENABLE_GAMING_PERIPHERALS="${ENABLE_GAMING_PERIPHERALS}" \
    ENABLE_VIRTUALIZATION_HOST="${ENABLE_VIRTUALIZATION_HOST}" \
    ENABLE_KSM="${ENABLE_KSM}" \
    ENABLE_SCX="${ENABLE_SCX}" \
    bash /ctx/packages-static.sh

# Proton-CachyOS is an offline fallback for fresh installs. The build must use
# the exact release tag resolved by CI; the mutable user-side updater may fetch
# newer versions later while retaining a rollback copy.
ARG PROTON_CACHYOS_VER
RUN --mount=type=bind,source=build_files/scripts/proton-cachyos.sh,target=/ctx/proton-cachyos.sh \
    --mount=type=bind,source=build_files/scripts/lib,target=/ctx/lib \
    --mount=type=secret,id=github_token \
    test -n "${PROTON_CACHYOS_VER}" && \
    PROTON_CACHYOS_VER="${PROTON_CACHYOS_VER}" bash /ctx/proton-cachyos.sh

# Third-party binary — umu launcher. Exact tags are resolved once by CI and
# used for both cache identity and downloads; installers never re-resolve
# "latest" inside the build.
ARG THIRDPARTY_VERSIONS_HASH=unset
ARG GAMING_VERSIONS_HASH=unset
ARG UMU_VERSION
RUN --mount=type=bind,source=build_files/scripts/thirdparty.sh,target=/ctx/thirdparty.sh \
    --mount=type=bind,source=build_files/scripts/thirdparty,target=/ctx/thirdparty \
    --mount=type=bind,source=build_files/scripts/lib,target=/ctx/lib \
    --mount=type=tmpfs,dst=/tmp \
    --mount=type=secret,id=github_token \
    : "cache-bust=${THIRDPARTY_VERSIONS_HASH}" && \
    UMU_VERSION="${UMU_VERSION}" \
    bash /ctx/thirdparty.sh

# Plymouth boot splash + initramfs rebuild.
# COPY (not bind-mount) is intentional: COPY includes file content hashes in the
# cache key, so the expensive dracut rebuild only reruns when the splash assets
# actually change — not on every daily dnf upgrade. Bind mounts do NOT contribute
# to the BuildKit cache key and would silently ship a stale cached splash.
# Kernel packages are excluded from ordinary dnf upgrades and updated as one
# coordinated stack during package assembly; the later kernel-repair layer
# validates the resulting latest kernel and initramfs. Sits after the large Proton-CachyOS/thirdparty download layers
# (which it does not depend on) so splash tweaks don't re-pull them, and before
# the BUILD_DATE cache-bust layer.
ARG PLYMOUTH_HASH=unset
COPY build_files/plymouth/kyth.plymouth             /tmp/kyth-plymouth/kyth.plymouth
COPY build_files/plymouth/kyth.script               /tmp/kyth-plymouth/kyth.script
COPY build_files/branding/kyth-logo-transparent.svg /tmp/kyth-branding/kyth-logo-transparent.svg
COPY build_files/branding/transparent-watermark.svg /tmp/kyth-branding/transparent-watermark.svg
COPY build_files/scripts/plymouth-setup.sh          /tmp/plymouth-setup.sh
COPY build_base/plymouth/kyth-plymouth-configure    /tmp/kyth-plymouth-configure
COPY build_files/scripts/plymouth-branding-guard.sh /tmp/plymouth-branding-guard.sh
RUN : "cache-bust:plymouth=${PLYMOUTH_HASH}" && \
    bash /tmp/plymouth-setup.sh && \
    rm -rf /tmp/kyth-plymouth /tmp/kyth-branding /tmp/plymouth-setup.sh /tmp/kyth-plymouth-configure /tmp/plymouth-branding-guard.sh

# kyth-vscode-wallet and the other helpers below are needed by both
# sysconfig-static and sysconfig layers. COPY once so neither layer needs a
# redundant bind-mount. sysconfig.sh removes these from /ctx once installed
# (see its tail) so they don't linger as duplicate content in the final image.
COPY build_files/kyth-vscode-wallet build_files/kyth-game-boost build_files/game-performance build_files/kyth-ntfs-repair build_files/kyth-shader-preheat build_files/kyth-health-check build_files/kyth-sched-arbiter build_files/kyth-power-arbiter build_files/kyth-power-arbiter.service build_files/kyth-storage-gate build_files/kyth-readahead-hint build_files/kyth-game-launch build_files/kyth-shader-prune build_files/kyth-tunable /ctx/

# Install the shared Python distribution for runtime scripts.
COPY build_files/kyth_shared /tmp/kyth-shared-package
RUN python3 -m pip install \
        --no-cache-dir \
        --no-deps \
        --no-build-isolation \
        --prefix=/usr \
        /tmp/kyth-shared-package && \
    rm -rf /tmp/kyth-shared-package


# Static system configuration — sysctl, kernel modules, PipeWire, Proton env
# vars, gamemode, MangoHud, vkBasalt, bluetooth, and kyth-* service units.
# Hash-gated — only re-runs when sysconfig-static.sh or sysconfig/ or data/
# change. Keeps the post-upgrade layer chain short and avoids users pulling
# a new sysconfig layer when only packages changed.
ARG SYSCONFIG_HASH=unset
RUN --mount=type=bind,source=build_files/scripts/sysconfig-static.sh,target=/ctx/sysconfig-static.sh \
    --mount=type=bind,source=build_files/scripts/sysconfig,target=/ctx/sysconfig \
    --mount=type=bind,source=build_files/scripts/lib,target=/ctx/lib \
    --mount=type=bind,source=build_files/data,target=/ctx/data \
    --mount=type=tmpfs,dst=/tmp \
    : "cache-bust:sysconfig=${SYSCONFIG_HASH}" && \
    bash /ctx/sysconfig-static.sh

# BUILD_DATE busts the upgrade layer and everything after it on every daily
# build. Package selection remains cached, but installed packages and the full
# Fedora kernel stack are refreshed against current repositories here.
ARG BUILD_DATE=unset

# Build cache boundary: upstream RPM upgrades and optional Mesa-git drivers.
# Mesa-git is folded into this layer instead of a standalone RUN so the no-op
# ENABLE_MESA_GIT=0 case does not add a separate empty layer to the manifest chain.
# Layers after this one are re-run on every daily build; layers before it are
# cached until their scripts or the base image change.
RUN --mount=type=bind,source=build_files/scripts/mesa-git.sh,target=/ctx/mesa-git.sh \
    --mount=type=bind,source=build_files/scripts/kernel-repair.sh,target=/ctx/kernel-repair.sh \
    --mount=type=bind,source=build_files/scripts/lib/fedora-kernel.sh,target=/ctx/lib/fedora-kernel.sh \
    --mount=type=bind,source=build_files/scripts/lib/find-kver.sh,target=/ctx/lib/find-kver.sh \
    --mount=type=bind,source=build_files/scripts/lib/dracut-retry.sh,target=/ctx/lib/dracut-retry.sh \
    --mount=type=bind,source=build_files/scripts/lib/check-multilib.sh,target=/ctx/lib/check-multilib.sh \
    --mount=type=cache,id=kyth-var-cache,target=/var/cache \
    --mount=type=cache,id=dnf-cache,sharing=locked,target=/var/cache/libdnf5 \
    --mount=type=cache,id=dnf-log,sharing=locked,target=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    : "cache-bust=${BUILD_DATE}" && \
    set -euo pipefail; \
    dnf5 upgrade -y --refresh --setopt=retries=10 --setopt=timeout=120 --setopt=zchunk=False --setopt=max_parallel_downloads=10 --setopt=keepcache=1 \
        --disablerepo='fedora-multimedia' \
        --exclude='gstreamer1-plugins-bad' \
        --exclude='gstreamer1-plugins-bad.i686' && \
    source /ctx/lib/fedora-kernel.sh && \
    if [[ "$(cat /usr/share/kyth/kernel-flavor 2>/dev/null || echo fedora)" == fedora ]]; then update_fedora_kernel; fi && \
    bash /ctx/kernel-repair.sh && \
    ENABLE_MESA_GIT=${ENABLE_MESA_GIT} bash /ctx/mesa-git.sh && \
    . /ctx/lib/check-multilib.sh && \
    check_multilib_pairs "${KYTH_MULTILIB_PAIRS[@]}" && \
    scan_multilib_orphans

# Build cache boundary: post-upgrade service wiring and account repair.
# Re-enforces display-manager symlinks that dnf5 upgrade can reset, and enables/
# disables runtime services after the upgrade has settled the unit file set.
RUN --mount=type=bind,source=build_files/scripts/sysconfig.sh,target=/ctx/sysconfig.sh \
    --mount=type=tmpfs,dst=/tmp \
    bash /ctx/sysconfig.sh

# Build cache boundary: Secure Boot signing, branding, helper app, and Plymouth.
# These operations share one raw BuildKit layer; legacy-rechunk repartitions the
# finished filesystem into update-efficient published OCI layers.
# Skipped gracefully when MOK_KEY is not set (local builds without a signing key).
# Pass the private key via: --secret id=mok_key,env=MOK_KEY
ARG SECUREBOOT_SIGNING_REQUESTED=0
RUN --mount=type=bind,source=build_files,target=/ctx \
    --mount=type=tmpfs,dst=/tmp \
    --mount=type=secret,id=mok_key \
    if [ -d /usr/share/factory/var/cache/libdnf5 ]; then \
        find /usr/share/factory/var/cache/libdnf5 -mindepth 1 -delete; \
    fi && \
    SECUREBOOT_SIGNING_REQUESTED=${SECUREBOOT_SIGNING_REQUESTED} bash /ctx/scripts/secureboot.sh && \
    bash /ctx/scripts/branding.sh && \
    bash /ctx/scripts/plymouth-initramfs.sh
