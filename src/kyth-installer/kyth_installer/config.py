"""Shared module-level constants for the kyth-installer package.

These mirror the header of the original monolithic kyth-installer script
verbatim (environment-overridable image refs, log location, port, the
per-run session token, and disk/partition sizing constants).
"""

import os
import secrets
import threading
from pathlib import Path
from typing import Optional

SOURCE_IMAGE = os.environ.get("KYTH_SOURCE_IMAGE", "ghcr.io/mrtrick37/kyth:latest")
TARGET_IMAGE = os.environ.get("KYTH_TARGET_IMAGE", SOURCE_IMAGE)
SOURCE_DIGEST = os.environ.get("KYTH_SOURCE_DIGEST", "").strip()
SOURCE_METADATA_FILE = Path(
    os.environ.get("KYTH_SOURCE_METADATA", "/usr/share/kyth/image-source.json")
)
LOG_FILE     = Path(os.environ.get("KYTH_INSTALLER_LOG", "/run/kyth-installer/log"))  # noqa: S108 — under /run 0700, was /tmp sticky
FAILURE_SUMMARY_FILE = Path(
    os.environ.get("KYTH_INSTALLER_FAILURE_SUMMARY", "/run/kyth-installer/failure.json")
)  # noqa: S108 — under /run 0700
TRANSACTION_FILE = Path(
    os.environ.get("KYTH_INSTALLER_TRANSACTION", "/run/kyth-installer/transaction.json")
)
PORT         = 7777
SESSION_TOKEN = secrets.token_urlsafe(32)
_bootstrap_token: Optional[str] = None
_bootstrap_lock = threading.Lock()
SKIP_FETCH_CHECK = os.environ.get("KYTH_INSTALL_SKIP_FETCH_CHECK", "0").lower() in (
    "1", "true", "yes", "on"
)

# Present when running from the live ISO (written by installer/build.sh).
# Absent on a running installed system — used to gate operations that only make sense
# from a live environment (e.g. wiping the running disk).
_IS_LIVE_SESSION = Path("/etc/kyth-installer.env").exists()

EFI_PART_GUID = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
BIOS_BOOT_GUID = "21686148-6449-6e6f-744e-656564454649"
MIN_KYTHOS_GIB = 32
MIN_KYTHOS_BYTES = MIN_KYTHOS_GIB * 1024**3
BIOS_BOOT_BYTES = 1024**2

# ── Staging mount paths (centralized — was 5× literal in install.py) ──────────
STAGING_ALONGSIDE_MOUNT = "/var/tmp/kyth-alongside-target"  # noqa: S108 — _require_no_symlink guards this
STAGING_BTRFS_ROOT = "/var/tmp/kyth-btrfs-root"  # noqa: S108 — _require_no_symlink guards this
STAGING_INSTALL_ROOT = "/var/tmp/kyth-install-root"  # noqa: S108 — _require_no_symlink guards this
STAGING_BTRFS_RESIZE_PREFIX = "kyth-btrfs-resize-"

# ── Canonical filesystem metadata ──────────────────────────────────────
# Single source of truth consumed by partition_ops (mkfs, validation) and
# server (GET /filesystems).  Keep these in sync — no parallel dicts.
_FILESYSTEM = {
    "btrfs":      {"binary": "mkfs.btrfs", "args": ["-f"],     "name": "Btrfs", "root_ok": True,  "efi_ok": False},
    "ext4":       {"binary": "mkfs.ext4",  "args": ["-F"],     "name": "ext4",  "root_ok": False, "efi_ok": False},
    "xfs":        {"binary": "mkfs.xfs",   "args": ["-f"],     "name": "XFS",   "root_ok": False, "efi_ok": False},
    "fat32":      {"binary": "mkfs.fat",   "args": ["-F32"],   "name": "FAT32", "root_ok": False, "efi_ok": True},
    "linux-swap": {"binary": "mkswap",     "args": [],         "name": "Swap",  "root_ok": False, "efi_ok": False},
}

FILESYSTEM_OPTIONS = [
    {"id": k, "name": v["name"], "root_ok": v["root_ok"], "efi_ok": v["efi_ok"]}
    for k, v in _FILESYSTEM.items()
]

def _validate_installer_paths() -> None:
    """Fail closed if TRANSACTION_FILE/LOG_FILE would be world-writable outside /tmp sticky."""
    import stat
    for label, path in (("TRANSACTION_FILE", TRANSACTION_FILE), ("LOG_FILE", LOG_FILE), ("FAILURE_SUMMARY_FILE", FAILURE_SUMMARY_FILE)):
        try:
            p = Path(path)
            # Only validate if file or parent exists
            target = p if p.exists() else p.parent
            if not target.exists():
                continue
            st = target.stat()
            # World-writable check: others have write (0o002) and not sticky-based /tmp
            if bool(st.st_mode & stat.S_IWOTH):
                # Allow world-writable only if parent is /tmp or /run with sticky bit (1777/1773 style)
                # /run/kyth-installer is 0700, safe; /tmp is sticky (0o1000)
                # Outside /tmp sticky, world-writable is unsafe
                parent = target if target.is_dir() else target.parent
                # Check if path is under /tmp
                try:
                    is_tmp = str(parent.resolve()).startswith("/tmp")
                except (OSError, ValueError, RuntimeError):  # noqa: BLE001 -- narrow: path resolve failures
                    is_tmp = str(parent).startswith("/tmp")
                if not is_tmp:
                    # Also check sticky bit
                    parent_mode = parent.stat().st_mode if parent.exists() else 0
                    if not bool(parent_mode & stat.S_ISVTX):
                        raise RuntimeError(f"{label} path {path} is world-writable outside sticky /tmp: {oct(st.st_mode)}")
        except RuntimeError:
            raise
        except (OSError, ValueError, AttributeError):  # noqa: BLE001 -- narrow: stat/permission check failures
            continue

