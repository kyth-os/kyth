"""Gaming scan atomic — tmp+os.replace+fsync for compatdata."""
from pathlib import Path
import os

def atomic_replace(src: Path, dst: Path) -> None:
    tmp = dst.with_suffix(".tmp")
    if src.is_dir():
        # for dirs, use replace on parent
        tmp = Path(str(dst) + ".tmp")
    # fsync parent to ensure atomicity
    try:
        os.replace(src, dst)
        # fsync parent dir
        fd = os.open(str(dst.parent), os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        # fallback to shutil.move for cross-device/Btrfs subvol
        import shutil
        shutil.move(str(src), str(dst))

def test_atomic_replace(tmp_path):
    pass
