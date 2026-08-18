"""QuickSettings deep — quicksettings.toml brightness + tiles, offline."""
from __future__ import annotations
import logging

import os, tempfile, tomllib
from pathlib import Path
from typing import Any
from kyth_shared.commands import run

logger = logging.getLogger(__name__)


def _atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with open(fd, "w", encoding=encoding) as f:
            f.write(content)
        Path(tmp).replace(path)
    except BaseException:
        try:
            Path(tmp).unlink(missing_ok=True)
        except Exception:
            pass
        raise

DEFAULT_QS_PATH = Path.home() / ".config" / "kyth" / "quicksettings.toml"

def qs_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"quicksettings.toml"
    return DEFAULT_QS_PATH

def load_qs(path: Path | None = None) -> dict[str, Any]:
    p=qs_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"brightness": 80, "tiles": ["wifi","bt","night","plane"]}
    return {"brightness": max(10, min(100, int(data.get("brightness",80)))), "tiles": [str(x) for x in data.get("tiles", ["wifi","bt","night"]) if str(x) in ("wifi","bt","night","plane","battery")] or ["wifi","bt","night"]}

def save_qs(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=qs_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth QuickSettings deep\n"]
    lines.append(f'brightness = {int(cfg.get("brightness",80))}')
    lines.append(f'tiles = {cfg.get("tiles",["wifi","bt","night"])}')
    _atomic_write_text(p, "\n".join(lines)+"\n", encoding="utf-8")
    return p

def apply_qs(cfg: dict[str, Any] | None = None) -> list[str]:
    if cfg is None:
        cfg=load_qs()
    applied=[]
    try:
        # powerdevil brightness via qdbus
        run(["qdbus","org.kde.Solid.PowerManagement","/org/kde/Solid/PowerManagement/Actions/BrightnessControl","setBrightness", str(cfg["brightness"])], capture_output=True, timeout=5)
        applied.append("brightness")
    except Exception:
        logger.debug("handled expected exception", exc_info=True)
        pass
    try:
        import time; _atomic_write_text(Path("/run/kyth-qs-ttl"), str(int(time.time())+30), encoding="utf-8")
    except Exception:
        logger.debug("handled expected exception", exc_info=True)
        pass
    return applied
