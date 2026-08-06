"""Windows NTFS Documents/Pictures migration helpers.

Pure helpers for the Welcome 'Migrate from Windows' card — enumerate
mounted NTFS drives (via _find_ntfs_drives, probe_cached 30s) and locate
Users/<name>/Documents|Pictures without auto-mounting BitLocker volumes.
Rsync commands are built as argv lists for Worker (no shell)."""
from __future__ import annotations

import os


def _ntfs_user_dirs() -> list[dict]:
    """Return candidate Windows user dirs found on mounted NTFS partitions.

    Each entry: {mount, user, kind, path, exists}. Does not mount.
    BitLocker partitions have mount=='' and are skipped."""
    try:
        from .hardware.drives import _find_ntfs_drives
    except Exception:
        return []
    try:
        drives = _find_ntfs_drives()
    except Exception:
        return []
    results: list[dict] = []
    for drive in drives:
        mount = (drive.get("mount") or "").strip() if isinstance(drive, dict) else ""
        if not mount or not os.path.isdir(mount):
            continue
        users_root = os.path.join(mount, "Users")
        try:
            entries = os.listdir(users_root)
        except OSError:
            continue
        for user in entries:
            if user.lower() in {"public", "default", "all users", "default user"}:
                continue
            user_path = os.path.join(users_root, user)
            if not os.path.isdir(user_path):
                continue
            for kind in ("Documents", "Pictures", "Downloads"):
                p = os.path.join(user_path, kind)
                results.append({
                    "mount": mount,
                    "user": user,
                    "kind": kind,
                    "path": p,
                    "exists": os.path.isdir(p),
                })
    return results


def migration_preview_command(src: str, dst: str) -> list[str]:
    """Build `rsync -a --dry-run --human-readable --stats` argv for preview."""
    if not src or not dst or any(c in src + dst for c in ("\0", "\n", "\r")):
        raise ValueError("Invalid src/dst for migration preview")
    return ["rsync", "-a", "--dry-run", "--human-readable", "--stats", src.rstrip("/") + "/", dst.rstrip("/") + "/"]


def migration_apply_command(src: str, dst: str) -> list[str]:
    """Build `rsync -a` argv for actual migration."""
    if not src or not dst or any(c in src + dst for c in ("\0", "\n", "\r")):
        raise ValueError("Invalid src/dst for migration apply")
    return ["rsync", "-a", src.rstrip("/") + "/", dst.rstrip("/") + "/"]
