"""Local AI control plane — offline, pure, no Qt.

Takes the unified probe snapshot + boot health + hardware Evaluation and
returns a deterministic repair/latency plan that the Hub can act on without
cloud. Ollama (via AiDev distrobox) is used only as an optional enhancer;
the core logic is rule-based so it works offline and is unit-testable.

Design mirrors `hardware_policy.evaluate_system()` — data in, actions out.
"""
from __future__ import annotations

import json
import os
from .commands import run as _run_cmd
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class AiAction:
    id: str
    label: str
    command: tuple[str, ...]
    reason: str
    priority: int = 100


@dataclass(frozen=True, slots=True)
class AiPlan:
    actions: tuple[AiAction, ...]
    summary: str
    offline: bool = True
    model: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "actions": [asdict(a) for a in self.actions],
            "summary": self.summary,
            "offline": self.offline,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AiPlan":
        raw_actions = data.get("actions", [])
        actions: list[AiAction] = []
        for item in raw_actions if isinstance(raw_actions, list) else []:
            if not isinstance(item, dict):
                continue
            try:
                actions.append(AiAction(
                    id=str(item["id"]),
                    label=str(item["label"]),
                    command=tuple(item.get("command", ())),
                    reason=str(item.get("reason", "")),
                    priority=int(item.get("priority", 100)),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return cls(
            actions=tuple(sorted(actions, key=lambda a: a.priority)),
            summary=str(data.get("summary", "")),
            offline=bool(data.get("offline", True)),
            model=data.get("model"),
        )


def _probe_has_error(snapshot: dict[str, Any], key: str) -> bool:
    val = snapshot.get(key)
    if isinstance(val, dict):
        return bool(val.get("error")) or val.get("status") == "failed"
    return False


def _should_offer_rollback(
    snapshot: dict[str, Any],
    boot_failures: int,
    status: str,
) -> bool:
    staged = False
    rollback = False
    try:
        from kyth_shared.system.bootc import has_rollback_deployment, has_staged_update

        staged = bool(has_staged_update())
        rollback = bool(has_rollback_deployment())
    except Exception:
        pass
    # Fallback/OR with snapshot so offline plan works without live probe cache
    if not staged:
        staged = snapshot.get("bootc-status-data", {}).get("status", {}).get("staged") is not None
    if not rollback:
        rollback = snapshot.get("bootc-status-data", {}).get("status", {}).get("rollback") is not None
    # Two failed boots after a staged image is the self-healing signal.
    if staged and rollback and boot_failures >= 2:
        return True
    if status in ("quarantined", "unhealthy") and rollback:
        return True
    return False


def _latency_actions(evaluation: Any) -> list[AiAction]:
    caps = set(getattr(evaluation, "capabilities", ()) or ())
    actions: list[AiAction] = []
    if "gaming.lowlatency" in caps or "gpu.nvidia" in caps or "gpu.amd" in caps:
        try:
            from kyth_shared.gaming import LATENCY_PROFILES  # type: ignore

            # Deterministic per-game env is handled by health.latency_env_for_profile;
            # here we surface the Hub-level toggle.
            if "low-latency" in LATENCY_PROFILES:
                actions.append(AiAction(
                    id="enable-low-latency",
                    label="Enable low-latency gaming",
                    command=("ujust", "gaming-low-latency", "on"),
                    reason="System supports low-latency Vulkan layer (gaming.lowlatency / GPU detected).",
                    priority=40,
                ))
        except Exception:
            pass
    return actions


def _quirk_expiry_actions(evaluation: Any) -> list[AiAction]:
    actions: list[AiAction] = []
    for quirk in getattr(evaluation, "quirks", ()) or ():
        if not isinstance(quirk, dict):
            continue
        if quirk.get("expires_on"):
            actions.append(AiAction(
                id=f"review-quirk-{quirk.get('id','unknown')}",
                label=f"Review quirk {quirk.get('id','')}",
                command=("kyth-hardware-policy", "validate", "--fail-expired"),
                reason=f"Quirk {quirk.get('id')} expires {quirk.get('expires_on')}: {quirk.get('reason','')}",
                priority=70,
            ))
            break  # one is enough to surface the bucket
    return actions


def generate_plan(
    snapshot: dict[str, Any] | None = None,
    boot_state: Any | None = None,
    evaluation: Any | None = None,
) -> AiPlan:
    """Deterministic, offline plan from snapshot + boot health + hardware eval.

    All inputs are optional so the Hub can call this even when a probe is
    still pending. Returns at least one action or a no-op summary.
    """
    snapshot = snapshot or {}
    actions: list[AiAction] = []

    # -- Boot / staged / rollback heuristics -----------------------------
    boot_failures = 0
    boot_status = "unknown"
    quarantine_len = 0
    if boot_state is not None:
        boot_failures = int(getattr(boot_state, "failures", 0) or 0)
        boot_status = str(getattr(boot_state, "status", "unknown") or "unknown")
        q = getattr(boot_state, "quarantined", {}) or {}
        quarantine_len = len(q) if isinstance(q, dict) else 0

    if _should_offer_rollback(snapshot, boot_failures, boot_status):
        actions.append(AiAction(
            id="rollback",
            label="Roll back to previous OS",
            command=("pkexec", "bootc", "rollback"),
            reason=f"Staged image has {boot_failures} failed boots (status={boot_status}); rollback is one reboot away.",
            priority=10,
        ))
        if quarantine_len:
            digest = next(iter(getattr(boot_state, "quarantined", {}).keys()), "")
            cmd = ("pkexec", "kyth-boot-health", "clear-quarantine", "--digest", digest) if digest else ("pkexec", "kyth-boot-health", "clear-quarantine")
            actions.append(AiAction(
                id="clear-quarantine",
                label="Clear quarantine for staged image",
                command=cmd,  # type: ignore[arg-type]
                reason="Quarantined digest is blocking retry; clear to re-stage.",
                priority=11,
            ))

    # -- Flatpak / app health ------------------------------------------
    flatpak_updates = snapshot.get("flatpak-updates")
    if isinstance(flatpak_updates, int) and flatpak_updates > 0:
        actions.append(AiAction(
            id="update-flatpaks",
            label=f"Update {flatpak_updates} Flatpak(s)",
            command=("flatpak", "update", "-y"),
            reason=f"{flatpak_updates} Flatpak update(s) pending.",
            priority=30,
        ))

    # -- Controller / display / nvidia probes ---------------------------
    if snapshot.get("nvidia-detect") is True:
        actions.append(AiAction(
            id="nvidia-status",
            label="Check NVIDIA driver status",
            command=("/usr/bin/kyth-nvidia-status",),
            reason="NVIDIA GPU detected; verify driver build.",
            priority=50,
        ))
    if snapshot.get("controllers-detect"):
        # controllers-detect returns list/dict; surface only if non-empty
        val = snapshot.get("controllers-detect")
        has = bool(val) if not isinstance(val, dict) else bool(val.get("devices") or val)
        if has:
            actions.append(AiAction(
                id="controller-check",
                label="Verify controllers",
                command=("/usr/bin/kyth-controller-check",),
                reason="Controller hardware detected; verify readiness.",
                priority=60,
            ))

    # -- Hardware evaluation derived actions -----------------------------
    if evaluation is not None:
        actions.extend(_latency_actions(evaluation))
        actions.extend(_quirk_expiry_actions(evaluation))
        warnings = getattr(evaluation, "warnings", ()) or ()
        if warnings:
            actions.append(AiAction(
                id="hardware-policy-warnings",
                label="Review hardware policy warnings",
                command=("kyth-hardware-policy", "status"),
                reason="; ".join(str(w) for w in warnings[:2]),
                priority=80,
            ))

    # -- Diagnostics log hints -----------------------------------------
    # If probe snapshot missing entirely, suggest collecting it.
    if not snapshot:
        actions.append(AiAction(
            id="refresh-probe",
            label="Refresh system probe cache",
            command=("/usr/libexec/kyth-probe",),
            reason="Probe snapshot empty; refresh cache to diagnose.",
            priority=90,
        ))

    if not actions:
        return AiPlan(
            actions=(),
            summary="System looks healthy. No repair actions needed.",
            offline=True,
        )

    actions.sort(key=lambda a: a.priority)
    summary = f"{len(actions)} action(s): " + ", ".join(a.label for a in actions[:3])
    if len(actions) > 3:
        summary += f" +{len(actions)-3} more"
    return AiPlan(actions=tuple(actions), summary=summary, offline=True)


def try_ollama_enhance(plan: AiPlan, prompt: str | None = None) -> AiPlan:
    """Optionally enhance plan via local Ollama. Never fails; offline fallback."""
    model = os.environ.get("KYTH_AI_MODEL", "qwen2.5-coder")
    # Only attempt if ollama binary exists and model dir has content or box exists
    try:
        if not any(
            Path(p).exists() for p in ("/usr/bin/ollama", "/usr/local/bin/ollama")
        ):
            # Check distrobox ollama
            res = _run_cmd(
                ["distrobox", "list", "--no-color"],
                capture_output=True, text=True, timeout=3,
            )
            if "kyth-ai-dev" not in res.stdout:
                return plan
            # try inside
            check = _run_cmd(
                ["distrobox", "enter", "kyth-ai-dev", "--", "command", "-v", "ollama"],
                capture_output=True, timeout=3,
            )
            if check.returncode != 0:
                return plan
            # For now, don't actually call remote model — keep offline deterministic.
            # The hook is here for future GHCR-signed prompt work.
            return plan
        # If local ollama exists but we want to keep fully offline deterministic,
        # skip network call as well — preserve GHCR-signed / offline story.
        return plan
    except Exception:
        return plan


def build_repair_plan(
    *,
    snapshot: dict[str, Any] | None = None,
    boot_state: Any | None = None,
    evaluation: Any | None = None,
    snapshot_path: Path | None = None,
) -> dict[str, Any]:
    """Convenience wrapper returning a serializable repair plan dict."""
    if snapshot is None and snapshot_path is not None:
        try:
            snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
            if isinstance(snapshot, dict) and "sections" in snapshot:
                # Unwrap probe-cache.json sections wrapper
                secs = snapshot.get("sections", {})
                snapshot = {k: v.get("data", v) if isinstance(v, dict) and "data" in v and "ts" in v else v for k, v in secs.items()}
        except Exception:
            snapshot = {}
    if snapshot is None:
        snapshot = {}
    if boot_state is None:
        try:
            from kyth_shared.boot_health import read_state

            boot_state = read_state()
        except Exception:
            boot_state = None
    if evaluation is None:
        try:
            from kyth_shared.hardware_policy import evaluate_system

            evaluation = evaluate_system()
        except Exception:
            evaluation = None
    plan = generate_plan(snapshot, boot_state, evaluation)
    enhanced = try_ollama_enhance(plan)
    as_dict = enhanced.as_dict()
    # Also push to HubState if available (control plane sharing)
    try:
        from kyth_welcome.services.hub_state import HUB_STATE  # type: ignore

        HUB_STATE.set_repair_plan(as_dict)
    except Exception:
        pass
    return as_dict

# New #7-10: Game Boost transactional FPS, System Restore UI, Peripherals zero-config, Local AI offline
