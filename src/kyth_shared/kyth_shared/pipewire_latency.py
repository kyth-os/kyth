"""PipeWire low-latency presets — pipewire-latency.toml → real conf drop-ins.

Maps app → quantum (16-2048). A ``default`` (or ``*``) entry sets the session
clock quantum via ``~/.config/pipewire/pipewire.conf.d/``. Named apps keep an
env map under ``~/.config/kyth/pipewire-latency.env`` for launch wrappers
(``PIPEWIRE_LATENCY=quantum/rate``).
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

from .atomic_io import atomic_write_text as _atomic_write_text

DEFAULT_PIPEWIRE_PATH = Path.home() / ".config" / "kyth" / "pipewire-latency.toml"
DEFAULT_ENV_MAP = Path.home() / ".config" / "kyth" / "pipewire-latency.env"
DEFAULT_QUANTUM_DROPIN = Path.home() / ".config" / "pipewire" / "pipewire.conf.d" / "99-kyth-latency.conf"


def pipewire_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "kyth" / "pipewire-latency.toml"
    return DEFAULT_PIPEWIRE_PATH


def _xdg_config() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


def _clamp_quantum(raw: object) -> int | None:
    try:
        qi = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return max(16, min(2048, qi))


def load_pipewire_latency(path: Path | None = None) -> dict[str, int]:
    p = pipewire_config_path(path)
    try:
        with p.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    apps = data.get("apps", {})
    if not isinstance(apps, dict):
        return {}
    out: dict[str, int] = {}
    for app, quantum in apps.items():
        qi = _clamp_quantum(quantum)
        if qi is None:
            continue
        out[str(app)] = qi
    return out


def save_pipewire_latency(apps: dict[str, int], path: Path | None = None) -> Path:
    p = pipewire_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Kyth PipeWire latency — app → quantum, offline\n", "[apps]"]
    for app in sorted(apps):
        lines.append(f'"{app}" = {int(apps[app])}')
    _atomic_write_text(p, "\n".join(lines) + "\n", encoding="utf-8")
    return p


def quantum_for_app(app_id: str, path: Path | None = None) -> int | None:
    return load_pipewire_latency(path).get(app_id)


def pipewire_env_for_app(app_id: str, rate: int = 48000, path: Path | None = None) -> dict[str, str]:
    q = quantum_for_app(app_id, path)
    if q is None:
        return {}
    return {"PIPEWIRE_LATENCY": f"{q}/{rate}"}


def _default_quantum(apps: dict[str, int]) -> int | None:
    for key in ("default", "*"):
        if key in apps:
            return apps[key]
    return None


def apply_pipewire_latency(
    apps: dict[str, int] | None = None,
    *,
    rate: int = 48000,
    quantum_dropin: Path | None = None,
    env_map: Path | None = None,
) -> list[str]:
    """Write PipeWire quantum drop-in + per-app env map. Returns applied notes."""
    if apps is None:
        apps = load_pipewire_latency()
    xdg = _xdg_config()
    dropin = quantum_dropin or (xdg / "pipewire" / "pipewire.conf.d" / "99-kyth-latency.conf")
    env_path = env_map or (xdg / "kyth" / "pipewire-latency.env")
    applied: list[str] = []

    default_q = _default_quantum(apps)
    if default_q is not None:
        content = (
            f"# Kyth PipeWire latency — default quantum {default_q}\n"
            "context.properties = {\n"
            f"  default.clock.quantum = {default_q}\n"
            "}\n"
        )
        dropin.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(dropin, content, encoding="utf-8")
        applied.append(f"quantum={default_q} → {dropin}")
    elif dropin.exists():
        try:
            dropin.unlink()
            applied.append(f"removed {dropin}")
        except OSError:
            pass

    # Per-app env map for launch wrappers (skip default/* keys).
    env_lines = [
        "# Kyth PipeWire per-app latency — source or parse from launch helpers\n",
        f"# rate={rate}\n",
    ]
    named = {k: v for k, v in apps.items() if k not in ("default", "*")}
    for app in sorted(named):
        env_lines.append(f"{app}=PIPEWIRE_LATENCY={named[app]}/{rate}\n")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(env_path, "".join(env_lines), encoding="utf-8")
    applied.append(f"{len(named)} apps → {env_path}")

    try:
        import time

        _atomic_write_text(Path("/run/kyth-pipewire-ttl"), str(int(time.time()) + 30), encoding="utf-8")
    except OSError:
        pass
    return applied
