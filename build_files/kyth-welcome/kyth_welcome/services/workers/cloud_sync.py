"""Qt workers for rclone / rsync cloud and Steam library copy."""
from __future__ import annotations

import os
import subprocess

from ...qt import Signal
from ..cloud_sync import extract_rclone_token, rclone_sync_command, rsync_copy_command
from ..runtime import TrackedThread


class SteamCopyWorker(TrackedThread):
    """Copies a steamapps directory using rsync, streaming output line-by-line."""
    BLOCKS_CLOSE = True
    line = Signal(str)
    done = Signal(int)

    def __init__(self, src: str, dst: str):
        super().__init__()
        self._src = src
        self._dst = dst
        self._proc = None

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def run(self):
        try:
            os.makedirs(self._dst, exist_ok=True)
        except OSError as exc:
            self.line.emit(f"Error creating destination: {exc}")
            self.done.emit(1)
            return
        cmd = rsync_copy_command(self._src, self._dst)
        self.line.emit(f"→ {' '.join(cmd)}\n")
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for ln in self._proc.stdout:
                self.line.emit(ln.rstrip())
            self._proc.wait()
            self.done.emit(self._proc.returncode)
        except Exception as exc:
            self.line.emit(f"Error: {exc}")
            self.done.emit(1)


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
            self._proc = subprocess.Popen(
                ["rclone", "authorize", self._remote_type],
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


class RcloneSyncWorker(TrackedThread):
    """Runs `rclone sync remote: folder --progress` and streams output lines."""
    BLOCKS_CLOSE = True
    line = Signal(str)
    done = Signal(int)

    def __init__(self, remote: str, folder: str):
        super().__init__()
        self._remote = remote
        self._folder = folder
        self._proc: subprocess.Popen[str] | None = None

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def run(self):
        try:
            self._proc = subprocess.Popen(
                rclone_sync_command(self._remote, self._folder),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert self._proc.stdout
            for ln in self._proc.stdout:
                self.line.emit(ln.rstrip())
            self._proc.wait()
            self.done.emit(self._proc.returncode)
        except Exception as exc:
            self.line.emit(f"Error: {exc}")
            self.done.emit(1)
