"""Qt workers for Windows library scan and user-file copy."""
from __future__ import annotations

import os
import re
import subprocess
import sys

from ...qt import Signal
from ..gaming import _probe_windows_partitions
from ..runtime import TrackedThread


class WindowsLibraryWorker(TrackedThread):
    result = Signal(list)

    def run(self) -> None:
        try:
            partitions = _probe_windows_partitions()
        except Exception as exc:
            print(f"game library probe failed: {exc}", file=sys.stderr)
            partitions = []
        self.result.emit(partitions)


class UserFilesCopyWorker(TrackedThread):
    """Copies selected profile folders into the home directory via rsync."""
    BLOCKS_CLOSE = True
    status = Signal(str)
    overall = Signal(int)          # 0–100 across all folders  # noqa: RUF003 — en dash, deliberate typography
    done = Signal(int, int, bool)  # (ok, failed, cancelled)

    def __init__(self, jobs: list[tuple[str, str, str]]):
        super().__init__()
        self._jobs = jobs  # (folder name, src, dst)
        self._proc: subprocess.Popen | None = None
        self._stop = False

    def stop(self):
        self._stop = True
        proc = self._proc
        if proc and proc.poll() is None:
            proc.terminate()

    def run(self):
        ok = failed = 0
        total = len(self._jobs) or 1
        for idx, (name, src, dst) in enumerate(self._jobs):
            if self._stop:
                break
            self.status.emit(f"Copying {name}…")
            code = self._copy_one(idx, total, name, src, dst)
            if self._stop:
                break
            # 24 = source files vanished mid-copy; harmless for a one-way import.
            if code in (0, 24):
                ok += 1
            else:
                failed += 1
            self.overall.emit(int((idx + 1) * 100 / total))
        self.done.emit(ok, failed, self._stop)

    def _copy_one(self, idx: int, total: int, name: str, src: str, dst: str) -> int:
        try:
            os.makedirs(dst, exist_ok=True)
        except OSError:
            return 1
        # -rt without -p/-o/-g: NTFS carries no useful Unix permissions, so new
        # files get normal home-folder modes. --update never overwrites a file
        # that is already newer on the KythOS side.
        cmd = [
            "rsync", "-rt", "--update", "--info=progress2", "--no-inc-recursive",
            src.rstrip("/") + "/", dst.rstrip("/") + "/",
        ]
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except OSError:
            return 1
        # progress2 updates end with \r, not \n, so read raw chunks, not lines.
        fd = self._proc.stdout.fileno()
        tail = b""
        last_pct = -1
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            tail = (tail + chunk)[-256:]
            pcts = re.findall(rb"(\d+)%", tail)
            if pcts:
                pct = min(100, int(pcts[-1]))
                if pct != last_pct:
                    last_pct = pct
                    self.overall.emit(int((idx * 100 + pct) / total))
                    self.status.emit(f"Copying {name} — {pct}%")
        self._proc.wait()
        return self._proc.returncode
