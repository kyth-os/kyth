"""NVIDIA detection, declarative setup state, and GPU probe."""
from __future__ import annotations

import json
from kyth_welcome.services.command import run_sync
from dataclasses import dataclass

from .types import HardwareProbe
from ..process import probe_cached


def _detect_nvidia() -> bool:
    def fetch() -> bool:
        # Canonical path: hardware_policy inventory via hardware_view probe cache
        # — single PCI parse for Hub hardware page, window sidebar, and
        # kyth-hw-setup. Falls back to raw lspci if policy load fails (live
        # session without /usr/share/kyth/hardware-profiles.toml).
        try:
            from kyth_shared.system.hardware_view import get_hardware_view

            view = get_hardware_view()
            return bool(view.has_nvidia)
        except Exception:
            pass
        try:
            r = run_sync(["lspci"], capture_output=True, text=True, timeout=5, check=False)
            return "nvidia" in r.stdout.lower()
        except Exception:
            return False
    return probe_cached("nvidia-detect", 300.0, fetch)
 # _detect_nvidia

def detect_nvidia_async(owner, on_result, *, attr: str = "_nvidia_probe_worker") -> None:
    """Run _detect_nvidia() on a background thread and call
    on_result(has_nvidia: bool) once it resolves, instead of blocking the
    GUI thread on the lspci call. `owner` is the page/window the worker's
    lifetime is tracked on via its `<attr>` attribute (need not be
    pre-declared — defaults to None) — a call made while a previous one is
    still running is a no-op rather than starting a second probe.

    Shared by every page that needs to react to NVIDIA presence
    asynchronously instead of hand-rolling this DataWorker wiring itself
    (MainWindow's sidebar, RepairPage's Quick Fixes NVIDIA buttons, ...).
    _detect_nvidia() is already probe_cached, so this is about not blocking
    the *first* call — not about avoiding redundant subprocess calls.
    """
    from ..runtime import DataWorker, guard_disposed  # local: keep this module Qt-import-free at module scope

    if getattr(owner, attr, None) is not None:
        return
    worker = DataWorker("detect-nvidia-async", _detect_nvidia)
    setattr(owner, attr, worker)
    # Guard on_result here, once, rather than trusting every caller to do it —
    # this helper exists precisely so pages don't hand-roll DataWorker wiring.
    worker.result.connect(guard_disposed(lambda _key, has_nvidia: on_result(bool(has_nvidia))))
    worker.failed.connect(lambda _key, _message: None)
    worker.finished.connect(lambda: setattr(owner, attr, None))
    worker.finished.connect(worker.deleteLater)
    worker.start()
 # detect_nvidia_async

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
    try:
        with open("/var/lib/kyth/hardware-policy.json", encoding="utf-8") as stream:
            state = json.load(stream)
        return state.get("status") in {"applied", "failed"}
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def _secureboot_state() -> str:
    """Return 'enabled:enrolled' / 'enabled:not-enrolled' / 'disabled' / 'unknown'.

    Probes mokutil --sb-state and, when enabled, mokutil --list-enrolled for
    the Kyth MOK. probe_cached 30s — avoids re-running mokutil on every Hub
    tab switch. Missing mokutil -> unknown (e.g. test hosts)."""
    def fetch() -> str:
        try:
            r = run_sync(["mokutil", "--sb-state"], capture_output=True, text=True, timeout=5, check=False)
            out = (r.stdout + r.stderr).lower()
            if "secureboot enabled" in out:
                enabled = True
            elif "secureboot disabled" in out:
                return "disabled"
            else:
                return "unknown"
        except Exception:
            return "unknown"
        if not enabled:
            return "disabled"
        try:
            r2 = run_sync(["mokutil", "--list-enrolled"], capture_output=True, text=True, timeout=5, check=False)
            hay = (r2.stdout + r2.stderr).lower()
            if "kyth" in hay:
                return "enabled:enrolled"
            return "enabled:not-enrolled"
        except Exception:
            return "enabled:unknown"
    return probe_cached("secureboot-state", 300.0, fetch)
 # _secureboot_state


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
    secureboot: str = "unknown"


def nvidia_status_view(
    *, has_gpu: bool, loaded: bool, built: bool, installed: bool,
    hw_setup_done: bool, svc_state: str, secureboot: str = "unknown",
) -> NvidiaStatusView:
    auto_building = svc_state == "activating"
    sb_hint = ""
    if secureboot == "enabled:not-enrolled":
        sb_hint = " Secure Boot is on but the Kyth key is not enrolled — the driver will not load until you enroll (Reboot → Enroll MOK → Continue)."
    elif secureboot == "enabled:unknown":
        sb_hint = " Secure Boot is on — if the driver fails to load, enroll the Kyth MOK at boot."
    elif secureboot == "enabled:enrolled":
        sb_hint = " Secure Boot: Kyth key enrolled."

    if not has_gpu:
        return NvidiaStatusView(
            "No NVIDIA GPU detected in this system.",
            "No NVIDIA hardware found.", "status-dim",
            False, "", False, False, auto_building, secureboot=secureboot,
        )
    if loaded:
        return NvidiaStatusView(
            "NVIDIA GPU detected.",
            "Drivers are active and the kernel module is loaded." + sb_hint, "status-ok",
            False, "", False, False, auto_building, secureboot=secureboot,
        )
    if built:
        return NvidiaStatusView(
            "NVIDIA GPU detected.",
            "Drivers installed — reboot to activate." + sb_hint, "status-warn",
            False, "", False, True, auto_building, secureboot=secureboot,
        )
    if auto_building:
        # kyth-hw-setup is running akmods in the background right now.
        return NvidiaStatusView(
            "NVIDIA GPU detected.",
            "Building NVIDIA kernel module automatically — this takes 5–15 minutes.\n"  # noqa: RUF001 — en dash, deliberate typography
            "You can keep using the system. This page will update when the build finishes." + sb_hint,
            "subheading",
            False, "", True, False, True, secureboot=secureboot,
        )
    if hw_setup_done and svc_state == "failed":
        # Service ran but akmods failed — offer a manual retry.
        return NvidiaStatusView(
            "NVIDIA GPU detected — automatic build failed.",
            "kyth-hw-setup could not build the kernel module. "
            "Check journalctl -u kyth-hw-setup for details, then click below to retry." + sb_hint,
            "status-err",
            True, "Retry Build", False, False, False, secureboot=secureboot,
        )
    if installed:
        # Service hasn't run yet or was reset — offer a manual kick-off.
        return NvidiaStatusView(
            "NVIDIA GPU detected.",
            "Kernel module will be compiled automatically on next boot, "
            "or click below to build it now." + sb_hint,
            "subheading",
            True, "Build Driver Now", False, False, False, secureboot=secureboot,
        )
    # akmod-nvidia missing — should never happen on a correctly built image.
    return NvidiaStatusView(
        "NVIDIA GPU detected — driver package missing.",
        "akmod-nvidia is not installed. This is unexpected on KythOS.\n"
        "Run: rpm-ostree install akmod-nvidia, then reboot and return here." + sb_hint,
        "status-err",
        False, "", False, False, False, secureboot=secureboot,
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
