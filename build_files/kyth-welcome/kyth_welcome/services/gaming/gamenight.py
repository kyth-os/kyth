"""Game night session manager."""
from __future__ import annotations

import atexit
import logging
import shutil
import subprocess
from typing import ClassVar

_logger = logging.getLogger(__name__)


class GameNightManager:
    _inhibit_proc = None
    _action_procs: ClassVar[list[subprocess.Popen]] = []
    _started = False

    @classmethod
    def _spawn_action(cls, cmd: list[str]) -> None:
        cls._action_procs = [proc for proc in cls._action_procs if proc.poll() is None]
        try:
            cls._action_procs.append(
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            )
        except FileNotFoundError:
            pass

    @classmethod
    def start(cls) -> bool:
        if cls._started:
            return False

        for cmd in (
            ["kyth-performance-mode", "save"],
            ["kyth-performance-mode", "gaming"],
        ):
            cls._spawn_action(cmd)

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
        cls._started = True
        return True

    @classmethod
    def stop(cls) -> None:
        if cls._inhibit_proc and cls._inhibit_proc.poll() is None:
            try:
                cls._inhibit_proc.terminate()
                cls._inhibit_proc.wait(timeout=5)
            except Exception:
                _logger.debug("stop: terminating the idle-inhibit process failed", exc_info=True)
            cls._inhibit_proc = None
        if cls._started:
            cls._spawn_action(["kyth-performance-mode", "restore"])
            cls._started = False

    @classmethod
    def is_active(cls) -> bool:
        return cls._started


def _cleanup_game_night():
    try:
        GameNightManager.stop()
        for proc in GameNightManager._action_procs:
            try:
                proc.wait(timeout=15)
            except Exception:
                proc.kill()
                proc.wait()
        GameNightManager._action_procs.clear()
    except Exception:
        _logger.debug("_cleanup_game_night: cleanup at exit failed", exc_info=True)


atexit.register(_cleanup_game_night)
