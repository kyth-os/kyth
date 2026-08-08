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
# tier -> QLabel objectName in theme_base/_gaming.py (borked/pending reuse the
# shared status-err/status-dim pills instead of their own tier-colored ones).
_PROTONDB_TIER_STYLE = {
    "platinum": "pdb-tier-platinum",
    "gold":     "pdb-tier-gold",
    "silver":   "pdb-tier-silver",
    "bronze":   "pdb-tier-bronze",
    "borked":   "status-err",
    "pending":  "status-dim",
}
