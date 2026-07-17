"""BitLocker unlock, Windows profile folder dests, and user-file copy workers."""
from __future__ import annotations

import os
import re
import subprocess
import sys

from ...qt import Signal
from ..gaming import _probe_windows_partitions
from ..process import _command_stdout
from ..runtime import TrackedThread

# The source system stores profile folders under their English names on disk
# regardless of display language, so these source names are locale-safe.
# Destinations go through xdg-user-dir so localized Linux home folders are honoured.
_XDG_FOLDER_KEYS = {
    "Desktop": "DESKTOP",
    "Documents": "DOCUMENTS",
    "Downloads": "DOWNLOAD",
    "Pictures": "PICTURES",
    "Music": "MUSIC",
    "Videos": "VIDEOS",
}


def unlock_bitlocker_drive(dev: str, key: str) -> tuple[bool, str]:
    """Unlock a BitLocker partition via udisks and mount the cleartext device.

    cryptsetup's bitlk backend accepts either the user password or the 48-digit
    recovery key as the passphrase. Runs on a worker thread (polkit may prompt).
    """
    try:
        r = subprocess.run(
            ["udisksctl", "unlock", "-b", dev, "--key-file", "/dev/stdin"],
            input=key, capture_output=True, text=True, timeout=180,
        )
    except Exception as exc:
        return False, str(exc)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip() or "Unlock failed."
    # udisksctl prints: "Unlocked /dev/sda3 as /dev/dm-3."
    m = re.search(r"\bas (/dev/\S+?)\.?\s*$", r.stdout.strip())
    if not m:
        return True, "Unlocked — rescan to mount the drive."
    try:
        rm = subprocess.run(
            ["udisksctl", "mount", "-b", m.group(1)],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as exc:
        return False, str(exc)
    if rm.returncode != 0:
        return False, (rm.stderr or rm.stdout).strip() or "Mount failed."
    return True, rm.stdout.strip()


# Underscore alias for page call sites
_unlock_bitlocker_drive = unlock_bitlocker_drive


def windows_folder_dest(folder: str) -> str:
    home = os.path.expanduser("~")
    if folder == "Saved Games":
        return os.path.join(windows_folder_dest("Documents"), "Saved Games")
    key = _XDG_FOLDER_KEYS.get(folder)
    if key:
        path = _command_stdout(["xdg-user-dir", key], timeout=5)
        # xdg-user-dir answers $HOME itself for unset entries; don't copy there.
        if path and os.path.abspath(path) != home:
            return path
    return os.path.join(home, folder)


_windows_folder_dest = windows_folder_dest


def folder_sizes_calc(paths: dict[str, str]):
    def _calc() -> dict[str, int]:
        sizes: dict[str, int] = {}
        for name, path in paths.items():
            try:
                out = subprocess.check_output(
                    ["du", "-sb", path], text=True, timeout=600,
                    stderr=subprocess.DEVNULL,
                )
                sizes[name] = int(out.split()[0])
            except Exception:
                sizes[name] = -1
        return sizes
    return _calc


_folder_sizes_calc = folder_sizes_calc


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
    overall = Signal(int)          # 0–100 across all folders
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
