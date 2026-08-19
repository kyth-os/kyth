"""Polkit presets — polkit.toml rules flatpak/btrfs, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path

DEFAULT_POLKIT_PATH = Path("/etc/kyth/polkit.toml")

def polkit_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1":
        return Path(xdg)/"kyth"/"polkit.toml"
    return DEFAULT_POLKIT_PATH

def load_polkit(path: Path | None = None) -> dict[str, bool]:
    p=polkit_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"flatpak": True, "btrfs": True}
    rules=data.get("rules",{})
    if not isinstance(rules, dict):
        return {"flatpak": True, "btrfs": True}
    return {"flatpak": bool(rules.get("flatpak", True)), "btrfs": bool(rules.get("btrfs", True))}

def save_polkit(rules: dict[str, bool], path: Path | None = None) -> Path:
    p=polkit_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth polkit presets\n","[rules]"]
    for k in sorted(rules):
        lines.append(f'{k} = {str(bool(rules[k])).lower()}')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p

def generate_polkit_rules(rules: dict[str, bool] | None = None) -> str:
    if rules is None:
        rules=load_polkit()
    lines=["// Kyth polkit — generated from polkit.toml, offline"]
    if rules.get("flatpak"):
        lines.append('polkit.addRule(function(a,s){if(a.id.indexOf("org.freedesktop.Flatpak")==0 && s.isInGroup("wheel"))return polkit.Result.YES;});')
    if rules.get("btrfs"):
        lines.append('polkit.addRule(function(a,s){if(a.id=="org.freedesktop.UDisks2.modify-device" && s.isInGroup("wheel"))return polkit.Result.YES;});')
    return "\n".join(lines)+"\n"
