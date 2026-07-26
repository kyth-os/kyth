"""BitLocker unlock, Windows profile folder dests (pure).

Qt workers: ``services.workers.windows_migration``.
"""
from __future__ import annotations

import os
import re
import subprocess

from kyth_welcome.services.command import run_sync

from ..process import _command_stdout

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
        r = run_sync(
            ["udisksctl", "unlock", "-b", dev, "--key-file", "/dev/stdin"],
            input=key, capture_output=True, text=True, timeout=180, check=False,
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
        rm = run_sync(
            ["udisksctl", "mount", "-b", m.group(1)],
            capture_output=True, text=True, timeout=60, check=False,
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
                result = run_sync(
                    ["du", "-sb", path], text=True, timeout=600, check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                sizes[name] = int(result.stdout.split()[0])
            except Exception:
                sizes[name] = -1
        return sizes
    return _calc


_folder_sizes_calc = folder_sizes_calc


def __getattr__(name: str):
    if name in {"WindowsLibraryWorker", "UserFilesCopyWorker"}:
        from ..workers.windows_migration import UserFilesCopyWorker, WindowsLibraryWorker
        return {
            "WindowsLibraryWorker": WindowsLibraryWorker,
            "UserFilesCopyWorker": UserFilesCopyWorker,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
