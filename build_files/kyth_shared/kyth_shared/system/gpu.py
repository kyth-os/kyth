"""Shared GPU detection helpers: lspci parsing, loaded kernel modules, installed RPM packages."""
from __future__ import annotations
import logging

from kyth_shared.commands import run_optional, run_text

logger = logging.getLogger(__name__)


def run_lspci_nn() -> list[str]:
    """Return the stdout lines of ``lspci -nn``, or an empty list if it fails."""
    res = run_text(["lspci", "-nn"])
    if res is None:
        return []
    return res.stdout.splitlines()


def lspci_gpu_lines() -> list[str]:
    """Return lspci -nn lines that look like a display controller (VGA/3D/Display)."""
    return [
        line for line in run_lspci_nn()
        if any(k in line.lower() for k in ("vga", "3d", "display"))
    ]


def loaded_kernel_modules() -> set[str]:
    """Return the set of currently loaded kernel module names from /proc/modules."""
    modules: set[str] = set()
    try:
        with open("/proc/modules", "r", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if parts:
                    modules.add(parts[0])
    except Exception:
        logger.debug("handled expected exception", exc_info=True)
        pass
    return modules


def is_kernel_module_loaded(name: str) -> bool:
    """Check whether a kernel module is currently loaded."""
    return name in loaded_kernel_modules()


def rpm_package_installed(name: str) -> bool:
    """Check whether an RPM package is installed."""
    res = run_optional(["rpm", "-q", name], capture_output=True)
    return res is not None and res.returncode == 0


def get_hardware_setup_service_status(service_name: str = "kyth-hw-setup.service") -> tuple[str, str]:
    """Return systemd (state, result) tuple for the specified hardware setup service."""
    state_res = run_text(["systemctl", "is-active", service_name])
    state = state_res.stdout.strip() if state_res else "unknown"

    show_res = run_text(["systemctl", "show", "-p", "Result", "--value", service_name])
    result = show_res.stdout.strip() if show_res else "unknown"

    return state, result


def query_nvidia_smi() -> str:
    """Return the name and driver version from nvidia-smi, or empty string."""
    res = run_text(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])
    if res is not None and res.returncode == 0:
        lines = res.stdout.strip().splitlines()
        return lines[0].strip() if lines else ""
    return ""

