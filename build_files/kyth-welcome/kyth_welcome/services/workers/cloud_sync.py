"""Qt workers for rclone / rsync cloud and Steam library copy."""
from __future__ import annotations

import os
import subprocess

from kyth_shared.commands import APPLICATION_RUNNER, command_spec

from ...qt import Signal
from ..cloud_sync import extract_rclone_token, rclone_sync_command, rsync_copy_command
from ..runtime import StreamingProcessWorker, TrackedThread


class SteamCopyWorker(StreamingProcessWorker):
    """Copies a steamapps directory using rsync, streaming output line-by-line."""

    def __init__(self, src: str, dst: str):
        super().__init__()
        self._src = src
        self._dst = dst

    def command(self) -> list[str]:
        return rsync_copy_command(self._src, self._dst)

    def prepare(self, cmd: list[str]) -> bool:
        try:
            os.makedirs(self._dst, exist_ok=True)
        except OSError as exc:
            self.line.emit(f"Error creating destination: {exc}")
            self.done.emit(1)
            return False
        self.line.emit(f"→ {' '.join(cmd)}\n")
        return True


class RcloneAuthorizeWorker(TrackedThread):
    """Runs `rclone authorize <type>`; emits the token JSON on success."""
    token_ready = Signal(str)
    failed = Signal(str)

    def __init__(self, remote_type: str):
        super().__init__()
        self._remote_type = remote_type
        self._proc = None

    def run(self):
        try:
            self._proc = APPLICATION_RUNNER.spawn(
                command_spec(["rclone", "authorize", self._remote_type], name="rclone-authorize", timeout=None),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
            )
            stdout, stderr = self._proc.communicate(timeout=300)
            if self._proc.returncode != 0 and not stdout.strip():
                self.failed.emit(
                    f"rclone authorize exited with code {self._proc.returncode}.\n\n"
                    f"{stderr.strip()[:400]}"
                )
                return
            token = extract_rclone_token(stdout) or extract_rclone_token(stderr)
            if token:
                self.token_ready.emit(token)
            else:
                combined = (stdout + stderr).strip()
                self.failed.emit(
                    "Authorization completed but could not parse the token.\n\n"
                    f"Output:\n{combined[:600]}"
                )
        except subprocess.TimeoutExpired:
            if self._proc:
                self._proc.kill()
                self._proc.wait()
            self.failed.emit("Authorization timed out after 5 minutes.")
        except Exception as exc:
            self.failed.emit(str(exc))

    def cancel(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


class RcloneSyncWorker(StreamingProcessWorker):
    """Runs `rclone sync remote: folder --progress` and streams output lines."""

    def __init__(self, remote: str, folder: str):
        super().__init__()
        self._remote = remote
        self._folder = folder

    def command(self) -> list[str]:
        return rclone_sync_command(self._remote, self._folder)
