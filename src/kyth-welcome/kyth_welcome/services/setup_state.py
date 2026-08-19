"""Resumable first-boot setup state.

Replaces the old single ``~/.config/kyth-welcome-done`` boolean sentinel
(core_base._WIZARD_SENTINEL) with per-step status, so closing the wizard
early no longer silently discards what was and wasn't done. Pure stdlib —
importable from non-Qt code the same way the rest of ``services/`` is.
"""
from __future__ import annotations

import os

from .config import load_json_config, save_json_config

STATUS_DONE = "done"
STATUS_SKIPPED = "skipped"
STATUS_PENDING = "pending"
_VALID_STATUSES = (STATUS_DONE, STATUS_SKIPPED, STATUS_PENDING)

# Steps a user can meaningfully skip and resume later. "welcome" (profile
# pick) isn't here — it's instant and not worth surfacing as outstanding work.
STEP_KEYS = ("machine", "apps", "gaming")

STEP_LABELS = {
    "machine": "Your machine check",
    "apps": "Get apps",
    "gaming": "Gaming setup",
}

# Where "Resume" on the Home page's setup card should send the user.
STEP_RESUME_PAGE = {
    "machine": "Hardware",
    "apps": "App Store",
    "gaming": "Gaming",
}

_STATE_PATH = os.path.expanduser("~/.config/kyth-welcome/setup-state.json")
_LEGACY_SENTINEL = os.path.expanduser("~/.config/kyth-welcome-done")


def _default_state() -> dict[str, str]:
    return dict.fromkeys(STEP_KEYS, STATUS_PENDING)


def load_state() -> dict[str, str]:
    if not os.path.exists(_STATE_PATH):
        if os.path.exists(_LEGACY_SENTINEL):
            # Pre-existing install that already finished the old wizard —
            # don't resurface a "finish setup" card for steps it never tracked.
            state = dict.fromkeys(STEP_KEYS, STATUS_DONE)
            save_state(state)
            return state
        return _default_state()

    raw = load_json_config(_STATE_PATH, default={})
    state = _default_state()
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in STEP_KEYS and value in _VALID_STATUSES:
                state[key] = value
    return state


def save_state(state: dict[str, str]) -> None:
    save_json_config(_STATE_PATH, state)


def mark_step(key: str, status: str) -> None:
    if key not in STEP_KEYS or status not in _VALID_STATUSES:
        return
    state = load_state()
    state[key] = status
    save_state(state)


def is_first_run() -> bool:
    return not os.path.exists(_STATE_PATH) and not os.path.exists(_LEGACY_SENTINEL)


def relevant_steps(profile: str) -> list[str]:
    return [k for k in STEP_KEYS if k != "gaming" or profile == "gaming"]


def incomplete_steps(profile: str) -> list[tuple[str, str]]:
    """[(step_key, status)] for steps that aren't done, in step order."""
    state = load_state()
    return [
        (key, state.get(key, STATUS_PENDING))
        for key in relevant_steps(profile)
        if state.get(key, STATUS_PENDING) != STATUS_DONE
    ]


def mark_wizard_closed(profile: str) -> None:
    """Call when the wizard window closes for any reason. Any relevant step
    that was never explicitly marked done/skipped is recorded as skipped —
    tracked and resumable from Home, not silently discarded."""
    state = load_state()
    changed = False
    for key in relevant_steps(profile):
        if state.get(key, STATUS_PENDING) == STATUS_PENDING:
            state[key] = STATUS_SKIPPED
            changed = True
    if changed:
        save_state(state)
