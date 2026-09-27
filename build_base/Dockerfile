# Pull the upstream Fedora bootc base and apply KythOS branding.
# Build with: docker build -t localhost/kyth-base:stable build_base/
# Override the base via: docker build --build-arg BASE_IMAGE=ghcr.io/ublue-os/kinoite-main:44 build_base/
ARG BASE_IMAGE=ghcr.io/ublue-os/kinoite-main:44@sha256:cab4b50650d4f1e07273b27bd8e6dd785a6b8c596e5bbe1b7ee2e18d3ecb2709
FROM ${BASE_IMAGE}

# Fedora is the default kernel flavor. CachyOS is an advanced image
# variant built from the same tree and exposed to users through bootc switches.
ARG KYTH_KERNEL_FLAVOR=fedora

# NVIDIA pre-stage is opt-in (Bazzite desktop-nvidia vs desktop) — same base
# digest for non-NVIDIA, separate stable-nvidia tag when enabled.
ARG ENABLE_NVIDIA=0

# Cachy v3 is x86-64-v3 opt-in (like CachyOS znver4/v3), not v4 (breaks older CPUs).
# Fedora default stays x86-64.
ARG CACHYOS_ARCH=x86-64-v3

# Passed at build time so the layer cache is busted whenever an alternate
# kernel version is published. Build scripts resolve the latest versions and
# pass them here. Explicitly referenced via the no-op ':' builtin so Docker
# (both classic and BuildKit) includes them in the cache key.
ARG CACHYOS_KERNEL_VER=unset

# Use a bind-mount so the script is never written into any image layer
RUN --mount=type=bind,source=build.sh,target=/run/build.sh \
    --mount=type=bind,source=plymouth,target=/run/plymouth \
    : "cache-bust=${KYTH_KERNEL_FLAVOR}-${CACHYOS_KERNEL_VER}-${ENABLE_NVIDIA}-${CACHYOS_ARCH}" \
    && KYTH_KERNEL_FLAVOR="${KYTH_KERNEL_FLAVOR}" \
       CACHYOS_KERNEL_VER="${CACHYOS_KERNEL_VER}" \
       ENABLE_NVIDIA="${ENABLE_NVIDIA}" \
       CACHYOS_ARCH="${CACHYOS_ARCH}" \
       bash /run/build.sh
