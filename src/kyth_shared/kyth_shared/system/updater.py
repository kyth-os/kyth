"""Shared utilities for downloading, verifying, and extracting third-party system components."""
from __future__ import annotations
import logging

import hashlib
import json
import os
import shutil
import stat
import tarfile
import urllib.request
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)


_MAX_ARCHIVE_MEMBERS = 100_000
_MAX_ARCHIVE_BYTES = 16 * 1024**3


@dataclass(frozen=True)
class ReleaseAsset:
    """A normalized downloadable asset from a release document."""

    name: str
    url: str


def release_assets(release: dict) -> tuple[ReleaseAsset, ...]:
    """Return only well-formed assets, insulating providers from JSON details."""
    assets = []
    for item in release.get("assets", []):
        name = item.get("name")
        url = item.get("browser_download_url")
        if isinstance(name, str) and name and isinstance(url, str) and url:
            assets.append(ReleaseAsset(name, url))
    return tuple(assets)


def find_release_asset(
    assets: Iterable[ReleaseAsset],
    predicate: Callable[[str], bool],
) -> ReleaseAsset | None:
    """Find the first release asset whose name matches *predicate*."""
    return next((asset for asset in assets if predicate(asset.name)), None)


def validate_version(version: str, pattern: str, component: str) -> str:
    """Validate an externally supplied version before using it in paths/URLs."""
    import re

    if not re.fullmatch(pattern, version):
        raise ValueError(f"Unexpected {component} version format: {version}")
    return version


def prune_installations(
    install_dir: Path,
    pattern: str,
    *,
    keep: int = 2,
) -> tuple[Path, ...]:
    """Remove older version directories, retaining newest *keep* entries."""
    entries = sorted(
        (path for path in install_dir.glob(pattern) if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed = tuple(entries[max(0, keep):])
    for path in removed:
        shutil.rmtree(path)
    return removed


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
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
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


def verify_checksum_file(checksum_file: Path, target_file: Path, algorithm: str = "sha256") -> bool:
    """Require exactly one valid checksum entry for *target_file*."""
    target_info = target_file.lstat()
    if not stat.S_ISREG(target_info.st_mode) or stat.S_ISLNK(target_info.st_mode):
        raise ValueError(f"Checksum target is not a regular file: {target_file}")

    try:
        expected_length = hashlib.new(algorithm).digest_size * 2
    except ValueError as exc:
        raise ValueError(f"Unsupported checksum algorithm: {algorithm}") from exc

    matches: list[str] = []
    lines = checksum_file.read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            raise ValueError(f"Malformed checksum entry on line {line_number}")
        expected_hash, filename = parts
        if filename.startswith("*"):
            filename = filename[1:]
        if filename.startswith("./"):
            filename = filename[2:]
        if not filename or PurePosixPath(filename).name != filename:
            raise ValueError(f"Unsafe checksum filename on line {line_number}")
        if len(expected_hash) != expected_length or any(char not in "0123456789abcdefABCDEF" for char in expected_hash):
            raise ValueError(f"Malformed {algorithm} digest on line {line_number}")
        if filename == target_file.name:
            matches.append(expected_hash.lower())

    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one checksum for {target_file.name}, found {len(matches)}"
        )

    digest = hashlib.new(algorithm)
    with target_file.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    actual_hash = digest.hexdigest()
    if actual_hash.lower() != matches[0]:
        raise ValueError(
            f"Checksum mismatch for {target_file.name}: expected {matches[0]}, got {actual_hash.lower()}"
        )
    return True


def _archive_output_path(dest_dir: Path, member_name: str) -> Path:
    """Resolve a portable archive member name beneath *dest_dir*."""
    if "\0" in member_name:
        raise ValueError("Archive member contains a NUL byte")
    relative = PurePosixPath(member_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Directory traversal attempt detected: {member_name}")
    parts = tuple(part for part in relative.parts if part not in ("", "."))
    target = dest_dir.joinpath(*parts)
    if not target.resolve(strict=False).is_relative_to(dest_dir):
        raise ValueError(f"Directory traversal attempt detected: {member_name}")
    return target


def _ensure_safe_parent(dest_dir: Path, target: Path) -> None:
    relative_parent = target.parent.relative_to(dest_dir)
    current = dest_dir
    for part in relative_parent.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            info = current.lstat()
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise ValueError(f"Archive output traverses a non-directory: {current}")
        else:
            current.mkdir(mode=0o755)


def _write_archive_file(dest_dir: Path, target: Path, source, mode: int) -> None:
    _ensure_safe_parent(dest_dir, target)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(target, flags, mode & 0o777 or 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)
        os.fchmod(fd, mode & 0o777 or 0o600)
    finally:
        os.close(fd)


def _make_archive_directory(dest_dir: Path, target: Path) -> None:
    if target == dest_dir:
        return
    _ensure_safe_parent(dest_dir, target)
    if target.exists() or target.is_symlink():
        info = target.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ValueError(f"Archive directory is not a real directory: {target}")
    else:
        target.mkdir(mode=0o755)


def extract_archive(archive_path: Path, dest_dir: Path) -> None:
    """Extract regular files/directories without links, devices, or traversal."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_info = dest_dir.lstat()
    if not stat.S_ISDIR(dest_info.st_mode) or stat.S_ISLNK(dest_info.st_mode):
        raise ValueError(f"Archive destination is not a real directory: {dest_dir}")
    resolved_dest = dest_dir.resolve()

    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            members = zip_ref.infolist()
            if len(members) > _MAX_ARCHIVE_MEMBERS:
                raise ValueError("Archive contains too many members")
            if sum(member.file_size for member in members) > _MAX_ARCHIVE_BYTES:
                raise ValueError("Archive expands beyond the permitted size")
            seen: set[Path] = set()
            for member in members:
                target = _archive_output_path(resolved_dest, member.filename)
                if target in seen:
                    raise ValueError(f"Duplicate archive member: {member.filename}")
                seen.add(target)
                unix_mode = member.external_attr >> 16
                file_type = stat.S_IFMT(unix_mode)
                if stat.S_ISLNK(unix_mode) or file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError(f"Unsupported archive member type: {member.filename}")
                if member.is_dir():
                    _make_archive_directory(resolved_dest, target)
                    continue
                with zip_ref.open(member, "r") as source:
                    _write_archive_file(resolved_dest, target, source, unix_mode or 0o644)
    else:
        def safe_extract(tar_ref: tarfile.TarFile) -> None:
            members = tar_ref.getmembers()
            if len(members) > _MAX_ARCHIVE_MEMBERS:
                raise ValueError("Archive contains too many members")
            if sum(member.size for member in members) > _MAX_ARCHIVE_BYTES:
                raise ValueError("Archive expands beyond the permitted size")
            seen: set[Path] = set()
            for member in tar_ref.getmembers():
                target = _archive_output_path(resolved_dest, member.name)
                if target in seen:
                    raise ValueError(f"Duplicate archive member: {member.name}")
                seen.add(target)
                if member.isdir():
                    _make_archive_directory(resolved_dest, target)
                elif member.isreg():
                    source = tar_ref.extractfile(member)
                    if source is None:
                        raise ValueError(f"Could not read archive member: {member.name}")
                    with source:
                        _write_archive_file(resolved_dest, target, source, member.mode)
                else:
                    raise ValueError(f"Unsupported archive member type: {member.name}")

        if archive_path.name.endswith(".tar.xz") or archive_path.suffix == ".xz":
            with tarfile.open(archive_path, "r:xz") as tar_ref:
                safe_extract(tar_ref)
        elif archive_path.name.endswith(".tar.gz") or archive_path.suffix == ".gz":
            with tarfile.open(archive_path, "r:gz") as tar_ref:
                safe_extract(tar_ref)
        else:
            with tarfile.open(archive_path, "r:*") as tar_ref:
                safe_extract(tar_ref)
