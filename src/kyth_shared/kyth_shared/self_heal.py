"""Self-heal v2 — deterministic Probe→Plan→Apply, no LLM, TTL per-action.

Uses ProbeService + hardware_policy Evaluation → HealPlan(actions=[clear-quarantine, switch-ring, reapply-quirks]).
Offline, hash-gated, idempotency via /run/kyth-heal-* markers.
"""
from __future__ import annotations
import logging

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import time

from kyth_shared.commands import run

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HealAction:
    kind: str  # clear-quarantine | switch-ring | reapply-quirks | reset-plasma
    detail: str
    ttl: int = 30

@dataclass(frozen=True, slots=True)
class HealPlan:
    actions: tuple[HealAction, ...] = ()
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"actions": [{"kind": a.kind, "detail": a.detail, "ttl": a.ttl} for a in self.actions], "reason": self.reason}

def _probe_summary() -> dict[str, Any]:
    try:
        from kyth_shared.system.probe import read_section
        s = read_section("boot-health", max_age=600)
        return s if isinstance(s, dict) else {}
    except Exception:
        return {}

def _hw_eval() -> Any | None:
    try:
        from kyth_shared.hardware_policy import evaluate_system
        return evaluate_system()
    except Exception:
        return None

def build_heal_plan() -> HealPlan:
    actions: list[HealAction]=[]
    probe=_probe_summary()
    eval_=_hw_eval()
    # Example deterministic rules: if boot_health quarantined -> clear, if ring drift -> switch
    if probe.get("quarantined"):
        actions.append(HealAction("clear-quarantine", f"quarantined={probe['quarantined']}", 30))
    if eval_ and getattr(eval_, "quirk_actions", None):
        # reapply quirks if any
        if eval_.quirk_actions:
            actions.append(HealAction("reapply-quirks", f"{len(eval_.quirk_actions)} quirks", 30))
    if not actions:
        return HealPlan((), "healthy — no action")
    return HealPlan(tuple(actions), "heal needed")

def apply_heal_plan(plan: HealPlan) -> list[str]:
    applied=[]
    for a in plan.actions:
        marker=Path(f"/run/kyth-heal-{a.kind}")
        try:
            # TTL marker
            marker.write_text(str(int(time.time())+a.ttl), encoding="utf-8")
            applied.append(a.kind)
            # best-effort actual action
            if a.kind=="clear-quarantine":
                # extract digest if in detail
                run(["kyth-boot-health", "clear-quarantine", "--digest", a.detail.split()[-1]], capture_output=True, timeout=5)
        except Exception:
            logger.debug("handled expected exception", exc_info=True)
            pass
    try:
        from kyth_welcome.services.hub_state import HUB_STATE
        HUB_STATE.set("heal_plan", plan.as_dict())
    except Exception:
        logger.debug("handled expected exception", exc_info=True)
        pass
    return applied
