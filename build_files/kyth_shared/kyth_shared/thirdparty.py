"""Helpers for third-party applications that operate on user-supplied files."""
from __future__ import annotations

from pathlib import Path


def find_latest_davinci_zip(download_dir: Path | None = None) -> Path | None:
    """Locate the latest DaVinci Resolve Linux zip file in download directories."""
    if download_dir is None:
        download_dir = Path.home() / "Downloads"

    candidates: list[Path] = []
    roots = [download_dir, Path.home() / "Downloads"]
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.glob("*"):
            if p.is_file() and ("DaVinci" in p.name and p.name.endswith(".zip")):
                candidates.append(p)

    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def prepare_davinci_resolve(zip_path: Path) -> dict[str, str]:
    """Inspect and resolve metadata for DaVinci Resolve installation."""
    if not zip_path.is_file():
        raise FileNotFoundError(f"ZIP file does not exist: {zip_path}")

    zip_name = zip_path.name.lower()
    is_studio = "studio" in zip_name
    app_id = "com.blackmagic.ResolveStudio" if is_studio else "com.blackmagic.Resolve"
    manifest = "com.blackmagic.ResolveStudio.yaml" if is_studio else "com.blackmagic.Resolve.yaml"

    return {
        "zip_path": str(zip_path),
        "app_id": app_id,
        "manifest": manifest,
        "is_studio": "true" if is_studio else "false",
    }
