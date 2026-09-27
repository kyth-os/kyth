"""Plasma drift reconciler — plasma.toml declarative apply via kwriteconfig6.

TOML section names map to KDE config files. Nested tables become config groups:

    [kwinrc]
    key = "value"                 # → --file kwinrc --group General

    [kwinrc.Compositing]
    AllowTearing = "false"        # → --file kwinrc --group Compositing

    [kwinrc.Containments.1.General]
    foo = "bar"                   # → nested --group path
"""
from __future__ import annotations

import logging
import os
import shutil
import tomllib
from pathlib import Path
from typing import Any

from kyth_shared.commands import run

from .atomic_io import atomic_write_text as _atomic_write_text

logger = logging.getLogger(__name__)

DEFAULT_PLASMA_PATH = Path.home() / ".config" / "kyth" / "plasma.toml"


def plasma_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "kyth" / "plasma.toml"
    return DEFAULT_PLASMA_PATH


def load_plasma(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load plasma.toml, flattening nested tables to dotted section keys."""
    p = plasma_config_path(path)
    try:
        with p.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return {}
    return _flatten_sections(data)


def _flatten_sections(data: dict[str, Any], prefix: str = "") -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    scalars: dict[str, Any] = {}
    for key, value in data.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            # Nested table: recurse. If it only holds scalars, those become keys
            # for this section; nested dicts become deeper sections.
            nested_scalars: dict[str, Any] = {}
            for child_key, child_val in value.items():
                if isinstance(child_val, dict):
                    out.update(_flatten_sections({child_key: child_val}, prefix=name))
                else:
                    nested_scalars[str(child_key)] = child_val
            if nested_scalars:
                out[name] = {str(k): str(v) for k, v in nested_scalars.items()}
        else:
            scalars[str(key)] = value
    if scalars and prefix:
        out[prefix] = {str(k): str(v) for k, v in scalars.items()}
    elif scalars and not prefix:
        # Top-level scalars are invalid for kwriteconfig; ignore.
        pass
    return out


def save_plasma(sections: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    p = plasma_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Kyth Plasma drift — declarative, offline\n"]
    for sec in sorted(sections):
        lines.append(f"[{sec}]")
        for key, value in sorted(sections[sec].items()):
            lines.append(f'{key} = "{value}"')
        lines.append("")
    _atomic_write_text(p, "\n".join(lines), encoding="utf-8")
    return p


def _parse_section(sec: str) -> tuple[str, list[str]]:
    """Split ``kwinrc.Compositing`` → (``kwinrc``, [``Compositing``])."""
    parts = [p for p in sec.split(".") if p]
    if not parts:
        raise ValueError(f"empty plasma.toml section: {sec!r}")
    if len(parts) == 1:
        return parts[0], ["General"]
    return parts[0], parts[1:]


def _kwriteconfig_bin() -> str | None:
    return shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5") or shutil.which("kwriteconfig")


def _reconfigure_kwin() -> None:
    for name in ("qdbus6", "qdbus-qt6", "qdbus"):
        if not shutil.which(name):
            continue
        try:
            run(
                [name, "org.kde.KWin", "/KWin", "reconfigure"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            return
        except (OSError, ValueError) as exc:
            logger.debug("plasma reconfigure via %s failed: %s", name, exc, exc_info=True)


def apply_plasma(sections: dict[str, dict[str, Any]] | None = None) -> list[str]:
    if sections is None:
        sections = load_plasma()
    bin_name = _kwriteconfig_bin()
    applied: list[str] = []
    if not bin_name:
        logger.debug("kwriteconfig not found; plasma drift skipped")
        return applied

    for sec, kv in sections.items():
        try:
            conf_file, groups = _parse_section(sec)
        except ValueError:
            logger.debug("skipping invalid plasma section %r", sec)
            continue
        for key, value in kv.items():
            args = [bin_name, "--file", conf_file]
            for group in groups:
                args.extend(["--group", group])
            args.extend(["--key", key, str(value)])
            try:
                res = run(args, capture_output=True, timeout=5, check=False)
                if res.returncode == 0:
                    applied.append(f"{sec}:{key}={value}")
            except (OSError, ValueError) as exc:
                logger.debug("kwriteconfig for %s failed: %s", sec, exc, exc_info=True)

    _reconfigure_kwin()
    try:
        import time

        _atomic_write_text(Path("/run/kyth-plasma-ttl"), str(int(time.time()) + 30), encoding="utf-8")
    except (OSError, ValueError) as exc:
        logger.debug("plasma ttl write failed: %s", exc, exc_info=True)
    return applied
