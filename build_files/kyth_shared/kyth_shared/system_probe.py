"""System state probing facade for KythOS."""
from __future__ import annotations

import configparser
import glob
import shutil
import subprocess
import time as _time

from .commands import run as run_command
from .runtime_output import parse_secure_boot_state, parse_systemd_state

_PROBE_CACHE: tuple[float, dict[str, str | bool]] | None = None
_PROBE_TTL = 30.0


class SystemProbe:
    """Facade for read-only system state detection."""

    @staticmethod
    def get_firewall_status() -> str:
        try:
            res = run_command(
                ["systemctl", "is-active", "firewalld"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5
            )
            return parse_systemd_state(res.stdout)
        except Exception:
            return "inactive"

    @staticmethod
    def get_selinux_status() -> str:
        try:
            res = run_command(
                ["getenforce"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5
            )
            return res.stdout.strip()
        except Exception:
            return ""

    @staticmethod
    def get_secure_boot_status() -> str:
        try:
            res = run_command(
                ["mokutil", "--sb-state"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5
            )
            return parse_secure_boot_state(res.stdout)
        except Exception:
            return ""

    @staticmethod
    def get_autologin_user() -> str:
        config = configparser.ConfigParser(interpolation=None, strict=False)
        config.optionxform = str
        sddm_files = ["/etc/sddm.conf", *sorted(glob.glob("/etc/sddm.conf.d/*.conf"))]
        try:
            config.read(sddm_files)
            return config.get("Autologin", "User", fallback="").strip()
        except (configparser.Error, OSError):
            return ""

    @staticmethod
    def _kreadconfig(file: str, group: str, key: str) -> str:
        if shutil.which("kreadconfig6"):
            try:
                res = run_command(
                    ["kreadconfig6", "--file", file, "--group", group, "--key", key],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=5
                )
                return res.stdout.strip()
            except Exception:
                return ""
        return ""

    @classmethod
    def get_screen_lock_status(cls) -> tuple[bool, bool]:
        """Returns (autolock_enabled, lock_on_resume_enabled)."""
        autolock = (cls._kreadconfig("kscreenlockerrc", "Daemon", "Autolock") or "true").lower()
        lock_resume = (cls._kreadconfig("kscreenlockerrc", "Daemon", "LockOnResume") or "true").lower()
        return (autolock not in ("false", "0"), lock_resume not in ("false", "0"))

    @classmethod
    def get_kwallet_enabled(cls) -> bool:
        wallet_enabled = (cls._kreadconfig("kwalletrc", "Wallet", "Enabled") or "true").lower()
        return wallet_enabled not in ("false", "0")

    @classmethod
    def invalidate_probe_cache(cls) -> None:
        global _PROBE_CACHE
        _PROBE_CACHE = None

    @classmethod
    def get_probe_snapshot(cls) -> dict[str, str | bool]:
        """Return a aggregated snapshot of system state."""
        global _PROBE_CACHE
        if _PROBE_CACHE is not None:
            _ts, _val = _PROBE_CACHE
            if _time.monotonic() - _ts < _PROBE_TTL:
                return dict(_val)
        autolock, lock_resume = cls.get_screen_lock_status()
        snap = {
            "firewall": cls.get_firewall_status(),
            "selinux": cls.get_selinux_status(),
            "secure_boot": cls.get_secure_boot_status(),
            "autologin_user": cls.get_autologin_user(),
            "autolock": autolock,
            "lock_on_resume": lock_resume,
            "kwallet_enabled": cls.get_kwallet_enabled(),
        }
        _PROBE_CACHE = (_time.monotonic(), dict(snap))
        return snap

    @classmethod
    def export_probe_cache(cls, path_str: str = "/run/kyth/hardware-probe.json") -> bool:
        """Export hardware and system probe data to a runtime cache file."""
        import json
        from pathlib import Path
        try:
            p = Path(path_str)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(cls.get_probe_snapshot(), indent=2), encoding="utf-8")
            return True
        except OSError:
            return False

