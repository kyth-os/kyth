"""Game compatibility helpers and recommendations."""
from __future__ import annotations

import re


def find_compat_game(compat_games, query: str):
    needle = query.strip().lower()
    if not needle:
        return None
    for game in compat_games:
        if game.name.lower() == needle:
            return game
    for game in compat_games:
        if needle in game.name.lower() or game.name.lower() in needle:
            return game
    return None

def recommended_launcher_for_game(game) -> str:
    name = game.name.lower()
    if "overwatch" in name:
        return "Lutris with Battle.net via umu-run"
    if any(token in name for token in ("red dead", "gta")):
        return "Steam when owned there; otherwise Lutris/Heroic plus the Rockstar launcher"
    if game.status == "blocked":
        return "None on Linux until the publisher enables support"
    if game.status == "native":
        return "Steam native Linux build"
    return "Steam with Proton Experimental first, then Proton-CachyOS"

def recommended_profile_for_game(game) -> str:
    if game.status == "blocked":
        return "Do not try bypass launch options; use other system or wait for publisher support."
    if any(token in game.name.lower() for token in ("cyberpunk", "red dead", "hogwarts")):
        return "kyth-gamescope quality -- %command%"
    if game.anticheat in ("EAC", "BattlEye", "VAC", "Warden"):
        return "game-performance --profile gaming -- %command%"
    return "kyth-gamescope quality -- %command%"

def blocked_compat_lookup(compat_games) -> tuple[dict[str, str], set[str]]:
    """Blocked Steam appids (from compat source URLs) and lowercase names."""
    appids: dict[str, str] = {}
    names: set[str] = set()
    for game in compat_games:
        if game.status != "blocked":
            continue
        names.add(game.name.lower())
        m = re.search(r"protondb\.com/app/(\d+)", game.source_url)
        if m:
            appids[m.group(1)] = game.name
    return appids, names


