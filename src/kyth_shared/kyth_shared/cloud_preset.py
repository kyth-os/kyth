"""Cloud Drive parity — cloud.toml rclone + kio, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path

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
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth Cloud Drive — rclone mount + kio network:/\n"]
    for name in sorted(drives):
        lines.append(f'[drives."{name}"]')
        lines.append(f'remote = "{drives[name].get("remote","")}"')
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p
