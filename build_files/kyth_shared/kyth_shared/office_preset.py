"""Office assoc — office.toml suite libre/onlyoffice, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path

DEFAULT_OFFICE_PATH = Path.home() / ".config" / "kyth" / "office.toml"

def office_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"office.toml"
    return DEFAULT_OFFICE_PATH

def load_office(path: Path | None = None) -> dict[str, str]:
    p=office_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"suite": "libre"}
    suite=str(data.get("suite","libre"))
    if suite not in ("libre","onlyoffice"):
        suite="libre"
    return {"suite": suite}

def save_office(cfg: dict[str, str], path: Path | None = None) -> Path:
    p=office_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth Office assoc\n"]
    lines.append(f'suite = "{cfg.get("suite","libre")}"')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p

def mime_for_suite(suite: str) -> dict[str,str]:
    if suite=="onlyoffice":
        return {"application/vnd.openxmlformats-officedocument.wordprocessingml.document": "onlyoffice-desktopeditors.desktop",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "onlyoffice-desktopeditors.desktop"}
    return {"application/vnd.openxmlformats-officedocument.wordprocessingml.document": "libreoffice-writer.desktop"}
