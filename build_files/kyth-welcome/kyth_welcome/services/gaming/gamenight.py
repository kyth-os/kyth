"""Game night session manager."""
from __future__ import annotations

import atexit
import logging
import shutil
import subprocess
from typing import ClassVar

from kyth_shared.commands import APPLICATION_RUNNER, command_spec

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
                APPLICATION_RUNNER.spawn(
                    command_spec(cmd, name="game-night-action", timeout=None),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
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
                command = [
                        "systemd-inhibit",
                        "--what=idle:sleep",
                        "--why=KythOS Game Night Mode",
                        "sleep",
                        "14400",
                    ]
                cls._inhibit_proc = APPLICATION_RUNNER.spawn(
                    command_spec(command, name="game-night-inhibit", timeout=None),
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
            except (OSError, subprocess.SubprocessError) as exc:
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
    except (OSError, RuntimeError) as exc:
        _logger.debug("_cleanup_game_night: GameNightManager.stop failed", exc_info=True)
    finally:
        for proc in list(GameNightManager._action_procs):
            try:
                proc.wait(timeout=15)
            except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError) as exc:
                _logger.debug("_cleanup_game_night: wait(15) failed %s", exc, exc_info=True)
                try:
                    proc.kill()
                except (OSError, subprocess.SubprocessError) as exc2:
                    _logger.debug("_cleanup_game_night: kill failed %s", exc2, exc_info=True)
                try:
                    proc.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError) as exc3:
                    _logger.debug("_cleanup_game_night: wait(5) failed %s", exc3, exc_info=True)
        GameNightManager._action_procs.clear()


atexit.register(_cleanup_game_night)