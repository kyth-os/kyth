"""NVIDIA detection, first-boot setup flags, and GPU probe."""
from __future__ import annotations

import os
import subprocess

from .types import HardwareProbe
from ..process import _probe_cached


def _detect_nvidia() -> bool:
    def fetch() -> bool:
        try:
            r = subprocess.run(["lspci"], capture_output=True, text=True, timeout=5, check=False)
            return "nvidia" in r.stdout.lower()
        except Exception:
            return False
    return _probe_cached("nvidia-detect", 10.0, fetch)
 # _detect_nvidia

def _nvidia_module_loaded() -> bool:
    try:
        r = subprocess.run(["lsmod"], capture_output=True, text=True, timeout=5, check=False)
        return "nvidia" in r.stdout.lower()
    except Exception:
        return False
 # _nvidia_module_loaded

def _akmod_nvidia_built() -> bool:
    try:
        r = subprocess.run(["modinfo", "nvidia"], capture_output=True, text=True, timeout=5, check=False)
        return r.returncode == 0
    except Exception:
        return False
 # _akmod_nvidia_built

def _akmod_nvidia_installed() -> bool:
    try:
        r = subprocess.run(["rpm", "-q", "akmod-nvidia"], capture_output=True, text=True, timeout=5, check=False)
        return r.returncode == 0
    except Exception:
        return False
 # _akmod_nvidia_installed

def _hw_setup_service_state() -> str:
    """Returns the systemd active state of kyth-hw-setup.service.
    Possible values: 'activating' (running), 'active' (done), 'failed', 'inactive', or ''."""
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "kyth-hw-setup.service"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return r.stdout.strip()
    except Exception:
        return ""
 # _hw_setup_service_state

def _hw_setup_done() -> bool:
    return os.path.exists("/var/lib/kyth/hw-setup-done")


def _gpu_probe(pci_text: str, lsmod_text: str) -> HardwareProbe:
    gpu_lines = [
        line.strip()
        for line in pci_text.splitlines()
        if any(token in line.lower() for token in ("vga compatible controller", "3d controller", "display controller"))
    ]
    if not gpu_lines:
        return HardwareProbe(
            "Graphics", "dim",
            "No GPU information detected.",
            "The helper app could not find a display adapter via lspci.",
        )

    has_nvidia = any("nvidia" in line.lower() for line in gpu_lines)
    has_amd = any("[amd/ati]" in line.lower() or "advanced micro devices" in line.lower() for line in gpu_lines)
    has_intel = any("intel corporation" in line.lower() for line in gpu_lines)
    vendors = [v for v, flag in [("NVIDIA", has_nvidia), ("AMD", has_amd), ("Intel", has_intel)] if flag]
    hybrid = len(vendors) > 1

    if has_nvidia:
        if _nvidia_module_loaded():
            summary = "Hybrid graphics active with NVIDIA drivers." if hybrid else "NVIDIA GPU with active proprietary drivers."
            return HardwareProbe("Graphics", "ok", summary, "Detected:\n" + "\n".join(gpu_lines))
        if _akmod_nvidia_built():
            return HardwareProbe(
                "Graphics", "warn",
                "NVIDIA drivers installed but not yet active.",
                "The nvidia module exists for this kernel but is not loaded.\nDetected:\n" + "\n".join(gpu_lines),
                "Reboot to activate the staged driver.",
                action_page_key="NVIDIA",
            )
        summary = "Hybrid graphics: NVIDIA driver not active." if hybrid else "NVIDIA hardware found without an active driver."
        return HardwareProbe(
            "Graphics", "err", summary,
            "Detected:\n" + "\n".join(gpu_lines),
            "Open NVIDIA Drivers to build and stage the driver.",
            action_page_key="NVIDIA",
        )

    if has_amd:
        loaded = "amdgpu" in lsmod_text.lower()
        status = "ok" if loaded else "warn"
        summary = "AMD GPU — amdgpu driver loaded." if loaded else "AMD GPU — amdgpu driver not found in lsmod."
        return HardwareProbe("Graphics", status, summary, "Detected:\n" + "\n".join(gpu_lines))

    if has_intel:
        loaded = "i915" in lsmod_text.lower() or "\nxe " in f"\n{lsmod_text.lower()}"
        status = "ok" if loaded else "warn"
        summary = "Intel GPU — kernel driver loaded." if loaded else "Intel GPU — no kernel driver found in lsmod."
        return HardwareProbe("Graphics", status, summary, "Detected:\n" + "\n".join(gpu_lines))

    return HardwareProbe("Graphics", "dim", "GPU detected, vendor not recognized.", "Detected:\n" + "\n".join(gpu_lines))
 # _gpu_probe

