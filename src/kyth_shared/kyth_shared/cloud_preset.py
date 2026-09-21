"""Cloud Drive parity — cloud.toml rclone + kio, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path

from .atomic_io import atomic_write_text
from .network_preset import _toml_name, _toml_str

DEFAULT_CLOUD_PATH = Path.home() / ".config" / "kyth" / "cloud.toml"

def cloud_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"cloud.toml"
    return DEFAULT_CLOUD_PATH

def load_cloud(path: Path | None = None) -> dict[str, dict[str, str]]:
    p=cloud_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out={}
    for name, e in data.get("drives", {}).items() if isinstance(data.get("drives"), dict) else []:
        if not isinstance(e, dict):
            continue
        out[str(name)]={"remote": str(e.get("remote",""))}
    return out

def save_cloud(drives: dict[str, dict[str, str]], path: Path | None = None) -> Path:
    p=cloud_path(path)
    lines=["# Kyth Cloud Drive — rclone mount + kio network:/\n"]
    for name in sorted(drives):
        # Drive names become TOML section headers the root daemon parses:
        # validate (no quotes/newlines/section injection) and escape remote.
        lines.append(f'[drives."{_toml_name(name)}"]')
        lines.append(f'remote = {_toml_str(drives[name].get("remote"), "")}')
        lines.append("")
    atomic_write_text(p, "\n".join(lines))
    return p
