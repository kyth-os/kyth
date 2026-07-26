#!/usr/bin/env python3
"""Export and restore a portable KythOS desktop setup archive."""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from kyth_shared.commands import run_text


ARCHIVE_VERSION = 1
ARCHIVE_PREFIX = "kyth-setup"
FLATHUB_REPO = "https://dl.flathub.org/repo/flathub.flatpakrepo"

# Deliberately excludes browser profiles, KWallet data, rclone.conf, and SMB
# credential files. Those contain passwords, cookies, or OAuth tokens.
CONFIG_PATHS = (
    ".config/kdeglobals",
    ".config/kglobalshortcutsrc",
    ".config/kwinrc",
    ".config/kwinrulesrc",
    ".config/kcminputrc",
    ".config/kscreenlockerrc",
    ".config/klipperrc",
    ".config/plasmarc",
    ".config/powerdevilrc",
    ".config/spectaclerc",
    ".config/konsolerc",
    ".config/kwalletrc",
    ".config/kyth-cloud-sync.json",
    ".config/kyth-dynamic-lock.json",
    ".config/kyth-smb-shares.json",
    ".config/MangoHud",
    ".config/vkBasalt",
    ".local/share/kyth/profile",
)

DEFAULT_MIME_TYPES = (
    "text/html",
    "x-scheme-handler/http",
    "x-scheme-handler/https",
    "x-scheme-handler/mailto",
    "application/pdf",
    "image/jpeg",
    "image/png",
    "video/mp4",
    "audio/mpeg",
    "text/plain",
    "inode/directory",
)


def _run(cmd: list[str], timeout: int = 30):
    return run_text(cmd, timeout=timeout)


def _installed_flatpaks() -> list[dict[str, str]]:
    result = _run(["flatpak", "list", "--app", "--columns=application,origin"])
    if result is None or result.returncode != 0:
        return []
    apps: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 1)
        app_id = parts[0].strip()
        if not app_id:
            continue
        apps.append({
            "id": app_id,
            "origin": parts[1].strip() if len(parts) > 1 else "flathub",
        })
    return sorted(apps, key=lambda item: item["id"].lower())


def _default_apps() -> dict[str, str]:
    defaults: dict[str, str] = {}
    for mime in DEFAULT_MIME_TYPES:
        result = _run(["xdg-mime", "query", "default", mime], timeout=5)
        if result is not None and result.returncode == 0 and result.stdout.strip():
            defaults[mime] = result.stdout.strip()
    return defaults


def _cloud_remotes() -> list[dict[str, str]]:
    result = _run(["rclone", "listremotes", "--long"], timeout=10)
    if result is None or result.returncode != 0:
        return []
    remotes: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        remotes.append({
            "name": parts[0].rstrip(":"),
            "type": parts[1] if len(parts) > 1 else "unknown",
        })
    return remotes


def _copy_into_payload(home: Path, payload: Path, rel: str) -> bool:
    source = home / rel
    if not source.exists():
        return False
    target = payload / "files" / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, symlinks=True)
    else:
        shutil.copy2(source, target, follow_symlinks=False)
    return True


def export_setup(destination: str) -> Path:
    home = Path.home()
    dest = Path(destination).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    archive = dest / f"{ARCHIVE_PREFIX}-{timestamp}.tar.gz"

    with tempfile.TemporaryDirectory(prefix="kyth-setup-export-") as tmp:
        payload = Path(tmp) / ARCHIVE_PREFIX
        payload.mkdir(parents=True)
        copied: list[str] = []
        for rel in CONFIG_PATHS:
            if _copy_into_payload(home, payload, rel):
                copied.append(rel)
        for source_name in glob.glob(str(home / ".local/share/applications/kyth-*.desktop")):
            source = Path(source_name)
            rel = str(source.relative_to(home))
            if rel not in copied and _copy_into_payload(home, payload, rel):
                copied.append(rel)

        manifest = {
            "format": "KythOS setup transfer",
            "version": ARCHIVE_VERSION,
            "created": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "hostname": os.uname().nodename,
            "flatpaks": _installed_flatpaks(),
            "default_apps": _default_apps(),
            "cloud_remotes": _cloud_remotes(),
            "copied_paths": sorted(copied),
            "secrets_excluded": [
                "browser profiles and cookies",
                "KWallet contents",
                "rclone OAuth tokens",
                "SMB passwords",
            ],
        }
        (payload / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as tar:
            tar.add(payload, arcname=ARCHIVE_PREFIX, recursive=True)

    archive.chmod(0o600)
    print(f"Setup archive created: {archive}", flush=True)
    print("Passwords, browser sessions, SMB credentials, and cloud OAuth tokens were not included.", flush=True)
    return archive


def _safe_extract(archive: Path, destination: Path) -> Path:
    with tarfile.open(archive, "r:gz") as tar:
        base = destination.resolve()
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            try:
                target.relative_to(base)
            except ValueError as exc:
                raise ValueError(f"Unsafe archive path: {member.name}") from exc
        tar.extractall(destination, filter="data")
    payload = destination / ARCHIVE_PREFIX
    if not payload.is_dir():
        raise ValueError("This is not a KythOS setup archive.")
    return payload


def _load_manifest(payload: Path) -> dict:
    manifest_path = payload / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("The setup archive manifest is missing or invalid.") from exc
    if manifest.get("format") != "KythOS setup transfer":
        raise ValueError("This is not a KythOS setup archive.")
    if manifest.get("version") != ARCHIVE_VERSION:
        raise ValueError(f"Unsupported setup archive version: {manifest.get('version')}")
    copied_paths = manifest.get("copied_paths")
    if not isinstance(copied_paths, list) or not all(
        isinstance(rel, str) and _is_allowed_restore_path(rel) for rel in copied_paths
    ):
        raise ValueError("The setup archive contains an unsupported settings path.")
    return manifest


def _is_allowed_restore_path(rel: str) -> bool:
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts:
        return False
    if rel in CONFIG_PATHS:
        return True
    return (
        len(path.parts) == 4
        and path.parts[:3] == (".local", "share", "applications")
        and path.name.startswith("kyth-")
        and path.suffix == ".desktop"
    )


def archive_summary(archive_name: str) -> str:
    archive = Path(archive_name).expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="kyth-setup-summary-") as tmp:
        payload = _safe_extract(archive, Path(tmp))
        manifest = _load_manifest(payload)
    flatpaks = len(manifest.get("flatpaks") or [])
    settings = len(manifest.get("copied_paths") or [])
    remotes = len(manifest.get("cloud_remotes") or [])
    return (
        f"Created {manifest.get('created', 'unknown')} on {manifest.get('hostname', 'unknown')}\n"
        f"{flatpaks} Flatpak apps, {settings} settings paths, {remotes} cloud definitions\n"
        "Passwords and login tokens are excluded. Network shares and cloud accounts will need reauthentication."
    )


def _restore_files(payload: Path, home: Path, paths: list[str]) -> int:
    restored = 0
    for rel in paths:
        source = payload / "files" / rel
        if not source.exists():
            continue
        target = home / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True, symlinks=True)
        else:
            shutil.copy2(source, target, follow_symlinks=False)
        restored += 1
    return restored


def _restore_defaults(defaults: dict[str, str]) -> int:
    restored = 0
    for mime, desktop in defaults.items():
        result = _run(["xdg-mime", "default", desktop, mime], timeout=10)
        if result is not None and result.returncode == 0:
            restored += 1
    return restored


def _restore_dynamic_lock(home: Path) -> bool:
    config_path = home / ".config/kyth-dynamic-lock.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(config, dict) or config.get("enabled") is not True:
        return False
    result = _run(
        ["systemctl", "--user", "enable", "--now", "kyth-dynamic-lock.service"],
        timeout=30,
    )
    return result is not None and result.returncode == 0


def _restore_flatpaks(apps: list[dict[str, str]]) -> tuple[int, int]:
    if not apps or shutil.which("flatpak") is None:
        return 0, len(apps)
    _run(["flatpak", "remote-add", "--if-not-exists", "flathub", FLATHUB_REPO], timeout=60)
    remotes_result = _run(["flatpak", "remotes", "--columns=name"], timeout=10)
    remotes = set(remotes_result.stdout.split()) if remotes_result else {"flathub"}
    installed = 0
    failed = 0
    for item in apps:
        app_id = str(item.get("id") or "").strip()
        if not app_id:
            continue
        origin = str(item.get("origin") or "flathub").strip()
        if origin not in remotes:
            origin = "flathub"
        print(f"Restoring app: {app_id}", flush=True)
        try:
            proc = subprocess.Popen(
                ["flatpak", "install", "-y", "--or-update", origin, app_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if line:
                    print(line, flush=True)
            code = proc.wait()
        except OSError:
            code = 1
        if code == 0:
            installed += 1
        else:
            failed += 1
    return installed, failed


def restore_setup(archive_name: str) -> None:
    archive = Path(archive_name).expanduser().resolve()
    home = Path.home()
    with tempfile.TemporaryDirectory(prefix="kyth-setup-restore-") as tmp:
        payload = _safe_extract(archive, Path(tmp))
        manifest = _load_manifest(payload)
        restored_paths = _restore_files(payload, home, manifest.get("copied_paths") or [])
        restored_defaults = _restore_defaults(manifest.get("default_apps") or {})
        dynamic_lock_restored = _restore_dynamic_lock(home)
        apps_ok, apps_failed = _restore_flatpaks(manifest.get("flatpaks") or [])

    _run(["kbuildsycoca6", "--noincremental"], timeout=30)
    print(
        f"Setup restored: {restored_paths} settings paths, {restored_defaults} default app associations, "
        f"{apps_ok} apps installed or updated.",
        flush=True,
    )
    if apps_failed:
        print(f"{apps_failed} app install(s) failed; retry them from Discover Apps.", flush=True)
    if manifest.get("cloud_remotes"):
        names = ", ".join(item.get("name", "unknown") for item in manifest["cloud_remotes"])
        print(f"Reconnect cloud account(s) in Cloud Storage: {names}", flush=True)
    if dynamic_lock_restored:
        print("Trusted-device Dynamic Lock restored.", flush=True)
    print("Re-enter network-share passwords from Network Shares, then sign out and back in.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export_parser = sub.add_parser("export", help="Create a setup archive")
    export_parser.add_argument("destination", help="Directory for the archive")
    summary_parser = sub.add_parser("summary", help="Describe a setup archive")
    summary_parser.add_argument("archive")
    restore_parser = sub.add_parser("restore", help="Restore a setup archive")
    restore_parser.add_argument("archive")
    args = parser.parse_args()

    try:
        if args.command == "export":
            export_setup(args.destination)
        elif args.command == "summary":
            print(archive_summary(args.archive))
        else:
            restore_setup(args.archive)
    except (OSError, ValueError, tarfile.TarError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
