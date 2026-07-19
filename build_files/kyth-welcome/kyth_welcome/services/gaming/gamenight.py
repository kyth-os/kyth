"""Game night session manager."""
from __future__ import annotations

import atexit
import shutil
import subprocess


class GameNightManager:
    _inhibit_proc = None

    @classmethod
    def start(cls) -> bool:
        if cls._inhibit_proc and cls._inhibit_proc.poll() is None:
            return False

        for cmd in (
            ["kyth-performance-mode", "save"],
            ["kyth-performance-mode", "gaming"],
        ):
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                pass

        if shutil.which("systemd-inhibit"):
            try:
                cls._inhibit_proc = subprocess.Popen(
                    [
                        "systemd-inhibit",
                        "--what=idle:sleep",
                        "--why=KythOS Game Night Mode",
                        "sleep",
                        "14400",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                cls._inhibit_proc = None
        return True

    @classmethod
    def stop(cls) -> None:
        if cls._inhibit_proc and cls._inhibit_proc.poll() is None:
            try:
                cls._inhibit_proc.terminate()
            except Exception:
                pass
            cls._inhibit_proc = None
        try:
            subprocess.Popen(
                ["kyth-performance-mode", "restore"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass

    @classmethod
    def is_active(cls) -> bool:
        return cls._inhibit_proc is not None and cls._inhibit_proc.poll() is None


def _cleanup_game_night():
    try:
        GameNightManager.stop()
    except Exception:
        pass


atexit.register(_cleanup_game_night)
