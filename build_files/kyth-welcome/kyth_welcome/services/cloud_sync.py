"""Cloud sync helpers and optional Qt workers.

Pure command/token helpers import without Qt (CI unit tests). Worker classes
are defined only when Qt bindings are available (desktop image).
"""
from __future__ import annotations

import os
import re
import subprocess


def extract_rclone_token(text: str) -> str | None:
    """Parse token JSON from `rclone authorize` stdout/stderr."""
    start_marker = "Paste the following into your remote machine --->"
    end_marker = "<---End paste"
    if start_marker in text and end_marker in text:
        start = text.index(start_marker) + len(start_marker)
        end = text.index(end_marker, start)
        candidate = text[start:end].strip()
        if candidate.startswith("{"):
            return candidate
    m = re.search(r'\{"access_token"[^<>]*\}', text, re.DOTALL)
    if m:
        return m.group(0)
    return None


_extract_rclone_token = extract_rclone_token


def rclone_sync_command(remote: str, folder: str) -> list[str]:
    return [
        "rclone", "sync", f"{remote}:", folder,
        "--progress", "--stats-one-line", "--stats=2s",
    ]


def rsync_copy_command(src: str, dst: str) -> list[str]:
    return [
        "rsync", "-a", "--info=name1,progress2", "--no-inc-recursive",
        src.rstrip("/") + "/",
        dst.rstrip("/") + "/",
    ]


try:
    from ..qt import Signal
    from .runtime import TrackedThread
except ImportError:  # pragma: no cover - CI / headless unit tests without Qt
    Signal = None  # type: ignore[assignment,misc]
    TrackedThread = object  # type: ignore[assignment,misc]
    _HAS_QT = False
else:
    _HAS_QT = True


if _HAS_QT:
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

        def run(self):
            try:
                proc = subprocess.Popen(
                    rclone_sync_command(self._remote, self._folder),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                for ln in proc.stdout:
                    self.line.emit(ln.rstrip())
                proc.wait()
                self.done.emit(proc.returncode)
            except Exception as exc:
                self.line.emit(f"Error: {exc}")
                self.done.emit(1)
else:  # pragma: no cover
    SteamCopyWorker = None  # type: ignore[assignment,misc]
    RcloneAuthorizeWorker = None  # type: ignore[assignment,misc]
    RcloneSyncWorker = None  # type: ignore[assignment,misc]
