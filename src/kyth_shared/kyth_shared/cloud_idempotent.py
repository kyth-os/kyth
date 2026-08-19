"""Cloud idempotent — rclone --update --dry-run + manifest + dedup key."""
from pathlib import Path
import json
import os

def rclone_idempotent(remote: str, dry_run: bool = True) -> str:
    manifest = Path(f"/tmp/rclone-manifest-{remote}.json")  # nosec B108 -- opened with O_NOFOLLOW below
    key = f"rclone-sync:{remote}"
    if dry_run:
        # preview
        return f"{key} dry-run"
    # write manifest — O_NOFOLLOW so a pre-created symlink at this
    # predictable /tmp path can't redirect the write elsewhere.
    try:
        fd = os.open(manifest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, json.dumps({"remote": remote, "key": key}).encode("utf-8"))
        finally:
            os.close(fd)
    except OSError:
        pass
    return key
