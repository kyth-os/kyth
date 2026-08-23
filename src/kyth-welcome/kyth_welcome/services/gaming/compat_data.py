"""Load and refresh curated game compatibility data (pure, no Qt)."""
from __future__ import annotations

from datetime import datetime
import json
import os
from dataclasses import dataclass
from pathlib import Path

_COMPAT_BUNDLED_PATH = str(
    Path(__file__).resolve().parents[2] / "compat_games.json"
)
_COMPAT_CACHE_PATH = os.path.expanduser("~/.cache/kyth-compat-games.json")
_COMPAT_REMOTE_URL = (
    "https://raw.githubusercontent.com/kyth-os/kyth/main/"
    "build_files/kyth-welcome/kyth_welcome/compat_games.json"
)
_COMPAT_STALE_DAYS = 45


@dataclass(frozen=True)
class CompatGame:
    name: str
    anticheat: str
    status: str
    note: str
    checked: str
    source: str
    source_url: str


def parse_compat_payload(data: object) -> tuple[str, list[CompatGame]]:
    if not isinstance(data, dict):
        return "", []
    games: list[CompatGame] = []
    for entry in data.get("games", []):
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        status = str(entry.get("status", ""))
        if status not in ("native", "proton", "tweaks", "blocked"):
            continue
        games.append(CompatGame(
            name=str(entry.get("name", "")),
            anticheat=str(entry.get("anticheat", "None")),
            status=status,
            note=str(entry.get("note", "")),
            checked=str(entry.get("checked", "")),
            source=str(entry.get("source", "")),
            source_url=str(entry.get("source_url", "")),
        ))
    return str(data.get("updated", "")), games


_parse_compat_payload = parse_compat_payload


def load_compat_games() -> tuple[str, list[CompatGame]]:
    """Return the newest of the image-bundled data and the runtime cache."""
    best_date, best_games = "", []
    for path in (_COMPAT_BUNDLED_PATH, _COMPAT_CACHE_PATH):
        try:
            with open(path, encoding="utf-8") as fh:
                updated, games = parse_compat_payload(json.load(fh))
        except (OSError, json.JSONDecodeError):
            continue
        if games and updated >= best_date:
            best_date, best_games = updated, games
    return best_date, best_games


_load_compat_games = load_compat_games

# Module-level snapshot; pages may mutate the list in place after a remote refresh.
_COMPAT_DATA_UPDATED, _COMPAT_GAMES = load_compat_games()


def replace_compat_games(updated: str, games: list[CompatGame]) -> None:
    """Update the shared in-memory list (call sites hold the same list object).

    This module is the single owner of _COMPAT_DATA_UPDATED — other modules
    should read it via `compat_data._COMPAT_DATA_UPDATED`, never import the
    name by value (which snapshots it and desyncs from this update).
    """
    global _COMPAT_DATA_UPDATED  # noqa: PLW0603
    _COMPAT_DATA_UPDATED = updated
    _COMPAT_GAMES[:] = games


# Underscore aliases for page import style
_COMPAT_BUNDLED_PATH = _COMPAT_BUNDLED_PATH
_COMPAT_CACHE_PATH = _COMPAT_CACHE_PATH
_COMPAT_REMOTE_URL = _COMPAT_REMOTE_URL
_COMPAT_STALE_DAYS = _COMPAT_STALE_DAYS


@dataclass(frozen=True)
class CompatStats:
    works: int
    blocked: int
    total: int
    oldest_check: str


def calculate_data_age_days(updated_date_str: str, now: datetime | None = None) -> int | None:
    """Calculates data age in days since updated_date_str."""
    if now is None:
        now = datetime.now()
    try:
        return (now - datetime.strptime(updated_date_str, "%Y-%m-%d")).days
    except (ValueError, TypeError):
        return None


def calculate_compat_stats(games: list[CompatGame]) -> CompatStats:
    """Computes summary statistics for game compatibility data."""
    works = sum(1 for game in games if game.status in ("native", "proton", "tweaks"))
    blocked = sum(1 for game in games if game.status == "blocked")
    total = len(games)
    oldest_check = min((game.checked for game in games), default="unknown")
    return CompatStats(
        works=works,
        blocked=blocked,
        total=total,
        oldest_check=oldest_check
    )
