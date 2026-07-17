"""Game night session manager."""
from __future__ import annotations

import os
import subprocess
import time

from ..process import _run_command


class GameNightManager:
    _inhibit_proc = None

    @classmethod
    def start(cls) -> bool:
        if cls._inhibit_proc and cls._inhibit_proc.poll() is None:
            return False

        subprocess.Popen(["kyth-performance-mode", "save"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(["kyth-performance-mode", "gaming"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if shutil.which("systemd-inhibit"):
            cls._inhibit_proc = subprocess.Popen(
                ["systemd-inhibit", "--what=idle:sleep", "--why=KythOS Game Night Mode", "sleep", "14400"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        return True

    @classmethod
    def stop(cls) -> None:
        if cls._inhibit_proc and cls._inhibit_proc.poll() is None:
            cls._inhibit_proc.terminate()
            cls._inhibit_proc = None
        subprocess.Popen(["kyth-performance-mode", "restore"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @classmethod
    def is_active(cls) -> bool:
        return cls._inhibit_proc is not None and cls._inhibit_proc.poll() is None


import atexit

def _cleanup_game_night():
    GameNightManager.stop()

atexit.register(_cleanup_game_night)


