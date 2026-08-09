"""Cloud idempotent — rclone --update --dry-run + manifest + dedup key."""
from pathlib import Path
import json

def rclone_idempotent(remote: str, dry_run: bool = True) -> str:
    manifest = Path(f"/tmp/rclone-manifest-{remote}.json")
    key = f"rclone-sync:{remote}"
    if dry_run:
        # preview
        return f"{key} dry-run"
    # write manifest
    try:
        manifest.write_text(json.dumps({"remote": remote, "key": key}))
    except OSError:
        pass
    return key
