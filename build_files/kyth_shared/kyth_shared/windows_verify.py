"""Windows verify — checks migration parity + PWA."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def windows_verify(path: Path | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"bookmarks": "unknown", "drives": "unknown", "files": "unknown", "onedrive": "unknown", "pwa": "unknown"}
    # bookmarks: check for chromium/bookmark file
    for p in (Path.home() / ".config/chromium/Default/Bookmarks", Path.home() / ".mozilla"):
        if p.exists():
            out["bookmarks"] = "found"
            break
    else:
        out["bookmarks"] = "missing"
    # drives: check windows-ports
    if Path("/var/home").exists():
        out["drives"] = "found"
    # files: check files_copy ledger
    if (Path.home() / ".local/share/kyth/files-copy.json").exists():
        out["files"] = "done"
    else:
        out["files"] = "pending"
    # onedrive rclone
    if Path.home().joinpath(".config/rclone/rclone.conf").exists():
        out["onedrive"] = "configured"
    else:
        out["onedrive"] = "missing"
    # PWA check
    pwa = 0
    for d in (Path.home() / ".local/share/applications",):
        if d.exists():
            for f in d.glob("*.desktop"):
                try:
                    t = f.read_text(encoding="utf-8")
                    if "Teams" in t or "Outlook" in t:
                        pwa += 1
                except OSError:
                    pass
    out["pwa"] = f"{pwa} PWA"
    # overall parity
    missing = [k for k, v in out.items() if v in ("missing", "pending", "unknown")]
    out["parity"] = "ok" if not missing else f"missing: {', '.join(missing)}"
    return out
