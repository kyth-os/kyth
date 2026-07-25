"""Shared utilities for KythOS gaming and performance tuning."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def get_cpu_topology() -> tuple[str, str]:
    """Retrieve CPU vendor ID and model name."""
    vendor = "Unknown"
    model = "Generic CPU"
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("vendor_id"):
                    vendor = line.split(":", 1)[1].strip()
                elif line.startswith("model name"):
                    model = line.split(":", 1)[1].strip()
    except Exception:
        pass
    return vendor, model


def has_3d_vcache() -> bool:
    """Check if the system has AMD 3D V-Cache."""
    try:
        # Check /proc/cpuinfo or lscpu
        with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
            for line in f:
                if "3d" in line.lower():
                    return True
    except Exception:
        pass

    if shutil.which("lscpu"):
        try:
            res = subprocess.run(["lscpu"], capture_output=True, text=True, check=False)
            if "3d" in res.stdout.lower():
                return True
        except Exception:
            pass
    return False


def get_amd_ccd0_cpus() -> str | None:
    """Retrieve CPU list for AMD 3D V-Cache CCD0."""
    path = Path("/sys/devices/system/cpu/cpu0/topology/core_siblings_list")
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return None


def get_intel_pcores() -> str | None:
    """Retrieve Intel Performance Cores CPU list based on maximum frequency matching cpu0."""
    cpu0_max_freq_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
    if not cpu0_max_freq_path.is_file():
        return None

    try:
        max_freq_cpu0 = int(cpu0_max_freq_path.read_text(encoding="utf-8").strip())
        if max_freq_cpu0 <= 0:
            return None

        pcores = []
        cpu_sys = Path("/sys/devices/system/cpu")
        for cpu_dir in cpu_sys.glob("cpu[0-9]*"):
            cpu_id = cpu_dir.name[3:]
            freq_file = cpu_dir / "cpufreq/cpuinfo_max_freq"
            if freq_file.is_file():
                freq = int(freq_file.read_text(encoding="utf-8").strip())
                if freq == max_freq_cpu0:
                    pcores.append(int(cpu_id))

        if pcores:
            return ",".join(str(c) for c in sorted(pcores))
    except Exception:
        pass
    return None


def set_epp(epp_value: str) -> bool:
    """Set Energy Performance Preference (EPP) for all CPU cores."""
    # Try calling kyth-set-epp helper via sudo if available
    if shutil.which("sudo"):
        try:
            res = subprocess.run(
                ["sudo", "-n", "/usr/bin/kyth-set-epp", epp_value],
                capture_output=True,
                check=False,
            )
            if res.returncode == 0:
                return True
        except Exception:
            pass

    # Fallback to writing directly
    success = False
    cpu_sys = Path("/sys/devices/system/cpu")
    for epp_file in cpu_sys.glob("cpu*/cpufreq/energy_performance_preference"):
        try:
            epp_file.write_text(epp_value, encoding="utf-8")
            success = True
        except Exception:
            pass
    return success


def get_current_epp() -> str:
    """Get Energy Performance Preference of CPU 0."""
    epp_file = Path("/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference")
    if epp_file.is_file():
        try:
            return epp_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return "n/a"


def set_power_profile(profile: str) -> bool:
    """Set the system power profile using powerprofilesctl."""
    if shutil.which("powerprofilesctl"):
        try:
            res = subprocess.run(["powerprofilesctl", "set", profile], capture_output=True, check=False)
            return res.returncode == 0
        except Exception:
            pass
    return False


def get_power_profile() -> str:
    """Get current active system power profile."""
    if shutil.which("powerprofilesctl"):
        try:
            res = subprocess.run(["powerprofilesctl", "get"], capture_output=True, text=True, check=False)
            return res.stdout.strip()
        except Exception:
            pass
    return "n/a"


def flush_page_caches() -> None:
    """Flush memory page cache."""
    drop_caches = Path("/proc/sys/vm/drop_caches")
    if os.access(drop_caches, os.W_OK):
        try:
            os.sync()
            drop_caches.write_text("3\n", encoding="utf-8")
        except Exception:
            pass


def set_transparent_hugepages(setting: str) -> None:
    """Set transparent hugepages mode (e.g. 'madvise')."""
    thp = Path("/sys/kernel/mm/transparent_hugepage/enabled")
    if os.access(thp, os.W_OK):
        try:
            thp.write_text(f"{setting}\n", encoding="utf-8")
        except Exception:
            pass


def switch_sched_ext_profile(profile: str) -> None:
    """Switch sched-ext low-latency scheduler profile using kyth-scx helper."""
    if shutil.which("scx_rusty") and shutil.which("sudo"):
        try:
            subprocess.run(["sudo", "-n", "/usr/bin/kyth-scx", "set", profile], capture_output=True, check=False)
        except Exception:
            pass
