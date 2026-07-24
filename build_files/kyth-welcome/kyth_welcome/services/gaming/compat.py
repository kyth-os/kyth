"""Game compatibility helpers and recommendations."""
from __future__ import annotations

import re
from dataclasses import dataclass


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

_STATUS_STYLE = {"native": "ok", "proton": "ok", "tweaks": "warn", "blocked": "err"}
_STATUS_LABEL = {"native": "Native", "proton": "Works", "tweaks": "Tweaks", "blocked": "Blocked"}
_READINESS_STATUS_LABEL = {
    "native": "Native Linux", "proton": "Works via Proton",
    "tweaks": "Works with tweaks", "blocked": "Blocked by publisher/anti-cheat",
}


@dataclass(frozen=True)
class GameRowStatusView:
    """What page_gaming_library.py's My Games row should show for one game
    — no Qt, so the compat-status decision is testable without a display."""
    status: str
    status_text: str
    summary: str
    profile: str


def game_row_status_view(compat) -> GameRowStatusView:
    """`compat` is a CompatGame or None (not in the curated list)."""
    if compat is None:
        return GameRowStatusView(
            status="dim", status_text="Unknown",
            summary="Not in curated list. ProtonDB rating shown when available.",
            profile="kyth-gamescope quality -- %command%",
        )
    return GameRowStatusView(
        status=_STATUS_STYLE.get(compat.status, "err"),
        status_text=_STATUS_LABEL.get(compat.status, compat.status),
        summary=f"{compat.note} Checked {compat.checked} via {compat.source}.",
        profile=recommended_profile_for_game(compat),
    )


def library_summary_text(games: list[dict], compat_games) -> str:
    matched = sum(1 for game in games if find_compat_game(compat_games, game.get("name", "")))
    by_launcher: dict[str, int] = {}
    for game in games:
        launcher = game.get("launcher", "Unknown")
        by_launcher[launcher] = by_launcher.get(launcher, 0) + 1
    launcher_summary = ", ".join(f"{name}: {count}" for name, count in sorted(by_launcher.items()))
    return f"Detected {len(games)} installed item(s); {matched} matched KythOS compatibility data. {launcher_summary}"


def readiness_result_text(game) -> str:
    """`game` is a CompatGame already found by find_compat_game — the
    "not found" branch stays in the page since it needs a URL-encoded
    ProtonDB search link built from the raw query string."""
    status_label = _READINESS_STATUS_LABEL.get(game.status, game.status)
    save_note = (
        "Back up saves with Ludusavi before migrating or modding."
        if game.status != "blocked"
        else "Do not migrate saves until the game has a supported Linux path."
    )
    mod_note = (
        "Use the Modding guide before applying other system mod managers."
        if game.status != "blocked"
        else "Modding is irrelevant while the game is blocked."
    )
    return (
        f"{game.name}: {status_label}\n"
        f"Anti-cheat/middleware: {game.anticheat}\n"
        f"Launcher: {recommended_launcher_for_game(game)}\n"
        f"Runner/profile: {recommended_profile_for_game(game)}\n"
        f"Saves: {save_note}\n"
        f"Mods: {mod_note}\n"
        f"Checked: {game.checked} via {game.source}\n"
        f"{game.note}"
    )


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


