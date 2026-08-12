"""Work migration idempotent — PST/fonts re-copy idempotent."""
from pathlib import Path
import shutil

def work_migrate_idempotent(src: Path, dst: Path) -> bool:
    if dst.exists():
        # if dst newer, skip
        try:
            if dst.stat().st_mtime >= src.stat().st_mtime:
                return False
        except OSError:
            pass
    try:
        shutil.copy2(src, dst)
        return True
    except OSError:
        return False
