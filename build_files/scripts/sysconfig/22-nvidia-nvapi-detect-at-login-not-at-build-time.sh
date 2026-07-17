#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── NVIDIA NVAPI: detect at login, not at build time ─────────────────────────
# PROTON_ENABLE_NVAPI tells Proton to emulate NVIDIA's API layer.  It is only
# meaningful on systems with NVIDIA hardware; setting it on AMD/Intel causes
# games that check for NVAPI to try NVIDIA-specific paths and silently fail.
# A systemd user-environment generator runs at each login and outputs the
# variable only when an NVIDIA GPU is detected via lspci.
install -m 0755 /dev/stdin /usr/lib/systemd/user-environment-generators/80-kyth-nvapi.sh <<'NVAPIEOF'
#!/bin/bash
if lspci -d ::0300 2>/dev/null | grep -qi nvidia || \
   lspci -d ::0302 2>/dev/null | grep -qi nvidia; then
    # VKD3D-Proton (DX12) NVAPI: enables DLSS, Reflex, and NV-specific rendering
    # paths in DX12 games. Proton checks this before its own NVAPI detection.
    echo "PROTON_ENABLE_NVAPI=1"
    # DXVK (DX9/10/11) NVAPI: complementary to PROTON_ENABLE_NVAPI — DXVK has
    # its own NVAPI implementation used for DX11 games with NVAPI dependencies.
    echo "DXVK_ENABLE_NVAPI=1"
    # NVIDIA equivalent of mesa_glthread: offloads OpenGL command submission to
    # a second thread. Only meaningful on NVIDIA + OpenGL; Vulkan/DXVK unaffected.
    echo "__GL_THREADED_OPTIMIZATIONS=1"
    # Keep the NVIDIA OpenGL shader disk cache and prevent automatic pruning.
    # Without these, NVIDIA deletes cached shaders when the cache grows beyond
    # a threshold, forcing recompilation stutter every N launches.
    echo "__GL_SHADER_DISK_CACHE=1"
    echo "__GL_SHADER_DISK_CACHE_SKIP_CLEANUP=1"
    # nvidia-vaapi-driver: libva will not auto-detect the NVIDIA backend without
    # an explicit driver name. NVD_BACKEND=direct uses the NvDecode API directly
    # (avoids the deprecated CUDA path; works on Turing/Ampere/Ada without CUDA).
    echo "LIBVA_DRIVER_NAME=nvidia"
    echo "NVD_BACKEND=direct"
fi
NVAPIEOF

