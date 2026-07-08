"""Shared module-level constants for the kyth-installer package.

These mirror the header of the original monolithic kyth-installer script
verbatim (environment-overridable image refs, log location, port, the
per-run session token, and disk/partition sizing constants).
"""

import os
import secrets
from pathlib import Path
from typing import Optional

SOURCE_IMAGE = os.environ.get("KYTH_SOURCE_IMAGE", "ghcr.io/mrtrick37/kyth:latest")
TARGET_IMAGE = os.environ.get("KYTH_TARGET_IMAGE", SOURCE_IMAGE)
LOG_FILE     = Path(os.environ.get("KYTH_INSTALLER_LOG", "/tmp/kyth-installer.log"))
PORT         = 7777
SESSION_TOKEN = secrets.token_urlsafe(32)
_bootstrap_token: Optional[str] = None
SKIP_FETCH_CHECK = os.environ.get("KYTH_INSTALL_SKIP_FETCH_CHECK", "0").lower() in (
    "1", "true", "yes", "on"
)

# Present when running from the live ISO (written by installer/build.sh).
# Absent on a running installed system — used to gate operations that only make sense
# from a live environment (e.g. wiping the running disk).
_IS_LIVE_SESSION = Path("/etc/kyth-installer.env").exists()

EFI_PART_GUID = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
MIN_KYTHOS_GIB = 32
MIN_KYTHOS_BYTES = MIN_KYTHOS_GIB * 1024**3
