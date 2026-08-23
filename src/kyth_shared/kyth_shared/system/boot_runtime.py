"""Runtime boot assertions for greenboot.

The presence checks in :mod:`kyth_shared.boot_health` prove the deployed tree
was assembled correctly, but every one of them inspects a path baked into the
image — so they cannot fail on a deployment that boots to a black screen, and
greenboot's rollback never fires on the failures users actually hit.

These probes assert *observable runtime state* instead: the display stack
reached its target, a DRM device exists (the classic akmod-nvidia build
failure leaves none), and no critical unit gave up.

Rollback is a heavy hammer, so the checks here are deliberately conservative —
each one must be unambiguous and unable to flap, because a false positive costs
a user their current deployment. Vendor-specific driver assertions are left out
for that reason: a hybrid laptop that parks its discrete GPU is healthy, and
``/dev/dri`` covers "no display driver at all" without guessing.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from ..commands import run_text

# Must clear kyth-selinux-relabel-home (TimeoutStartSec=300) plus greeter
# startup. The previous 180s budget raced restorecon on large /var/home and
# scored a healthy first boot red.
DEFAULT_DEADLINE = 300.0
DEFAULT_INTERVAL = 2.0
SYSTEMD_RUNTIME_MARKER = Path("/run/systemd/system")
DRM_DEVICE_DIR = Path("/dev/dri")
GRAPHICAL_TARGET = "graphical.target"
# plasmalogin.service carries the display-manager.service alias; `list-units`
# reports the concrete name, so both spellings are matched.
DISPLAY_MANAGER_UNITS = ("plasmalogin.service", "display-manager.service")
CRITICAL_UNITS = frozenset({
    "dbus-broker.service",
    "dbus.service",
    "display-manager.service",
    "plasmalogin.service",
    "NetworkManager.service",
})


@dataclass(frozen=True, slots=True)
class RuntimeCheck:
    name: str
    passed: bool
    detail: str


def _systemd_booted() -> bool:
    return SYSTEMD_RUNTIME_MARKER.is_dir()


def _unit_active(unit: str) -> bool:
    result = run_text(["systemctl", "is-active", unit], timeout=10)
    return result is not None and result.stdout.strip() == "active"


def _default_target() -> str:
    result = run_text(["systemctl", "get-default"], timeout=10)
    return result.stdout.strip() if result is not None else ""


def _failed_units() -> frozenset[str]:
    result = run_text(
        ["systemctl", "list-units", "--state=failed", "--no-legend", "--plain", "--no-pager"],
        timeout=15,
    )
    if result is None:
        return frozenset()
    return frozenset(
        fields[0] for fields in (line.split() for line in result.stdout.splitlines()) if fields
    )


def _display_manager_active(unit_active: Callable[[str], bool]) -> bool:
    return any(unit_active(unit) for unit in DISPLAY_MANAGER_UNITS)


def _drm_devices() -> tuple[str, ...]:
    try:
        return tuple(sorted(path.name for path in DRM_DEVICE_DIR.glob("card*")))
    except OSError:
        return ()


def _wait_until(
    predicate: Callable[[], bool],
    *,
    deadline: float,
    interval: float,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> bool:
    """Poll *predicate* until it holds or *deadline* seconds elapse."""
    start = monotonic()
    while True:
        if predicate():
            return True
        if monotonic() - start >= deadline:
            return False
        sleep(interval)


def runtime_checks(
    *,
    systemd_booted: Callable[[], bool] = _systemd_booted,
    unit_active: Callable[[str], bool] = _unit_active,
    default_target: Callable[[], str] = _default_target,
    failed_units: Callable[[], frozenset[str]] = _failed_units,
    drm_devices: Callable[[], Sequence[str]] = _drm_devices,
    deadline: float = DEFAULT_DEADLINE,
    interval: float = DEFAULT_INTERVAL,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[RuntimeCheck, ...]:
    """Assert this boot actually produced a usable desktop.

    greenboot runs its required checks well before ``graphical.target`` would
    normally settle, so the display assertions poll up to *deadline* seconds
    rather than sampling once and declaring the boot dead.

    This deliberately never asserts on ``graphical.target`` itself being
    active. greenboot-healthcheck.service is ``WantedBy=multi-user.target``,
    and systemd gives target units an implicit ``After=`` on everything they
    ``Wants=``/``Requires=`` — so ``multi-user.target`` (and therefore
    ``graphical.target``, which requires it) cannot go active until *this
    service's own job* finishes. Polling for graphical.target here would wait
    on a state this process's own execution blocks, timing out and failing
    every healthy boot regardless of how fast the desktop actually came up.
    Display-manager activation is not behind that ordering, so it is used as
    the non-circular proxy for "the display stack came up".
    """
    if not systemd_booted():
        # Image build, container, or test context: there is no boot to assess,
        # and failing here would quarantine a deployment over a missing runtime.
        return (RuntimeCheck("Runtime assertions", True, "skipped: not a systemd boot"),)

    target = default_target()
    expects_graphical = target == GRAPHICAL_TARGET

    def _ready() -> bool:
        if expects_graphical and not _display_manager_active(unit_active):
            return False
        if expects_graphical:
            return bool(drm_devices())
        return True

    _wait_until(
        _ready,
        deadline=deadline,
        interval=interval,
        monotonic=monotonic,
        sleep=sleep,
    )

    checks: list[RuntimeCheck] = []
    if expects_graphical:
        reached = _display_manager_active(unit_active)
        checks.append(
            RuntimeCheck(
                "Graphical session",
                reached,
                "display manager active"
                if reached
                else f"display manager not reached within {deadline:.0f}s",
            )
        )
    else:
        # A deliberately headless deployment is not a rollback trigger.
        checks.append(
            RuntimeCheck(
                "Graphical session",
                True,
                f"skipped: default target is {target or 'unknown'}",
            )
        )

    devices = tuple(drm_devices())
    # Headless deployments intentionally have no DRM device; don't fail them.
    if expects_graphical:
        checks.append(
            RuntimeCheck(
                "Display device",
                bool(devices),
                f"/dev/dri: {', '.join(devices)}"
                if devices
                else "no DRM card device — GPU driver did not load",
            )
        )
    else:
        checks.append(
            RuntimeCheck(
                "Display device",
                True,
                f"skipped: default target is {target or 'unknown'}",
            )
        )

    failed = frozenset(failed_units()) & CRITICAL_UNITS
    checks.append(
        RuntimeCheck(
            "Critical units",
            not failed,
            "no critical unit failed"
            if not failed
            else "failed: " + ", ".join(sorted(failed)),
        )
    )
    return tuple(checks)
