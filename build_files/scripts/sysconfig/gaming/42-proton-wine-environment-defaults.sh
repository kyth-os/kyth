#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── Proton/Wine environment defaults ──────────────────────────────────────────
# /etc/environment.d is process-global: anything written here is inherited by
# every desktop app, not just games. Keep only fallbacks that are provably safe
# outside games (sync-primitive fallbacks, log silencing, cache sizing).
# Game-only tunables (FSR upscaling, GL threading, VKD3D RT flags, MangoHud
# dlsym hooking, Steam browser subprocess) live in /etc/kyth/game-launch.env
# and are applied per-launch via the kyth-game-env wrapper or Steam launch
# options — never globally.
write_config /etc/environment.d/proton-radv.conf <<'PROTONEOF'
PROTON_FORCE_LARGE_ADDRESS_AWARE=1
WINE_LARGE_ADDRESS_AWARE=1
PROTON_USE_NTSYNC=1
# esync/fsync: fallback sync primitives used when NTSYNC is unavailable (module
# not loaded, older kernel, or non-kyth install). Proton checks in priority order:
# NTSYNC → fsync → esync → default. Having both enabled costs nothing when NTSYNC
# is active, and keeps Wine/Proton fast on any system this image runs on.
WINEFSYNC=1
WINEESYNC=1
# Suppress the Windows-style crash/error dialog that pops up when a game
# exits unexpectedly via Wine's built-in error handler. On Linux the crash is
# already captured by the kernel and Proton's own logging; the dialog just
# forces the user to click through a meaningless "Application Error" popup.
PROTON_NO_WINDOWS_CRASH_DIALOG=1
# Silence DXVK verbose debug output. The default "info" level writes to disk
# on every DX9/10/11 draw call setup, adding measurable I/O overhead on
# titles with high draw call counts. "none" keeps only fatal errors.
DXVK_LOG_LEVEL=none
# VKD3D-Proton logs at "warn" level by default — noisy in the journal.
# Matches DXVK_LOG_LEVEL=none above.
VKD3D_LOG_LEVEL=none
# Mesa Shader Cache size limit: raise to 10 GB to prevent shader eviction and
# stuttering on subsequent launches of shader-heavy games.
MESA_SHADER_CACHE_MAX_SIZE=10G
PROTONEOF

# Game-only env: sourced per-launch, never exported globally.
# Steam example (per-game Properties → Launch Options):
#   kyth-game-env mangohud %command%
write_config /etc/kyth/game-launch.env <<'GAMEENVEOF'
# Game-only Proton/Wine tunables — applied per-launch via kyth-game-env.
# FSR upscaling in fullscreen Wine/Proton games — lets older titles that don't
# run at native resolution get FidelityFX Super Resolution upscaling via Wine's
# built-in FSR pass. Strength 0 = sharpest, 5 = most blur; 2 is a good default.
WINE_FULLSCREEN_FSR=1
WINE_FULLSCREEN_FSR_STRENGTH=2
# Mesa GL threading: offloads OpenGL command submission; helps older GL titles,
# can regress Vulkan or Qt apps, so it must not leak into the global session.
mesa_glthread=true
# Enable DirectX 12 ray tracing in VKD3D-Proton. dxr advertises Tier 1 RT;
# dxr11 adds DX11-style conservative RT fallback used by some titles. VKD3D
# won't expose RT to the game unless the GPU Vulkan driver actually supports the
# VK_KHR_ray_tracing_pipeline extension.
VKD3D_CONFIG=dxr11,dxr
# MangoHud: fall back to dlsym hooking for older OpenGL games that dlopen libGL
# rather than linking it at load time. No-op for Vulkan, but game-scoped anyway.
MANGOHUD_DLSYM=1
# Prevent Steam from spawning a renderer subprocess for the built-in browser
# when it is not in use — saves ~100 MB of resident memory while gaming.
STEAM_DISABLE_BROWSER_SUBPROCESS=1
GAMEENVEOF

# Per-launch wrapper: `kyth-game-env <cmd>...` exports the game-only env file
# (plus kyth-game-launch consumers such as Steam launch options) and execs.
install -m 0755 /dev/stdin /usr/bin/kyth-game-env <<'GAMEENVEOF2'
#!/bin/bash
# kyth-game-env — apply game-only env per-launch, then exec.
set -euo pipefail
ENV_FILE="${KYTH_GAME_ENV:-/etc/kyth/game-launch.env}"
if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
fi
if [[ $# -eq 0 ]]; then
    echo "Usage: kyth-game-env <cmd> [args...]" >&2
    exit 2
fi
exec "$@"
GAMEENVEOF2
