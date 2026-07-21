#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Proton/Wine environment defaults ──────────────────────────────────────────
mkdir -p /etc/environment.d
cat >/etc/environment.d/proton-radv.conf <<'PROTONEOF'
PROTON_FORCE_LARGE_ADDRESS_AWARE=1
WINE_LARGE_ADDRESS_AWARE=1
PROTON_USE_NTSYNC=1
# esync/fsync: fallback sync primitives used when NTSYNC is unavailable (module
# not loaded, older kernel, or non-kyth install). Proton checks in priority order:
# NTSYNC → fsync → esync → default. Having both enabled costs nothing when NTSYNC
# is active, and keeps Wine/Proton fast on any system this image runs on.
WINEFSYNC=1
WINEESYNC=1
mesa_glthread=true
# FSR upscaling in fullscreen Wine/Proton games — lets older titles that don't
# run at native resolution get FidelityFX Super Resolution upscaling via Wine's
# built-in FSR pass. Works on AMD, NVIDIA, and Intel — it's a shader effect, not
# hardware. Strength 0 = sharpest, 5 = most blur; 2 is a good default balance.
WINE_FULLSCREEN_FSR=1
WINE_FULLSCREEN_FSR_STRENGTH=2
# Suppress the Windows-style crash/error dialog that pops up when a game
# exits unexpectedly via Wine's built-in error handler. On Linux the crash is
# already captured by the kernel and Proton's own logging; the dialog just
# forces the user to click through a meaningless "Application Error" popup.
PROTON_NO_WINDOWS_CRASH_DIALOG=1
# Silence DXVK verbose debug output. The default "info" level writes to disk
# on every DX9/10/11 draw call setup, adding measurable I/O overhead on
# titles with high draw call counts. "none" keeps only fatal errors.
DXVK_LOG_LEVEL=none
# Enable DirectX 12 ray tracing in VKD3D-Proton. dxr advertises Tier 1 RT;
# dxr11 adds DX11-style conservative RT fallback used by some titles. VKD3D
# won't expose RT to the game unless the GPU Vulkan driver actually supports the
# VK_KHR_ray_tracing_pipeline extension, so this is safe to set globally.
VKD3D_CONFIG=dxr11,dxr
# VKD3D-Proton logs at "warn" level by default — noisy in the journal.
# Matches DXVK_LOG_LEVEL=none above.
VKD3D_LOG_LEVEL=none
# MangoHud: fall back to dlsym hooking for older OpenGL games that dlopen libGL
# rather than linking it at load time. Safe to set globally; no-op for Vulkan.
MANGOHUD_DLSYM=1
# Prevent Steam from spawning a renderer subprocess for the built-in browser
# when it is not in use — saves ~100 MB of resident memory.
STEAM_DISABLE_BROWSER_SUBPROCESS=1
# Mesa Shader Cache size limit: raise to 10 GB to prevent shader eviction and
# stuttering on subsequent launches of shader-heavy games.
MESA_SHADER_CACHE_MAX_SIZE=10G
PROTONEOF
