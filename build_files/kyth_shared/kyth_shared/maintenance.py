"""Shared utilities for KythOS system maintenance and cleanups."""
from __future__ import annotations

import os
import shutil
import subprocess

from .commands import run as run_command
from datetime import datetime, timezone
from pathlib import Path


def prune_trash(days: int = 30) -> None:
    """Prune trash files and their metadata if older than the specified days."""
    home = Path.home()
    info_dir = home / ".local/share/Trash/info"
    files_dir = home / ".local/share/Trash/files"

    if not info_dir.is_dir():
        return

    now = datetime.now(timezone.utc)
    for info_file in info_dir.glob("*.trashinfo"):
        try:
            deletion_date_str = None
            with open(info_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("DeletionDate="):
                        deletion_date_str = line.split("=", 1)[1].strip()
                        break

            if not deletion_date_str:
                continue

            # Try parsing ISO format (e.g. 2026-07-20T14:30:00)
            try:
                # Add timezone if missing to compare with timezone-aware datetime
                dt = datetime.fromisoformat(deletion_date_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

            age_seconds = (now - dt).total_seconds()
            if age_seconds > days * 86400:
                # Resolve original file name from trashinfo stem or Path name
                # In Trash spec, the file in files/ has the same name as the trashinfo (minus extension)
                name = info_file.stem
                # Decode url-encoded names if necessary, but files/ uses the same filesystem name
                target_path = files_dir / name

                # Safely delete
                if target_path.exists():
                    if target_path.is_dir() and not target_path.is_symlink():
                        shutil.rmtree(target_path, ignore_errors=True)
                    else:
                        target_path.unlink(missing_ok=True)
                info_file.unlink(missing_ok=True)
        except Exception:
            pass


def cleanup_flatpaks() -> None:
    """Uninstall unused flatpak packages in non-interactive mode."""
    if shutil.which("flatpak"):
        try:
            run_command(
                ["flatpak", "uninstall", "--unused", "-y", "--noninteractive"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def vacuum_user_journals(days: int = 30) -> None:
    """Vacuum systemd user journal files older than specified days."""
    if shutil.which("journalctl"):
        try:
            run_command(
                ["journalctl", "--user", f"--vacuum-time={days}d"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def supports_dedupe(path: str) -> bool:
    """Check if filesystem of given path supports deduplication (btrfs or xfs)."""
    if not shutil.which("findmnt"):
        return False
    try:
        res = run_command(
            ["findmnt", "-no", "FSTYPE", "-T", path],
            capture_output=True,
            text=True,
            check=False,
        )
        fstype = res.stdout.strip().lower()
        return fstype in ("btrfs", "xfs")
    except Exception:
        return False


def find_dedupe_targets(root_path: str = "/var/home") -> list[str]:
    """Scan root_path up to depth 7 for Steam compatdata or shadercache dirs."""
    targets = []

    def walk_depth(current_path: Path, depth: int) -> None:
        if depth > 7:
            return
        try:
            for entry in os.scandir(current_path):
                if entry.is_dir(follow_symlinks=False):
                    epath = entry.path
                    if depth >= 4:
                        # Check path endings
                        if epath.endswith("/Steam/steamapps/compatdata") or epath.endswith("/Steam/steamapps/shadercache"):
                            targets.append(epath)
                            continue
                    walk_depth(Path(epath), depth + 1)
        except Exception:
            pass

    root = Path(root_path)
    if root.is_dir():
        walk_depth(root, 1)
    return sorted(list(set(targets)))


def dedupe_directory(dir_path: str) -> None:
    """Perform deduplication on the given directory using duperemove."""
    if not shutil.which("duperemove"):
        return
    # Generate unique hash filename from path
    hash_name = dir_path.replace("/", "__").replace(" ", "__")
    hash_file = f"/var/tmp/{hash_name}.duperemove.hash"

    # Run nice/ionice wrapper
    cmd = [
        "nice", "-n", "19",
        "duperemove", "-rdh", "--hashfile", hash_file, dir_path
    ]
    if shutil.which("ionice"):
        cmd = ["ionice", "-c3"] + cmd

    try:
        run_command(cmd, check=False)
    except Exception:
        pass
