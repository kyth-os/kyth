"""Signing preset — signing.toml gpg/cosign, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_SIGNING_PATH = Path.home() / ".config" / "kyth" / "signing.toml"

def signing_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"signing.toml"
    return DEFAULT_SIGNING_PATH

def load_signing(path: Path | None = None) -> dict[str, Any]:
    p=signing_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"gpg_key": "", "cosign_key": "", "gitsign": False}
    return {"gpg_key": str(data.get("gpg_key","")), "cosign_key": str(data.get("cosign_key","")), "gitsign": bool(data.get("gitsign", False))}

def save_signing(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=signing_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth signing preset, offline\n"]
    lines.append(f'gpg_key = "{cfg.get("gpg_key","")}"')
    lines.append(f'cosign_key = "{cfg.get("cosign_key","")}"')
    lines.append(f'gitsign = {str(bool(cfg.get("gitsign", False))).lower()}')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p

def git_config_for_signing(cfg: dict[str, Any] | None = None) -> dict[str,str]:
    if cfg is None:
        cfg=load_signing()
    env={}
    if cfg.get("gpg_key"):
        env["commit.gpgsign"]="true"
        env["user.signingkey"]=cfg["gpg_key"]
    if cfg.get("gitsign"):
        env["gpg.x509.program"]="gitsign"
        env["gpg.format"]="x509"
    return env
