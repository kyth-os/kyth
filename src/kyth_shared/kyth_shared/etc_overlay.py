"""Immutable /etc merge — etc-overlay.toml offline staged config.

Like preset.toml, declarative overlay under /usr/etc → /etc via tmpfiles, atomic apply + rollback marker.
"""
from __future__ import annotations
import json
import logging

import os
import tomllib
from pathlib import Path

from .atomic_io import atomic_write_text

logger = logging.getLogger(__name__)

DEFAULT_OVERLAY_PATH = Path("/etc/kyth/etc-overlay.toml")


def overlay_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "etc-overlay.toml"
    return DEFAULT_OVERLAY_PATH


def load_overlay(path: Path | None = None) -> dict[str, str]:
    cfg_path = overlay_path(path)
    try:
        with cfg_path.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    files = data.get("files", {})
    if not isinstance(files, dict):
        return {}
    out: dict[str, str] = {}
    for dest, content in files.items():
        if isinstance(content, str):
            out[str(dest)] = content
    return out


def save_overlay(files: dict[str, str], path: Path | None = None) -> Path:
    cfg_path = overlay_path(path)
    lines = ["# Kyth etc overlay — offline staged /etc merge\n", "[files]"]
    for dest in sorted(files):
        dest_key = str(dest)
        if not dest_key or any(c in dest_key for c in "\n\r"):
            continue
        lines.append(f"{json.dumps(dest_key, ensure_ascii=False)} = {json.dumps(str(files[dest]), ensure_ascii=False)}")
    atomic_write_text(cfg_path, "\n".join(lines) + "\n", mode=0o600)
    return cfg_path


def apply_overlay(files: dict[str, str] | None = None, root: Path = Path("/")) -> list[Path]:
    if files is None:
        files = load_overlay()
    written: list[Path] = []
    for dest, content in files.items():
        # prevent traversal
        p = (root / dest.lstrip("/")).resolve()
        # ensure under root
        try:
            p.relative_to(root.resolve())
        except ValueError:
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(p)
        written.append(p)
    # TTL marker like ai_perf
    try:
        import time
        Path("/run/kyth-etc-overlay-ttl").write_text(str(int(time.time()) + 30), encoding="utf-8")
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass
    return written
