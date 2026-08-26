"""Hybrid-graphics GPU switching — a thin supergfxctl wrapper.

supergfxctl (asus-linux.org) ships its own systemd service and D-Bus
policy (see sysconfig/hardware/57-asus-dbus-policy-fixup.sh) and handles
its own polkit-backed privilege escalation, so this talks to the CLI
directly rather than going through services/privileged.py's gateway —
unlike the actions Kyth mediates itself, supergfxd already mediates this
one. Install stays opt-in via `ujust install-asus-tools`
(build_files/just/kyth/*.just); this module only detects whether it is
present and drives it if so — it never installs anything itself.
"""
from __future__ import annotations

import logging
import shutil
import subprocess

from kyth_welcome.services.command import run_sync

_logger = logging.getLogger(__name__)

# supergfxctl's own static mode list — AsusMuxDgpu only actually appears in
# `supergfxctl -s`'s output on hardware with a physical MUX switch. Used as
# a fallback if that output can't be parsed, not as a claim every mode is
# available on every machine.
SUPPORTED_MODES = ("Hybrid", "Integrated", "VFIO", "AsusMuxDgpu")


def supergfxctl_available() -> bool:
    return shutil.which("supergfxctl") is not None


def is_hybrid_system() -> bool:
    """True if this machine has both an NVIDIA GPU and another one to
    offload/switch to — the same inventory read Hub's NVIDIA detection
    already uses (see services/hardware/nvidia.py's _detect_nvidia)."""
    try:
        from kyth_shared.system.hardware_view import get_hardware_view

        return bool(get_hardware_view().is_hybrid)
    except (OSError, subprocess.SubprocessError, AttributeError, ImportError) as exc:
        _logger.debug("hybrid GPU detect failed: %s", exc)
        return False


def current_mode() -> str:
    """Current supergfxd mode, or "" if supergfxctl is missing/unreachable."""
    if not supergfxctl_available():
        return ""
    try:
        result = run_sync(["supergfxctl", "-g"], capture_output=True, text=True, timeout=5, check=False)
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        _logger.debug("supergfxctl -g failed: %s", exc)
        return ""


def supported_modes() -> tuple[str, ...]:
    """Modes this system's supergfxd actually offers. Falls back to the
    static list if the CLI's output can't be parsed — better a possibly
    stale list than none at all."""
    if not supergfxctl_available():
        return ()
    try:
        result = run_sync(["supergfxctl", "-s"], capture_output=True, text=True, timeout=5, check=False)
        raw = result.stdout.strip().strip("[]")
        modes = tuple(m.strip() for m in raw.split(",") if m.strip())
        return modes or SUPPORTED_MODES
    except (OSError, subprocess.SubprocessError) as exc:
        _logger.debug("supergfxctl -s failed: %s", exc)
        return SUPPORTED_MODES


def set_mode(mode: str) -> tuple[bool, str]:
    """Switch GPU mode. Hybrid<->Integrated needs a logout; AsusMuxDgpu
    needs a reboot — supergfxd's own reply carries that guidance, which is
    surfaced back to the caller verbatim rather than re-worded here."""
    if not supergfxctl_available():
        return False, "supergfxctl is not installed — run: ujust install-asus-tools"
    try:
        result = run_sync(["supergfxctl", "-m", mode], capture_output=True, text=True, timeout=10, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
            return False, detail
        return True, (result.stdout or f"Switched to {mode}").strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
