"""Gaming scan atomic — tmp+os.replace+fsync for compatdata."""
from pathlib import Path
import os

from .atomic_io import atomic_write_bytes, atomic_write_json, atomic_write_text

__all__ = ["atomic_replace", "atomic_write_text", "atomic_write_bytes", "atomic_write_json"]


def atomic_replace(src: Path, dst: Path) -> None:
    """Atomically move *src* to *dst* (file or directory) with parent fsync.

    Uses tmp+replace semantics where possible; falls back to shutil.move on
    cross-device / Btrfs subvol EXDEV. Parent directory is fsync'd on success
    to ensure durability across power loss.
    """
    try:
        os.replace(src, dst)
        # fsync parent dir to persist rename
        fd = os.open(str(dst.parent), os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        # fallback to shutil.move for cross-device/Btrfs subvol
        import shutil

        shutil.move(str(src), str(dst))
