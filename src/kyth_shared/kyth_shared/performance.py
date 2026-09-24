"""Shared utilities for KythOS gaming and performance tuning."""
from __future__ import annotations
import logging

import os
import re
import shutil

from .commands import run as run_command
from pathlib import Path

logger = logging.getLogger(__name__)


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
    except (OSError, ValueError) as exc:
        logger.debug("get_cpu_topology failed: %s", exc, exc_info=True)
    return vendor, model


def _model_reports_3d_vcache(text: str) -> bool:
    """Recognize AMD X3D model names, not unrelated CPU flags like 3DNow."""
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() in {"model name", "model"}:
            normalized = value.lower()
            if re.search(r"x3d\b", normalized) or "3d v-cache" in normalized:
                return True
    return False


def has_3d_vcache() -> bool:
    """Check whether the CPU model identifies AMD 3D V-Cache."""
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
            if _model_reports_3d_vcache(f.read()):
                return True
    except (OSError, ValueError) as exc:
        logger.debug("has_3d_vcache cpuinfo read failed: %s", exc, exc_info=True)

    if shutil.which("lscpu"):
        try:
            res = run_command(["lscpu"], capture_output=True, text=True, check=False)
            if _model_reports_3d_vcache(res.stdout):
                return True
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
    return False


def get_amd_ccd0_cpus() -> str | None:
    """Retrieve CPU list for AMD 3D V-Cache CCD0."""
    path = Path("/sys/devices/system/cpu/cpu0/topology/core_siblings_list")
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8").strip()
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
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
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass
    return None


def set_epp(epp_value: str) -> bool:
    """Set Energy Performance Preference (EPP) for all CPU cores."""
    # Try calling kyth-set-epp helper via sudo if available
    if shutil.which("sudo"):
        try:
            res = run_command(
                ["sudo", "-n", "/usr/bin/kyth-set-epp", epp_value],
                capture_output=True,
                check=False,
            )
            if res.returncode == 0:
                return True
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
            pass

    # Fallback to writing directly
    success = False
    cpu_sys = Path("/sys/devices/system/cpu")
    for epp_file in cpu_sys.glob("cpu*/cpufreq/energy_performance_preference"):
        try:
            epp_file.write_text(epp_value, encoding="utf-8")
            success = True
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
            pass
    return success


def get_current_epp() -> str:
    """Get Energy Performance Preference of CPU 0."""
    epp_file = Path("/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference")
    if epp_file.is_file():
        try:
            return epp_file.read_text(encoding="utf-8").strip()
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
            pass
    return "n/a"


def set_power_profile(profile: str) -> bool:
    """Set the system power profile using powerprofilesctl."""
    if shutil.which("powerprofilesctl"):
        try:
            res = run_command(["powerprofilesctl", "set", profile], capture_output=True, check=False)
            return res.returncode == 0
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
            pass
    return False


def get_power_profile() -> str:
    """Get current active system power profile."""
    if shutil.which("powerprofilesctl"):
        try:
            res = run_command(["powerprofilesctl", "get"], capture_output=True, text=True, check=False)
            return res.stdout.strip()
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
            pass
    return "n/a"


def set_transparent_hugepages(setting: str) -> None:
    """Set transparent hugepages mode (e.g. 'madvise')."""
    thp = Path("/sys/kernel/mm/transparent_hugepage/enabled")
    if os.access(thp, os.W_OK):
        try:
            thp.write_text(f"{setting}\n", encoding="utf-8")
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
            pass


def switch_sched_ext_profile(profile: str) -> None:
    """Switch sched-ext low-latency scheduler profile using kyth-scx helper."""
    if shutil.which("scx_rusty") and shutil.which("sudo"):
        try:
            run_command(["sudo", "-n", "/usr/bin/kyth-scx", "set", profile], capture_output=True, check=False)
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
            pass


def apply_nvme_tuning() -> bool:
    """Apply low-latency I/O queue tuning for NVMe storage devices."""
    tuned_count = 0
    sys_block = Path("/sys/block")
    if sys_block.is_dir():
        for nvme_queue in sys_block.glob("nvme*/queue/scheduler"):
            try:
                nvme_queue.write_text("none\n", encoding="utf-8")
                tuned_count += 1
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                logger.debug("handled expected exception", exc_info=True)
                pass
    return tuned_count > 0


def get_gamescope_cmd(target_command: list[str]) -> list[str]:
    """Wrap a application command line with Gamescope launcher flags."""
    if not shutil.which("gamescope"):
        return target_command

    gamescope_cmd = [
        "gamescope",
        "-f",
        "-e",
        "--rt",
        "--",
    ] + target_command
    return gamescope_cmd


#: Single power owner: power-profiles-daemon (PPD). Everything else follows the
#: PPD profile instead of writing competing knobs.
POWER_PROFILE_OWNER = "power-profiles-daemon"

#: Launcher mode -> PPD profile.
MODE_POWER_PROFILE = {
    "gaming": "performance",
    "performance": "performance",
    "balanced": "balanced",
    "powersave": "power-saver",
}

#: PPD profile -> follower EPP value (mirrors kyth-performance-mode).
PPD_EPP_FOLLOWER = {
    "performance": "performance",
    "balanced": "balance_performance",
    "power-saver": "power",
}

POWER_OWNER_STATE_FILE = Path("/run/kyth/power-owner.state")


def apply_power_owner(mode: str) -> bool:
    """Set the PPD profile for *mode*, then the follower EPP. Returns PPD ok."""
    profile = MODE_POWER_PROFILE.get(mode, "balanced")
    owned = set_power_profile(profile)
    set_epp(PPD_EPP_FOLLOWER.get(profile, "balance_performance"))
    return owned


def save_power_state(path: Path | None = None) -> Path:
    """Persist the current PPD profile + EPP for crash-safe restore."""
    dest = Path(path) if path is not None else POWER_OWNER_STATE_FILE
    dest.parent.mkdir(parents=True, exist_ok=True)
    profile = get_power_profile()
    epp = get_current_epp()
    dest.write_text(
        "# Kyth power-owner state — restored on next apply/restore after a crash"
        + os.linesep
        + f"POWER_PROFILE={profile}"
        + os.linesep
        + f"EPP={epp}"
        + os.linesep,
        encoding="utf-8",
    )
    return dest


def restore_power_state(path: Path | None = None) -> bool:
    """Restore a saved PPD profile + EPP once, then drop the state file.

    Missing state (normal boot, /run is tmpfs) is a no-op True. The file is
    always removed after a restore attempt so a crash can only ever restore
    once — no stale loop.
    """
    dest = Path(path) if path is not None else POWER_OWNER_STATE_FILE
    try:
        text = dest.read_text(encoding="utf-8")
    except OSError:
        return True
    try:
        values: dict[str, str] = {}
        for line in text.splitlines():
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip()
        if values.get("POWER_PROFILE") and values["POWER_PROFILE"] != "n/a":
            set_power_profile(values["POWER_PROFILE"])
        if values.get("EPP") and values["EPP"] != "n/a":
            set_epp(values["EPP"])
    finally:
        try:
            dest.unlink()
        except OSError:
            pass
    return True


