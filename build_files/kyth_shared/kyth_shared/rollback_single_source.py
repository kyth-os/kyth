"""Rollback single source — UpdateCoordinator owns staged+rollback_available."""
from pathlib import Path
import json

HUB_STATE = Path("/var/lib/kyth/hub_state.json")

def update_coordinator_state() -> dict:
    try:
        if HUB_STATE.is_file():
            return json.loads(HUB_STATE.read_text())
    except Exception:
        pass
    return {"staged": False, "rollback_available": False}

def is_rollback_available() -> bool:
    # single source: read once, derive both
    state = update_coordinator_state()
    return bool(state.get("staged") and state.get("rollback_available"))
