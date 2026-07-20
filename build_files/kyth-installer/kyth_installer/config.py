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
LOG_FILE     = Path(os.environ.get("KYTH_INSTALLER_LOG", "/tmp/kyth-installer.log"))  # noqa: S108 — created with O_EXCL|O_NOFOLLOW in install.py
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
