"""PipeWire low-latency quantum presets (N32).

Nobara ships low-latency pipewire; KythOS exposes 128/256 toggle via
tmp→apply without global env.d, rollback on fail. No daemon.
"""
from __future__ import annotations

import os
from pathlib import Path

_PRESETS = {"gaming": "128", "work": "256", "balanced": "256"}


def available_audio_presets() -> list[str]:
    return sorted(_PRESETS.keys())


def apply_pipewire_quantum(preset: str, dry_run: bool = False) -> tuple[bool, str]:
    if preset not in _PRESETS:
        return False, f"unknown preset {preset}"
    if dry_run:
        return True, f"dry-run ok: {preset} quantum {_PRESETS[preset]}"
    try:
        q = _PRESETS[preset]
        # Use pw-metadata or gsettings style: write client quantum via pipewire conf override
        # Transactional: tmp conf, fsync, replace
        xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        conf_dir = Path(xdg) / "pipewire" / "pipewire.conf.d"
        conf_dir.mkdir(parents=True, exist_ok=True)
        target = conf_dir / "99-kyth-quantum.conf"
        tmp = conf_dir / "99-kyth-quantum.conf.tmp"
        content = f'# kyth quantum {preset}\ncontext.properties = {{\n  default.clock.quantum = {q}\n}}\n'
        tmp.write_text(content)
        tmp.chmod(0o644)
        # fsync tmp
        try:
            fd = os.open(str(tmp), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except Exception:
            pass
        tmp.replace(target)
        try:
            fd2 = os.open(str(target.parent), os.O_DIRECTORY)
            try:
                os.fsync(fd2)
            finally:
                os.close(fd2)
        except Exception:
            pass
        return True, f"pipewire quantum {q} ({preset}) applied — restart pipewire"
    except Exception as exc:
        return False, str(exc)
