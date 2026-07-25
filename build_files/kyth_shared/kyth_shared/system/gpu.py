"""Shared GPU detection helpers: lspci parsing, loaded kernel modules, installed RPM packages."""
from __future__ import annotations

import subprocess


def run_lspci_nn() -> list[str]:
    """Return the stdout lines of ``lspci -nn``, or an empty list if it fails."""
    try:
        res = subprocess.run(["lspci", "-nn"], capture_output=True, text=True, check=False)
    except Exception:
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
        pass
    return modules


def is_kernel_module_loaded(name: str) -> bool:
    """Check whether a kernel module is currently loaded."""
    return name in loaded_kernel_modules()


def rpm_package_installed(name: str) -> bool:
    """Check whether an RPM package is installed."""
    try:
        res = subprocess.run(["rpm", "-q", name], capture_output=True, check=False)
    except Exception:
        return False
    return res.returncode == 0
