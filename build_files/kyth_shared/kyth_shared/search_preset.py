"""Search parity — search.toml baloo + krunner + kickoff weights, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any
from kyth_shared.commands import run

DEFAULT_SEARCH_PATH = Path.home() / ".config" / "kyth" / "search.toml"

def search_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"search.toml"
    return DEFAULT_SEARCH_PATH

def load_search(path: Path | None = None) -> dict[str, Any]:
    p=search_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"baloo": True, "recent": 20, "apps_weight": 3, "files_weight": 1}
    return {"baloo": bool(data.get("baloo", True)), "recent": max(5, min(100, int(data.get("recent",20)))), "apps_weight": max(1, min(5, int(data.get("apps_weight",3)))), "files_weight": max(1, min(5, int(data.get("files_weight",1))))}

def save_search(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=search_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth search parity — baloo + kickoff weights\n"]
    lines.append(f'baloo = {str(bool(cfg.get("baloo",True))).lower()}')
    lines.append(f'recent = {int(cfg.get("recent",20))}')
    lines.append(f'apps_weight = {int(cfg.get("apps_weight",3))}')
    lines.append(f'files_weight = {int(cfg.get("files_weight",1))}')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p

def apply_search(cfg: dict[str, Any] | None = None) -> list[str]:
    if cfg is None:
        cfg=load_search()
    applied=[]
    try:
        run(["kwriteconfig5","--file","baloofilerc","--group","General","--key","Indexing-Enabled", str(cfg["baloo"]).lower()], capture_output=True, timeout=5)
        applied.append("baloofilerc")
    except Exception:
        pass
    try:
        run(["kwriteconfig5","--file","krunnerrc","--group","General","--key","RecentFiles", str(cfg["recent"])], capture_output=True, timeout=5)
    except Exception:
        pass
    return applied
