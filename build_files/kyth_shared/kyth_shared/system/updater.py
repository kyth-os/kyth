"""Shared utilities for downloading, verifying, and extracting third-party system components."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import urllib.request
import zipfile
from pathlib import Path


def get_github_headers() -> dict[str, str]:
    """Retrieve default GitHub headers, incorporating auth tokens if available."""
    headers = {
        "User-Agent": "KythOS-Updater/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    token = None
    secret_path = Path("/run/secrets/github_token")
    if secret_path.is_file():
        try:
            token = secret_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    if not token:
        token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def fetch_github_latest_release(repo: str) -> dict:
    """Fetch JSON metadata for the latest release of a GitHub repository."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers=get_github_headers())
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def download_file(url: str, dest: Path, headers: dict[str, str] | None = None) -> None:
    """Download a file from a URL to the specified destination path."""
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=120) as response, dest.open("wb") as f:
        shutil.copyfileobj(response, f)


def verify_checksum_file(checksum_file: Path, target_dir: Path, algorithm: str = "sha256") -> bool:
    """Verify files listed in a checksum file (e.g. SHA256SUMS) that exist in the target directory."""
    lines = checksum_file.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if not line.strip():
            continue
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        expected_hash, filename = parts
        if filename.startswith("*"):
            filename = filename[1:]
        
        # Only verify files that are present in the target directory
        file_to_check = target_dir / filename
        if file_to_check.is_file():
            h = hashlib.new(algorithm)
            with file_to_check.open("rb") as f:
                while chunk := f.read(8192):
                    h.update(chunk)
            actual_hash = h.hexdigest()
            if actual_hash.lower() != expected_hash.lower():
                raise ValueError(
                    f"Checksum mismatch for {filename}: expected {expected_hash.lower()}, got {actual_hash.lower()}"
                )
    return True


def extract_archive(archive_path: Path, dest_dir: Path) -> None:
    """Extract a ZIP or TAR archive to the destination directory."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            zip_ref.extractall(dest_dir)
    else:
        def safe_extract(tar_ref: tarfile.TarFile) -> None:
            resolved_dest = dest_dir.resolve()
            members = []
            for member in tar_ref.getmembers():
                target_path = (resolved_dest / member.name).resolve()
                if not target_path.is_relative_to(resolved_dest):
                    raise ValueError(f"Directory traversal attempt detected: {member.name}")
                members.append(member)
            tar_ref.extractall(resolved_dest, members=members)

        if archive_path.name.endswith(".tar.xz") or archive_path.suffix == ".xz":
            with tarfile.open(archive_path, "r:xz") as tar_ref:
                safe_extract(tar_ref)
        elif archive_path.name.endswith(".tar.gz") or archive_path.suffix == ".gz":
            with tarfile.open(archive_path, "r:gz") as tar_ref:
                safe_extract(tar_ref)
        else:
            with tarfile.open(archive_path, "r:*") as tar_ref:
                safe_extract(tar_ref)
