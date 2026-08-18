"""Per-app presets — app-presets.toml → cgroup, generalizes gaming.slice."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any
from kyth_shared.cgroup_slice import generate_slice_conf

DEFAULT_APP_PRESETS_PATH = Path.home() / ".config" / "kyth" / "app-presets.toml"

def app_presets_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"app-presets.toml"
    return DEFAULT_APP_PRESETS_PATH

def load_app_presets(path: Path | None = None) -> dict[str, dict[str, Any]]:
    p=app_presets_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return {}
    apps=data.get("apps",{})
    if not isinstance(apps, dict):
        return {}
    out={}
    for app, entry in apps.items():
        if not isinstance(entry, dict):
            continue
        try:
            out[str(app)]={"cpu_weight": int(entry.get("cpu_weight", 100)), "memory_max": str(entry.get("memory_max","80%")), "latency": str(entry.get("latency","balanced"))}
        except (OSError, ValueError, TypeError):
            continue
    return out

def save_app_presets(apps: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    p=app_presets_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth per-app presets → cgroup\n"]
    for app in sorted(apps):
        e=apps[app]
        lines.append(f'[apps."{app}"]')
        lines.append(f'cpu_weight = {e.get("cpu_weight",100)}')
        lines.append(f'memory_max = "{e.get("memory_max","80%")}"')
        lines.append(f'latency = "{e.get("latency","balanced")}"')
        lines.append("")
    import tempfile

    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=f".{p.name}.")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            f.flush()
            os.fsync(f.fileno())
        Path(tmp).replace(p)
        try:
            dfd = os.open(str(p.parent), os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except (OSError, ValueError):
            pass
    except BaseException:
        try:
            Path(tmp).unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
        raise
    return p

def cgroup_for_app(app_id: str, path: Path | None = None) -> dict[str, Any]:
    presets=load_app_presets(path)
    return presets.get(app_id, {"cpu_weight":100, "memory_max":"80%", "latency":"balanced"})

def apply_app_preset(app_id: str, root: Path = Path("/")) -> Path | None:
    cfg=cgroup_for_app(app_id)
    # generate gaming.slice.d drop-in for app
    dest = root / "etc/systemd/system/app.slice.d" if str(root)!="/" else Path("/etc/systemd/system/app.slice.d")
    if str(root)!="/":
        dest=root/"etc/systemd/system/app.slice.d"
    else:
        dest=Path("/etc/systemd/system/app.slice.d")
    # Actually use gaming.slice.d for now (single slice)
    return generate_slice_conf({"cpu_weight": cfg["cpu_weight"], "memory_max": cfg["memory_max"], "io_weight":200, "allowed_cpus":""}, dest / "50-kyth-app.conf")
