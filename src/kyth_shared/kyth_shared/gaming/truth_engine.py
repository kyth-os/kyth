"""Truth Engine — map a user's library to compat data (pure)."""
from __future__ import annotations

import re
from pathlib import Path

from kyth_shared.gaming.compat_data import CompatGame  # type: ignore

# Normalize names for matching: lowercase, strip punctuation, collapse spaces
def _normalize(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def build_compat_index(games: list[CompatGame]) -> dict[str, CompatGame]:
    """Normalized name -> CompatGame for O(1) lookup."""
    idx: dict[str, CompatGame] = {}
    for g in games:
        key = _normalize(g.name)
        if key and key not in idx:
            idx[key] = g
        # Also index without year suffix e.g. "Overwatch 2" vs "Overwatch"
        # kept minimal — exact match only for honesty
    return idx


def scan_steam_manifests(library_paths: list[str] | None = None) -> list[str]:
    """Best-effort: scan local Steam manifests for installed game names.

    If library_paths provided, scans those; otherwise checks ~/.steam/steam/steamapps.
    Returns list of app names (may be empty if not installed).
    """
    names: list[str] = []
    candidates: list[Path] = []
    if library_paths:
        for p in library_paths:
            candidates.append(Path(p) / "steamapps")
    else:
        home = Path.home()
        candidates = [
            home / ".steam" / "steam" / "steamapps",
            home / ".steam" / "steamapps",
            home / ".local" / "share" / "Steam" / "steamapps",
        ]
    for base in candidates:
        if not base.is_dir():
            continue
        for mf in base.glob("appmanifest_*.acf"):
            try:
                text = mf.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r'"name"\s+"([^"]+)"', text)
                if m:
                    names.append(m.group(1).strip())
            except OSError:
                continue
    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        k = _normalize(n)
        if k not in seen:
            seen.add(k)
            out.append(n)
    return out


def classify_library(user_games: list[str], compat_games: list[CompatGame]) -> dict:
    """Classify user's game names against compat data.

    Returns dict with buckets: native/proton/tweaks/blocked/unknown counts and per-game details.
    Unknown = not in Kyth list — suggest ProtonDB check.
    """
    idx = build_compat_index(compat_games)
    buckets: dict[str, list[dict]] = {"native": [], "proton": [], "tweaks": [], "blocked": [], "unknown": []}
    for name in user_games:
        key = _normalize(name)
        g = idx.get(key)
        if g is None:
            buckets["unknown"].append({"name": name, "status": "unknown", "note": "Not in Kyth list — check ProtonDB."})
        else:
            buckets[g.status].append({"name": g.name, "status": g.status, "anticheat": g.anticheat, "note": g.note, "checked": g.checked})
    total = len(user_games)
    works = len(buckets["native"]) + len(buckets["proton"])
    blocked = len(buckets["blocked"])
    return {
        "total": total,
        "works": works,
        "blocked": blocked,
        "buckets": buckets,
        "summary": f"{works} of {total} should work; {blocked} blocked by vendor anti-cheat." if total else "No games to check — install Steam or paste your library below.",
    }
