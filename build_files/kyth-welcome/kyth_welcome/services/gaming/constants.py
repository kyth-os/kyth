"""Shared gaming constants."""
from __future__ import annotations

import os
import re

_PROC_MOUNT_ESCAPE_RE = re.compile(r"\\([0-7]{3})")

_STEAM_NON_GAME_PATTERNS = (
    "steamworks common redistributables",
    "steam linux runtime",
    "proton",
    "steamvr",
)

_PROTONDB_CACHE_PATH = os.path.expanduser("~/.cache/kyth-protondb.json")
_PROTONDB_TIER_STYLE = {
    "platinum": ("#102010", "#7ee8a2"),
    "gold":     ("#2b2410", "#d4a843"),
    "silver":   ("#181e2b", "#8cadcf"),
    "bronze":   ("#2b1a10", "#c47c4a"),
    "borked":   ("#3a1010", "#f48771"),
    "pending":  ("#252526", "#858585"),
}
