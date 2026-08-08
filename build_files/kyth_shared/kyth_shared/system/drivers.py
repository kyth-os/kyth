"""Hardware driver and module probing utilities."""
from __future__ import annotations

from kyth_shared.commands import run_text


def get_loaded_kernel_modules() -> set[str]:
    """Return set of currently loaded kernel module names from /proc/modules."""
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


def is_module_loaded(module_name: str) -> bool:
    """Check if a kernel module is loaded."""
    return module_name in get_loaded_kernel_modules()


def get_pci_devices_by_class(device_class: str) -> list[str]:
    """Return lspci lines matching a given device class string (e.g. 'VGA', 'Network')."""
    res = run_text(["lspci", "-nn"])
    if not res or res.returncode != 0:
        return []
    return [
        line for line in res.stdout.splitlines()
        if device_class.lower() in line.lower()
    ]
