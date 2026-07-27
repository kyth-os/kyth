"""NVIDIA detection, first-boot setup flags, and GPU probe."""
from __future__ import annotations

import os
from kyth_welcome.services.command import run_sync
from dataclasses import dataclass

from .types import HardwareProbe
from ..process import probe_cached


def _detect_nvidia() -> bool:
    def fetch() -> bool:
        try:
            r = run_sync(["lspci"], capture_output=True, text=True, timeout=5, check=False)
            return "nvidia" in r.stdout.lower()
        except Exception:
            return False
    return probe_cached("nvidia-detect", 10.0, fetch)
 # _detect_nvidia

def _nvidia_module_loaded() -> bool:
    try:
        r = run_sync(["lsmod"], capture_output=True, text=True, timeout=5, check=False)
        return "nvidia" in r.stdout.lower()
    except Exception:
        return False
 # _nvidia_module_loaded

def _akmod_nvidia_built() -> bool:
    try:
        r = run_sync(["modinfo", "nvidia"], capture_output=True, text=True, timeout=5, check=False)
        return r.returncode == 0
    except Exception:
        return False
 # _akmod_nvidia_built

def _akmod_nvidia_installed() -> bool:
    try:
        r = run_sync(["rpm", "-q", "akmod-nvidia"], capture_output=True, text=True, timeout=5, check=False)
        return r.returncode == 0
    except Exception:
        return False
 # _akmod_nvidia_installed

def _hw_setup_service_state() -> str:
    """Returns the systemd active state of kyth-hw-setup.service.
    Possible values: 'activating' (running), 'active' (done), 'failed', 'inactive', or ''."""
    try:
        r = run_sync(
            ["systemctl", "is-active", "kyth-hw-setup.service"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return r.stdout.strip()
    except Exception:
        return ""
 # _hw_setup_service_state

def _hw_setup_done() -> bool:
    return os.path.exists("/var/lib/kyth/hw-setup-done")


@dataclass(frozen=True)
class NvidiaStatusView:
    """What page_nvidia.py's NvidiaPage should show, driven purely by probe
    results — no Qt, so the decision tree is testable without a display."""
    sub_text: str
    status_text: str
    status_style: str
    install_visible: bool
    install_text: str
    progress_visible: bool
    reboot_visible: bool
    keep_polling: bool


def nvidia_status_view(
    *, has_gpu: bool, loaded: bool, built: bool, installed: bool,
    hw_setup_done: bool, svc_state: str,
) -> NvidiaStatusView:
    auto_building = svc_state == "activating"

    if not has_gpu:
        return NvidiaStatusView(
            "No NVIDIA GPU detected in this system.",
            "No NVIDIA hardware found.", "status-dim",
            False, "", False, False, auto_building,
        )
    if loaded:
        return NvidiaStatusView(
            "NVIDIA GPU detected.",
            "Drivers are active and the kernel module is loaded.", "status-ok",
            False, "", False, False, auto_building,
        )
    if built:
        return NvidiaStatusView(
            "NVIDIA GPU detected.",
            "Drivers installed — reboot to activate.", "status-warn",
            False, "", False, True, auto_building,
        )
    if auto_building:
        # kyth-hw-setup is running akmods in the background right now.
        return NvidiaStatusView(
            "NVIDIA GPU detected.",
            "Building NVIDIA kernel module automatically — this takes 5–15 minutes.\n"  # noqa: RUF001 — en dash, deliberate typography
            "You can keep using the system. This page will update when the build finishes.",
            "subheading",
            False, "", True, False, True,
        )
    if hw_setup_done and svc_state == "failed":
        # Service ran but akmods failed — offer a manual retry.
        return NvidiaStatusView(
            "NVIDIA GPU detected — automatic build failed.",
            "kyth-hw-setup could not build the kernel module. "
            "Check journalctl -u kyth-hw-setup for details, then click below to retry.",
            "status-err",
            True, "Retry Build", False, False, False,
        )
    if installed:
        # Service hasn't run yet or was reset — offer a manual kick-off.
        return NvidiaStatusView(
            "NVIDIA GPU detected.",
            "Kernel module will be compiled automatically on next boot, "
            "or click below to build it now.",
            "subheading",
            True, "Build Driver Now", False, False, False,
        )
    # akmod-nvidia missing — should never happen on a correctly built image.
    return NvidiaStatusView(
        "NVIDIA GPU detected — driver package missing.",
        "akmod-nvidia is not installed. This is unexpected on KythOS.\n"
        "Run: rpm-ostree install akmod-nvidia, then reboot and return here.",
        "status-err",
        False, "", False, False, False,
    )


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

