"""System state probing facade for KythOS."""
from __future__ import annotations

import configparser
import glob
import shutil
import subprocess


class SystemProbe:
    """Facade for read-only system state detection."""

    @staticmethod
    def get_firewall_status() -> str:
        try:
            res = subprocess.run(
                ["systemctl", "is-active", "firewalld"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5
            )
            return res.stdout.strip()
        except Exception:
            return "inactive"

    @staticmethod
    def get_selinux_status() -> str:
        try:
            res = subprocess.run(
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
            res = subprocess.run(
                ["mokutil", "--sb-state"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5
            )
            return res.stdout.strip().lower()
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
                res = subprocess.run(
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
