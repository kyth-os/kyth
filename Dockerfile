
ARG BASE_IMAGE=localhost/kyth-base:stable

# Base Image
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
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
ARG ENABLE_SCX=1
ARG ENABLE_MESA_GIT=0
ARG ENABLE_GAMING_PERIPHERALS=0
ARG ENABLE_VIRTUALIZATION_HOST=0
ARG ENABLE_KSM=0
LABEL org.kyth.profile.gaming-peripherals="${ENABLE_GAMING_PERIPHERALS}"
LABEL org.kyth.profile.virtualization-host="${ENABLE_VIRTUALIZATION_HOST}"
LABEL org.kyth.profile.ksm="${ENABLE_KSM}"

# Build cache boundary: all RPM package installs (~2-3 GB).
# Stable — only re-run when packages-static.sh or packages/*.sh fragments
# change or the base image is updated.
# Published layer boundaries are defined later by legacy-rechunk metadata.
RUN --mount=type=bind,source=build_files/scripts/packages-static.sh,target=/ctx/packages-static.sh \
    --mount=type=bind,source=build_files/scripts/packages,target=/ctx/packages \
    --mount=type=bind,source=build_files/scripts/lib,target=/ctx/lib \
    --mount=type=bind,source=build_files/RPM-GPG-KEY-microsoft,target=/ctx/RPM-GPG-KEY-microsoft \
    --mount=type=bind,source=build_files/RPM-GPG-KEY-google-antigravity,target=/ctx/RPM-GPG-KEY-google-antigravity \
    --mount=type=cache,id=kyth-var-cache,target=/var/cache \
    --mount=type=cache,id=kyth-var-log,target=/var/log \
    --mount=type=tmpfs,dst=/tmp \
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

# Third-party binary — umu launcher.
# Placed before BUILD_DATE so the layer is only re-run when a tool ships a new
# release. Exact tags are resolved once by CI and used for both cache identity
# and downloads; installers never re-resolve "latest" inside the build.
ARG THIRDPARTY_VERSIONS_HASH=unset
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
# Kernel packages are excluded from dnf upgrade (see packages.sh excludepkgs), so
# the kernel version is fixed from the base image and the initramfs built here is
# the one that ships. Sits after the large Proton-CachyOS/thirdparty download layers
# (which it does not depend on) so splash tweaks don't re-pull them, and before
# the BUILD_DATE cache-bust layer.
COPY build_files/plymouth/kyth.plymouth             /tmp/kyth-plymouth/kyth.plymouth
COPY build_files/plymouth/kyth.script               /tmp/kyth-plymouth/kyth.script
COPY build_files/branding/kyth-logo-transparent.svg /tmp/kyth-branding/kyth-logo-transparent.svg
COPY build_files/branding/transparent-watermark.svg /tmp/kyth-branding/transparent-watermark.svg
COPY build_files/scripts/plymouth-setup.sh          /tmp/plymouth-setup.sh
COPY build_files/scripts/plymouth-branding-guard.sh /tmp/plymouth-branding-guard.sh
RUN bash /tmp/plymouth-setup.sh && \
    rm -rf /tmp/kyth-plymouth /tmp/kyth-branding /tmp/plymouth-setup.sh /tmp/plymouth-branding-guard.sh

# kyth-vscode-wallet and kyth-ai-dev are needed by both sysconfig-static and
# sysconfig layers. COPY once so neither layer needs a redundant bind-mount.
COPY build_files/kyth-vscode-wallet build_files/kyth-ai-dev build_files/kyth-game-boost build_files/kyth-ntfs-repair build_files/kyth-shader-preheat build_files/kyth-health-check /ctx/

# Static system configuration — sysctl, kernel modules, PipeWire, Proton env
# vars, gamemode, MangoHud, vkBasalt, bluetooth, and kyth-* service units.
# Stable — only re-runs when sysconfig-static.sh or config defaults change,
# not on every daily dnf5 upgrade. This keeps the post-upgrade layer chain
# short and avoids users pulling a new sysconfig layer when only packages changed.
# kyth_shared is bind-mounted (not yet pip-installed at this point in the build —
# that happens further down) so kyth-vscode-wallet can import it when the
# 24-vs-code-avoid-kwallet-password-prompts.sh fragment runs it against /etc/skel.
RUN --mount=type=bind,source=build_files/scripts/sysconfig-static.sh,target=/ctx/sysconfig-static.sh \
    --mount=type=bind,source=build_files/scripts/sysconfig,target=/ctx/sysconfig \
    --mount=type=bind,source=build_files/scripts/lib,target=/ctx/lib \
    --mount=type=bind,source=build_files/data,target=/ctx/data \
    --mount=type=bind,source=build_files/kyth_shared,target=/ctx/kyth_shared \
    --mount=type=tmpfs,dst=/tmp \
    bash /ctx/sysconfig-static.sh

# BUILD_DATE busts the cache for the upgrade layer and everything after it on
# every daily build, ensuring dnf5 upgrade always runs even when the base image
# digest and build_files/ contents haven't changed.
# Pass as: --build-arg BUILD_DATE="$(date +%Y-%m-%d)"
ARG BUILD_DATE=unset

# Build cache boundary: upstream RPM upgrades and optional Mesa-git drivers.
# Mesa-git is folded into this layer instead of a standalone RUN so the no-op
# ENABLE_MESA_GIT=0 case does not add a separate empty layer to the manifest chain.
# Layers after this one are re-run on every daily build; layers before it are
# cached until their scripts or the base image change.
RUN --mount=type=bind,source=build_files/scripts/mesa-git.sh,target=/ctx/mesa-git.sh \
    --mount=type=bind,source=build_files/scripts/kernel-repair.sh,target=/ctx/kernel-repair.sh \
    --mount=type=bind,source=build_files/scripts/lib/find-kver.sh,target=/ctx/lib/find-kver.sh \
    --mount=type=bind,source=build_files/scripts/lib/check-multilib.sh,target=/ctx/lib/check-multilib.sh \
    --mount=type=cache,id=kyth-var-cache,target=/var/cache \
    --mount=type=tmpfs,dst=/tmp \
    : "cache-bust=${BUILD_DATE}" && \
    set -euo pipefail; \
    dnf5 upgrade -y --refresh --exclude='akmod-*' --exclude='kmod-*' \
        --exclude='gamescope*' \
        --disablerepo='fedora-multimedia' \
        --exclude='gstreamer1-plugins-bad' \
        --exclude='gstreamer1-plugins-bad.i686' && \
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

# Install the shared Python distribution from a COPY-backed source so content
# changes invalidate BuildKit's cache. The later /ctx bind mount alone does not
# participate in the cache key.
COPY build_files/kyth_shared /tmp/kyth-shared-package
RUN python3 -m pip install \
        --no-cache-dir \
        --no-deps \
        --no-build-isolation \
        --prefix=/usr \
        /tmp/kyth-shared-package && \
    rm -rf /tmp/kyth-shared-package

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
