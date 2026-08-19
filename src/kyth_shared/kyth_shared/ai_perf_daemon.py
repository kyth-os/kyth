"""AI perf daemon core — offline policy picker with 30s TTL rollback.

Pure, no Qt, no cloud. Watches gaming/cgroup/power + hardware caps and
picks scx + sysctl + GPU perf level. Ollama is optional local enhancer;
deterministic rules win when absent. Mirrors ai_assist fallback style.
"""
from __future__ import annotations
import logging

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kyth_shared.commands import run

logger = logging.getLogger(__name__)

# TTL for daemon-applied policy — auto-revert if p95 worsens or daemon stops
POLICY_TTL_S = 30
SCX_LOADER_CONF = Path("/etc/scx/scx_loader.conf")
SYSCTL_CONF = Path("/etc/sysctl.d/99-kyth-ai.conf")

# Deterministic mapping used when ollama absent or offline
# Keys are (is_gaming, power_profile, has_nvidia, has_amd) patterns
DEFAULT_SCX_FOR_GAMING = "scx_rusty"
DEFAULT_SCX_FOR_DESKTOP = "scx_bpfland"


@dataclass(frozen=True, slots=True)
class PerfSample:
    is_gaming: bool
    pressure_some_avg10: float  # 0..100
    power_profile: str  # performance|balanced|power-saver|unknown
    battery_percent: int | None
    has_nvidia: bool
    has_amd: bool
    hdr_active: bool = False


@dataclass(frozen=True, slots=True)
class PerfPolicy:
    scx: str  # scx_rusty|scx_bpfland|scx_lavd|none
    sysctl: dict[str, str]
    gpu_power: str  # auto|high|low
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "scx": self.scx,
            "sysctl": dict(self.sysctl),
            "gpu_power": self.gpu_power,
            "reason": self.reason,
            "ttl": POLICY_TTL_S,
        }


def _power_profile() -> str:
    for cmd in (
        ["powerprofilesctl", "get"],
        ["powerprofilesctl", "get", "--no-pager"],
    ):
        try:
            res = run(cmd, capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip().lower()
        except (OSError, ValueError) as exc:
            logger.debug("_power_profile %s failed: %s", cmd, exc, exc_info=True)
            pass
    return "unknown"


def _battery_percent() -> int | None:
    for path in (
        Path("/sys/class/power_supply/BAT0/capacity"),
        Path("/sys/class/power_supply/BAT1/capacity"),
    ):
        try:
            txt = path.read_text(encoding="utf-8").strip()
            return int(txt)
        except (OSError, ValueError) as exc:
            logger.debug("_battery_percent read %s failed: %s", path, exc, exc_info=True)
            continue
    return None


def _pressure_avg10() -> float:
    for path in (Path("/proc/pressure/cpu"), Path("/sys/fs/cgroup/cpu.pressure")):
        try:
            txt = path.read_text(encoding="utf-8")
            # cpu pressure: some avg10=0.12 avg60=... ; cgroup: some avg10=...
            for part in txt.split():
                if part.startswith("avg10="):
                    return float(part.split("=")[1])
        except (OSError, ValueError) as exc:
            logger.debug("_pressure_avg10 read %s failed: %s", path, exc, exc_info=True)
            continue
    return 0.0


def _detect_gaming() -> bool:
    try:
        from kyth_shared.gaming import proc_gaming_active

        if proc_gaming_active():
            return True
    except (OSError, ValueError, ImportError, RuntimeError) as exc:
        logger.debug("proc_gaming_active failed: %s", exc, exc_info=True)
        pass
    try:
        # fallback: if gamescope session lock exists
        from kyth_shared.gaming import _active_uids, gamescope_session_active

        for uid in _active_uids():
            if gamescope_session_active(uid):
                return True
    except (OSError, ValueError, ImportError, RuntimeError) as exc:
        logger.debug("gamescope_session_active failed: %s", exc, exc_info=True)
        pass
    return False


def _hardware_caps() -> tuple[bool, bool]:
    has_nvidia = False
    has_amd = False
    try:
        from kyth_shared.hardware_policy import evaluate_system

        ev = evaluate_system()
        caps = set(ev.capabilities)
        has_nvidia = "gpu.nvidia" in caps
        has_amd = "gpu.amd" in caps
    except (OSError, ValueError, ImportError, RuntimeError) as exc:
        logger.debug("evaluate_system failed: %s", exc, exc_info=True)
        # Fallback to probe
        try:
            from kyth_shared.system.probe import read_section

            has_nvidia = bool(read_section("nvidia-detect", max_age=300))
        except (OSError, ValueError, ImportError, RuntimeError) as exc:
            logger.debug("probe fallback failed: %s", exc, exc_info=True)
            pass
    return has_nvidia, has_amd


def collect_sample() -> PerfSample:
    has_nvidia, has_amd = _hardware_caps()
    return PerfSample(
        is_gaming=_detect_gaming(),
        pressure_some_avg10=_pressure_avg10(),
        power_profile=_power_profile(),
        battery_percent=_battery_percent(),
        has_nvidia=has_nvidia,
        has_amd=has_amd,
        hdr_active=False,
    )


def _ollama_choose(sample: PerfSample, evaluation: Any | None) -> PerfPolicy | None:
    """Try local ollama qwen2.5-coder for a nuanced pick. Never fails."""
    _model = os.environ.get("KYTH_AI_MODEL", "qwen2.5-coder")  # noqa: F841
    _prompt = (  # noqa: F841
        f"Sample is_gaming={sample.is_gaming} pressure={sample.pressure_some_avg10:.1f} "
        f"power={sample.power_profile} battery={sample.battery_percent} "
        f"nvidia={sample.has_nvidia} amd={sample.has_amd}. "
        f"Pick scx in [scx_rusty, scx_bpfland, scx_lavd, none] and one-line reason. "
        f"Prefer scx_rusty for gaming, bpfland for desktop, lavd for mixed."
    )
    # Only attempt if ollama binary or kyth-ai-dev box has it — else offline
    try:
        # Check distrobox box quickly via commands.run (no subprocess)
        box_check = run(["distrobox", "list", "--no-color"], capture_output=True, text=True, timeout=3)
        has_box = "kyth-ai-dev" in (box_check.stdout if box_check.returncode == 0 else "")
        local_ollama = Path("/usr/bin/ollama").exists() or Path("/usr/local/bin/ollama").exists()
        if not (has_box or local_ollama):
            return None
        # For now keep deterministic — hook is here for GHCR-signed prompt work
        # Real call would be: ollama run <model> "<prompt>" with 4s timeout
        # Keeping offline to avoid network/flake in daemon loop
        return None
    except (OSError, ValueError) as exc:
        logger.debug("_ollama_choose failed: %s", exc, exc_info=True)
        return None


def choose_policy(
    sample: PerfSample,
    evaluation: Any | None = None,
    boot_state: Any | None = None,
) -> PerfPolicy:
    # Try local LLM first (optional)
    llm = _ollama_choose(sample, evaluation)
    if llm is not None:
        return llm

    # Deterministic fallback — TTL-bounded, safe to revert
    if sample.is_gaming:
        # Gaming: favor low-latency SCX, keep GPU high when plugged
        scx = DEFAULT_SCX_FOR_GAMING
        gpu = "high" if sample.power_profile != "power-saver" and (sample.battery_percent is None or sample.battery_percent > 30) else "auto"
        sysctl: dict[str, str] = {"vm.swappiness": "10", "kernel.sched_latency_ns": "8000000"}
        reason = "gaming active — scx_rusty + low swappiness"
        if sample.has_nvidia and sample.power_profile == "performance":
            gpu = "high"
        return PerfPolicy(scx=scx, sysctl=sysctl, gpu_power=gpu, reason=reason)

    # Desktop / mixed pressure
    if sample.pressure_some_avg10 > 40:
        return PerfPolicy(scx="scx_lavd", sysctl={"vm.swappiness": "15"}, gpu_power="auto", reason=f"high pressure {sample.pressure_some_avg10:.1f} — lavd")
    if sample.power_profile == "power-saver" or (sample.battery_percent is not None and sample.battery_percent < 20):
        return PerfPolicy(scx="none", sysctl={"vm.swappiness": "60"}, gpu_power="low", reason="battery saver — scx none")
    return PerfPolicy(scx=DEFAULT_SCX_FOR_DESKTOP, sysctl={"vm.swappiness": "30"}, gpu_power="auto", reason="desktop — bpfland balanced")


def apply_policy(policy: PerfPolicy, ttl: int = POLICY_TTL_S) -> bool:
    """Atomically write scx + sysctl + gpu files with TTL marker. Returns ok."""
    try:
        # SCX loader — Fedora scx_loader reads /etc/scx/scx_loader.conf
        SCX_LOADER_CONF.parent.mkdir(parents=True, exist_ok=True)
        if policy.scx == "none":
            content = "# kyth-ai-perfd: no scx (ttl %d) reason: %s\n" % (ttl, policy.reason)
        else:
            content = "SCX_SCHEDULER=%s\n# reason: %s ttl %d\n" % (policy.scx, policy.reason, ttl)
        tmp = SCX_LOADER_CONF.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(SCX_LOADER_CONF)

        # sysctl — 99-kyth-ai.conf, TTL via header comment; systemd-sysctl will apply on next boot, daemon applies now
        SYSCTL_CONF.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# kyth-ai-perfd ttl {ttl} reason: {policy.reason}"]
        for k, v in policy.sysctl.items():
            lines.append(f"{k} = {v}")
        tmp2 = SYSCTL_CONF.with_suffix(".tmp")
        tmp2.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp2.replace(SYSCTL_CONF)
        # Apply now (best-effort, requires root for /etc)
        for k, v in policy.sysctl.items():
            try:
                run(["sysctl", "-w", f"{k}={v}"], capture_output=True, timeout=3)
            except (OSError, ValueError) as exc:
                logger.debug("sysctl %s failed: %s", k, exc, exc_info=True)
                pass
        # GPU power — best-effort (may need root)
        if policy.gpu_power in ("high", "auto", "low"):
            level = {"high": "high", "low": "low", "auto": "auto"}[policy.gpu_power]
            for card in Path("/sys/class/drm").glob("card*/device/power_dpm_force_performance_level"):
                try:
                    card.write_text(level, encoding="utf-8")
                except (OSError, ValueError) as exc:
                    logger.debug("gpu power write failed: %s", exc, exc_info=True)
                    pass
        # Record TTL marker for rollback
        marker = Path("/run/kyth-ai-perfd-ttl")
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(str(int(time.time()) + ttl), encoding="utf-8")
        except (OSError, ValueError) as exc:
            logger.debug("ttl marker write failed: %s", exc, exc_info=True)
            pass
        # Also expose current SCX for gamescope env merge (KYTH_AI_SCX)
        try:
            Path("/run/kyth-ai-perfd-scx").write_text(policy.scx, encoding="utf-8")
        except (OSError, ValueError) as exc:
            logger.debug("scx marker write failed: %s", exc, exc_info=True)
            pass
        # Push to HUB_STATE so Welcome/Performance cards show it without extra probe
        try:
            from kyth_welcome.services.hub_state import HUB_STATE

            HUB_STATE.set("ai_perf", policy.as_dict())
        except (OSError, ValueError, ImportError, RuntimeError) as exc:
            logger.debug("HUB_STATE push failed: %s", exc, exc_info=True)
            pass
        return True
    except (OSError, ValueError) as exc:
        logger.debug("apply_policy failed: %s", exc, exc_info=True)
        return False


def should_rollback(previous: PerfPolicy, current_fps_p95_ms: float | None, baseline_p95_ms: float | None) -> bool:
    if current_fps_p95_ms is None or baseline_p95_ms is None:
        return False
    # Roll back if p95 got worse by >10%
    return current_fps_p95_ms > baseline_p95_ms * 1.10
