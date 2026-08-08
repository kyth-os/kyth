"""Per-game gaming config — HDR + latency profile per Steam app.

Persists to ``~/.config/kyth/gaming-per-game.toml`` like ``preset.toml``.
Pure, no Qt, testable. Keeps base lean (no global LD_PRELOAD) — per-game
env toggling is the progressive split vs Bazzite's global layer.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_PER_GAME_PATH = Path.home() / ".config" / "kyth" / "gaming-per-game.toml"
# For tests that need an isolated path
TEST_MARKER = "test-appid"


def per_game_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "kyth" / "gaming-per-game.toml"
    return DEFAULT_PER_GAME_PATH


def load_per_game_config(path: Path | None = None) -> dict[str, dict[str, Any]]:
    cfg_path = per_game_config_path(path)
    try:
        data = tomllib.load(cfg_path.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    games = data.get("games", {})
    if not isinstance(games, dict):
        return {}
    # Only keep well-formed entries
    out: dict[str, dict[str, Any]] = {}
    for appid, entry in games.items():
        if not isinstance(entry, dict):
            continue
        profile = str(entry.get("profile", "balanced"))
        hdr = bool(entry.get("hdr", False))
        if profile not in {"low-latency", "balanced", "battery", "quality", "hdr", "sharp", "latency"}:
            profile = "balanced"
        out[str(appid)] = {"profile": profile, "hdr": hdr}
    return out


def save_per_game_config(
    games: dict[str, dict[str, Any]],
    path: Path | None = None,
) -> Path:
    cfg_path = per_game_config_path(path)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Kyth per-game gaming config — HDR + latency profile\n"]
    for appid in sorted(games):
        entry = games[appid]
        profile = str(entry.get("profile", "balanced"))
        hdr = bool(entry.get("hdr", False))
        lines.append(f'[games."{appid}"]')
        lines.append(f'profile = "{profile}"')
        lines.append(f'hdr = {str(hdr).lower()}')
        lines.append("")
    cfg_path.write_text("\n".join(lines), encoding="utf-8")
    return cfg_path


def get_profile_for_appid(
    appid: str,
    path: Path | None = None,
) -> dict[str, Any]:
    cfg = load_per_game_config(path)
    return cfg.get(str(appid), {"profile": "balanced", "hdr": False})


def set_profile_for_appid(
    appid: str,
    profile: str = "balanced",
    hdr: bool = False,
    path: Path | None = None,
) -> Path:
    cfg = load_per_game_config(path)
    cfg[str(appid)] = {"profile": profile, "hdr": hdr}
    return save_per_game_config(cfg, path)


def gaming_launch_env_for_appid(
    appid: str,
    path: Path | None = None,
) -> dict[str, str]:
    """Env dict for a specific Steam app (latency profile + optional HDR).

    HDR is surfaced as ``KYTH_HDR=1`` so ``kyth-gamescope`` can add
    ``--hdr-enabled`` without baking it globally.
    """
    entry = get_profile_for_appid(appid, path)
    profile = str(entry.get("profile", "balanced"))
    hdr = bool(entry.get("hdr", False))
    # Map UI goals to latency profiles
    profile_map = {
        "quality": "balanced",
        "hdr": "balanced",
        "sharp": "balanced",
        "latency": "low-latency",
        "troubleshoot": "battery",
    }
    latency_profile = profile_map.get(profile, profile if profile in {"low-latency", "balanced", "battery"} else "balanced")
    try:
        from kyth_welcome.services.gaming.health import latency_env_for_profile

        env = dict(latency_env_for_profile(latency_profile))
    except Exception:
        try:
            from kyth_shared.health import latency_env_for_profile as _fallback

            env = dict(_fallback(latency_profile))
        except Exception:
            env = {}
    if hdr:
        env["KYTH_HDR"] = "1"
    return env
