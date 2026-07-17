#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── AMD GPU kernel module options ────────────────────────────────────────────
# ppfeaturemask=0xffffffff: enables all PowerPlay features including fine-grained
# GPU/memory clock and voltage control. Required for gamemode's amd_performance_level
# switch to actually take full effect on RDNA APUs; without it some power states
# are locked out and the GPU stays in a lower-performance tier during gameplay.
#
# gttsize: GTT (Graphics Translation Table) is system RAM the GPU maps for overflow
# VRAM and DMA transfers. On a 14 GB APU the default is auto-sized but uncapped —
# the GPU can claim most of system RAM as GTT under sustained gaming load, starving
# CPU-side processes. Capping at 4096 MB leaves ≥10 GB reliably available for the
# CPU without starving games that need GPU memory bandwidth.
cat >/etc/modprobe.d/amdgpu-kyth.conf <<'AMDGPUEOF'
options amdgpu ppfeaturemask=0xffffffff
options amdgpu gttsize=4096
# noretry=0: allow the GPU to retry faulting memory accesses instead of
# immediately raising a fault signal. Prevents crashes in DX12 titles that
# access partially-mapped resources (common in games using tiled/sparse
# textures). The retry adds a small latency penalty on actual fault paths,
# which are rare during normal rendering.
options amdgpu noretry=0
AMDGPUEOF
