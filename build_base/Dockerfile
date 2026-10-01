# Pull the upstream Fedora bootc base and apply KythOS branding.
# Build with: docker build -t localhost/kyth-base:stable build_base/
# Override the base via: docker build --build-arg BASE_IMAGE=quay.io/fedora/fedora-kinoite:45 build_base/
ARG BASE_IMAGE=quay.io/fedora/fedora-kinoite:45@sha256:884d0dee45a250f0e5d31c52e8167e6c8fc9e66fad80f1401d36400620d36861
FROM ${BASE_IMAGE}

# testing is the Fedora 45 line. main's build.yml (which GitHub runs for
# workflow_run events) passes its own F44 base through --build-arg BASE_IMAGE,
# so the pin above alone cannot stop an F44 build of this tree. Fail the build
# instead of publishing an F44 image as :testing.
RUN . /etc/os-release \
    && [ "${VERSION_ID}" = "45" ] \
    || { echo "testing must build on Fedora 45 but the base is Fedora ${VERSION_ID:-unknown}" >&2; exit 1; }

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
