# Hardware Support Matrix

> Generated from `build_files/config/hardware-profiles.toml`; do not edit manually.

## Image variants

| Variant | Status | Intended hardware | Qualification |
|---|---|---|---|
| `universal` | shipping | AMD, Intel, NVIDIA and hybrid desktop/laptop systems | Automated image checks plus the current real-hardware matrix |
| `desktop-amd-intel` | planned | AMD/Intel graphics without the proprietary NVIDIA payload | Requires representative AMD and Intel suspend, display and gaming results |
| `desktop-nvidia` | planned | NVIDIA proprietary and hybrid graphics with prebuilt modules | Requires module ABI, Secure Boot, Wayland and suspend qualification |
| `handheld` | planned | Controller-first handheld and couch-PC platforms | Requires per-device controls, suspend and dock validation |

## Device profiles

| Profile | Tier | Recommended variant | Capabilities |
|---|---|---|---|
| `asus-rog-ally` | experimental | `universal` | `form-factor.handheld`, `input.controller-first` |
| `valve-handheld` | experimental | `universal` | `form-factor.handheld`, `input.controller-first` |
| `amd-nvidia-hybrid` | supported | `universal` | `gpu.hybrid`, `gpu.offload` |
| `intel-nvidia-hybrid` | supported | `universal` | `gpu.hybrid`, `gpu.offload` |
| `nvidia-proprietary` | supported | `universal` | `gpu.nvidia`, `nvidia.proprietary`, `wayland.explicit-sync` |
| `amd-graphics` | supported | `universal` | `gpu.amd`, `vulkan.radv`, `video.vaapi` |
| `intel-graphics` | supported | `universal` | `gpu.intel`, `vulkan.anv`, `video.vaapi` |
| `baseline` | supported | `universal` | `atomic-updates`, `hardware-policy`, `plasma-wayland` |

## Managed quirks

| Quirk | Review by | Reason | Provenance |
|---|---|---|---|
| `amdgpu-gaming-memory` | 2027-08-01 | Expose PowerPlay controls while bounding APU GTT pressure and retaining recoverable VM fault handling | [policy rationale](hardware-policy.md#managed-quirks) |
| `amdgpu-psr-disable` | 2027-08-01 | Disable Display Core PSR on Navi 33 (7480) DCN 3.2.1 and Rembrandt (1681) DCN 3.1.2 to avoid Pageflip timed out on eDP under Wayland/VRR | https://gitlab.freedesktop.org/drm/amd/-/issues and journalctl amdgpu Pageflip timed out (DCN 3.2.1 on 7480, DCN 3.1.2 eDP-2 PSR 1) |
| `bluetooth-usb-autosuspend` | 2027-08-01 | Prevent missed remote wake traffic from Bluetooth controllers and low-bandwidth peripherals | [policy rationale](hardware-policy.md#managed-quirks) |
| `intel-i915-media-firmware` | 2027-08-01 | Enable GuC submission and HuC media firmware on systems still using i915 | [policy rationale](hardware-policy.md#managed-quirks) |
| `intel-wifi-association-power` | 2027-08-01 | Keep Intel wireless active during WPA association while preserving Bluetooth coexistence | [policy rationale](hardware-policy.md#managed-quirks) |
| `mediatek-pcie-wifi-aspm` | 2027-08-01 | Avoid intermittent wake and association failures on mt7921e and mt7925e adapters | [policy rationale](hardware-policy.md#managed-quirks) |
| `nvidia-wayland-suspend` | 2027-08-01 | Enable DRM modesetting and preserve video memory across suspend on the proprietary driver | [policy rationale](hardware-policy.md#managed-quirks) |
