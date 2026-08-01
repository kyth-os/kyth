"""kyth_shared.thirdparty — Module for managing thirdparty application & CDM installations."""
from __future__ import annotations

import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

VERSION_URL = "https://dl.google.com/widevine-cdm/versions.txt"
CDM_BASE = "https://dl.google.com/widevine-cdm"


def fetch_widevine_version() -> str | None:
    """Fetch the latest Widevine CDM version string."""
    try:
        req = urllib.request.Request(VERSION_URL, headers={"User-Agent": "KythOS"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            line = resp.readline().decode("utf-8", errors="replace").strip()
            return line if line else None
    except Exception:
        return None


def download_file(url: str, dest: Path) -> bool:
    """Download a file via HTTP/HTTPS to a destination path."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KythOS"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
            shutil.copyfileobj(resp, out)
        return True
    except Exception:
        return False


def install_widevine_cdm() -> int:
    """Install Widevine CDM for supported Flatpak browsers (Firefox, Chromium)."""
    version = fetch_widevine_version()
    if not version:
        sys.stderr.write(f"Error: Could not fetch Widevine version list from {VERSION_URL}\n")
        return 1

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        zip_path = tmp_path / "widevine.zip"

        download_url = f"{CDM_BASE}/{version}-linux-x64.zip"
        if not download_file(download_url, zip_path):
            sys.stderr.write("Error: Download failed\n")
            return 1

        cdm_dir = tmp_path / "cdm"
        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(cdm_dir)
        except Exception as exc:
            sys.stderr.write(f"Error: Failed to extract zip: {exc}\n")
            return 1

        lib_file = cdm_dir / "libwidevinecdm.so"
        manifest_file = cdm_dir / "manifest.json"
        if not lib_file.is_file() or not manifest_file.is_file():
            sys.stderr.write("Error: Required Widevine files missing in extracted archive\n")
            return 1

        installed = 0
        home = Path.home()

        targets = [
            ("org.mozilla.firefox", home / ".var" / "app" / "org.mozilla.firefox" / "config" / "google-chrome" / "WidevineCdm" / version),
            ("org.chromium.Chromium", home / ".var" / "app" / "org.chromium.Chromium" / "config" / "chromium" / "WidevineCdm" / version),
        ]

        for app_id, cdm_dest in targets:
            app_var = home / ".var" / "app" / app_id
            if app_var.is_dir():
                lib_dir = cdm_dest / "_platform_specific" / "linux_x64"
                lib_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(manifest_file, cdm_dest / "manifest.json")
                shutil.copy2(lib_file, lib_dir / "libwidevinecdm.so")
                installed += 1

        if installed > 0:
            return 0
        return 1


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
