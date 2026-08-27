#!/usr/bin/env python3
"""Bridge for the Tauri shell's `guardian_snapshot` command.

Deliberately reads only Guardian's own on-disk state
(kyth_shared.guardian's load_state() + pending_recommendations(), both
pure computation over a JSON file — no subprocess calls) — NOT
guardian.inspect()/collect_symptoms(), which runs a real probe sweep
(audio/network/bluetooth/portal/plasma/flatpak/storage/... a dozen-plus
subprocess calls) and has no place running on every dashboard load. Same
"read the cache, don't trigger fresh work" posture as probe_bridge.py.

`history` entries are already PII-redacted at write time (see
kyth_shared.guardian's redact() calls at each site that appends to
state["history"]) — nothing here needs to re-redact before printing.
"""
from __future__ import annotations

import json

from kyth_shared.guardian import RECIPES, load_state, pending_recommendations


def _title_for(recipe_id: str | None) -> str:
    if recipe_id and recipe_id in RECIPES:
        return RECIPES[recipe_id].title
    return recipe_id or "Guardian"


def main() -> int:
    state = load_state()
    pending = pending_recommendations(state)
    history = state.get("history", [])

    # Most recent first, capped — this feeds a small activity list, not a
    # full audit log.
    recent = sorted(
        (item for item in history if isinstance(item, dict) and "timestamp" in item),
        key=lambda item: item["timestamp"],
        reverse=True,
    )[:8]

    payload = {
        "pending_count": len(pending),
        "history": [
            {
                "timestamp": item["timestamp"],
                "title": _title_for(item.get("recipe_id")),
                "detail": item.get("detail", ""),
                "action": item.get("action", "executed"),
                "verified": item.get("verified"),
            }
            for item in recent
        ],
    }
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
