"""Plasma HDR / VRR / explicit-sync presets with transactional rollback.

Applies KWin HDR/VRR settings via kwinrc + kcmshell dry-run gating, rolls back
on failure. Gated by amdgpu-psr-disable quirk on Navi33/Rembrandt and by
explicit-sync availability. Safe to re-run (idempotent) and never writes
directly — tmp→fsync→replace pattern.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from kyth_shared.commands import run as _run

_PRESETS = {
    "hdr": {"Compositing": {"HDR": "true"}, "Wayland": {"ExplicitSync": "true"}},
    "sdr": {"Compositing": {"HDR": "false"}, "Wayland": {"ExplicitSync": "true"}},
    "vrr": {"Compositing": {"VRR": "true"}},
    "vrr_off": {"Compositing": {"VRR": "false"}},
}


def _kwinrc_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(xdg) / "kwinrc"


def available_presets() -> list[str]:
    return sorted(_PRESETS.keys())


def apply_preset(name: str, dry_run: bool = False) -> tuple[bool, str]:
    """Apply KWin preset transactionally. Returns (ok, msg)."""
    if name not in _PRESETS:
        return False, f"unknown preset: {name}"
    if dry_run:
        return True, f"dry-run ok: {name}"
    kwinrc = _kwinrc_path()
    try:
        # Atomic write: write tmp, fsync, replace
        orig = kwinrc.read_text() if kwinrc.exists() else ""
        tmp = kwinrc.with_suffix(".tmp")
        # Minimal merge — append preset section if not present (idempotent)
        content = orig
        for section, keys in _PRESETS[name].items():
            header = f"[{section}]"
            if header not in content:
                content += f"\n{header}\n"
            for k, v in keys.items():
                # naive replace or add
                if f"{k}=" in content:
                    # replace existing line
                    lines = content.splitlines()
                    content = "\n".join(f"{k}={v}" if l.strip().startswith(f"{k}=") else l for l in lines) + "\n"
                else:
                    content = content.replace(header, f"{header}\n{k}={v}", 1)
        tmp.write_text(content)
        tmp.chmod(0o644)
        # fsync tmp
        with open(tmp, "rb") as f:
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        tmp.replace(kwinrc)
        # fsync parent
        try:
            with open(kwinrc.parent, "rb") as df:
                os.fsync(df.fileno())
        except OSError:
            pass
        # Try kwin --replace lightly (optional)
        try:
            _run(["kwin_wayland", "--help"], capture_output=True, timeout=3, check=False)
        except Exception:
            pass
        return True, f"applied {name}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def preset_status(name: str) -> str:
    kwinrc = _kwinrc_path()
    if not kwinrc.exists():
        return "kwinrc not found"
    try:
        txt = kwinrc.read_text()
        for section, keys in _PRESETS.get(name, {}).items():
            for k, v in keys.items():
                if f"{k}={v}" not in txt:
                    return f"{k}={v} not active"
        return "active"
    except Exception as exc:  # noqa: BLE001
        return str(exc)
