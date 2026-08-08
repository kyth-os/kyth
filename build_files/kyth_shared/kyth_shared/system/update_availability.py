"""Single availability truth for System Hub's Update page.

The Update page previously stitched three independent sources:
  * `bootc_status_data()` (local booted/staged digests, cached 5 s)
  * `check_registry_update()` → `skopeo inspect` (remote digest, 45 s timeout)
  * `flatpak remote-ls --updates` (flatpak count)

`UpdateCheckCoordinator` required *both* probes to complete, but neither had
a Hub-side deadline. If `skopeo` or `flatpak` hung (slow CachyOS testing
mirror, offline live session), `page_update_availability` stayed on
“Checking…” forever — issue #164. Manual `Full Update` worked because it
bypasses the coordinator and runs `kyth-full-update` directly.

This module provides the single `AvailabilityStatus` the Hub should render and
a helper that enforces a Hub-side timeout so the page always reaches a
terminal `available | uptodate | staged | error` state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kyth_shared.system.bootc import bootc_status_data, has_staged_update
from kyth_shared.system.bootc_policy import UpdateAvailabilityView, update_availability_view
from kyth_shared.system.registry import check_registry_update, REGISTRY
from kyth_shared.system.bootc_query import image_digest_from_status
from kyth_shared.system.probe import probe_cached

FLATPAK_CACHE_TTL = 10.0
BOOTC_CACHE_TTL = 5.0
# Hub-side deadline for the whole availability probe. 45 s skopeo + flatpak
# should never keep the spinner longer than this.
AVAILABILITY_TIMEOUT_S = 15


@dataclass(frozen=True, slots=True)
class AvailabilityStatus:
    """What the Hub’s availability card should show."""

    state: str  # idle | checking | available | uptodate | staged | error
    detail: str = ""
    flatpak_count: int = 0
    flatpak_detail: str = ""
    staged: bool = False
    manifest_raw: str = ""
    blocked_reason: str = ""


def _flatpak_count_cached() -> int | None:
    from kyth_shared.system.process import run_command

    # Reuse the same probe cache key the Flatpak probe worker uses so a
    # Hub-side poll and a background kyth-probe refresh share the result.
    def _fetch() -> int | None:
        total = 0
        saw_ok = False
        for scope in ("--system", "--user"):
            result = run_command(
                ["flatpak", "remote-ls", "--updates", scope, "--columns=application"],
                timeout=15,
            )
            if result is None or result.returncode != 0:
                continue
            saw_ok = True
            total += len([ln for ln in result.stdout.splitlines() if ln.strip()])
        return total if saw_ok else None

    return probe_cached("flatpak-updates", FLATPAK_CACHE_TTL, _fetch)


def collect_availability(*, branch: str | None = None, use_cached: bool = True) -> AvailabilityStatus:
    """Synchronous, timeout-bounded availability check.

    Used by tests and by the worker thread. Never raises — on any error it
    returns `state="error"` so the Hub can render a retry banner instead of
    spinning forever. Callers that need async should run this in a
    `TrackedThread`/`QTimer` like the Hub does.
    """
    # staged takes precedence — no registry call needed
    try:
        staged = bool(has_staged_update())
    except Exception:
        staged = False
    if staged:
        # staged image already pending reboot — no need to check remote
        flatpak = _flatpak_count_cached() if use_cached else 0
        return AvailabilityStatus(
            state="staged",
            detail="A staged image is ready to boot.",
            flatpak_count=max(0, flatpak or 0),
            staged=True,
        )

    # Resolve branch and status once (both are probe-cached)
    try:
        from kyth_shared.system.bootc import current_branch

        b = branch or current_branch() or "latest"
        status_data = bootc_status_data() or {}
    except Exception as exc:
        return AvailabilityStatus(state="error", detail=str(exc))

    # Registry check — the slow path (skopeo, 45 s inner timeout)
    try:
        result = check_registry_update(
            status_data=status_data,
            branch=b,
            registry=REGISTRY,
        )
        manifest_raw = result.manifest_raw.decode("utf-8", errors="ignore") if result.manifest_raw else ""
        if result.state == "error":
            return AvailabilityStatus(state="error", detail=result.detail, flatpak_count=0)
        system_state = result.state  # "available" | "uptodate" | etc
        system_detail = result.detail
    except Exception as exc:
        return AvailabilityStatus(state="error", detail=str(exc))

    # Flatpak count — best effort, never fails the whole check
    try:
        flatpak = _flatpak_count_cached()
        flatpak_count = max(0, int(flatpak)) if flatpak is not None else 0
        flatpak_detail = ""
    except Exception as exc:
        flatpak_count = 0
        flatpak_detail = str(exc)

    # Map registry states to Hub card states
    if system_state == "available":
        state = "available"
    elif system_state == "uptodate":
        state = "uptodate"
    else:
        state = system_state

    return AvailabilityStatus(
        state=state,
        detail=system_detail,
        flatpak_count=flatpak_count,
        flatpak_detail=flatpak_detail,
        staged=False,
        manifest_raw=manifest_raw,
    )


def availability_view(status: AvailabilityStatus, *, check_ts: str, staged_ts: str | None) -> UpdateAvailabilityView:
    """Thin adapter from `AvailabilityStatus` to the existing view helper."""
    return update_availability_view(
        staged=status.staged,
        check_state=status.state,
        flatpak_count=status.flatpak_count,
        check_ts=check_ts,
        check_ts_details=status.detail,
        staged_ts=staged_ts,
    )
