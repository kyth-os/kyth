"""Desktop stack health — portals, PipeWire, and session signals.

These checks are for ``kyth-doctor`` / smoke diagnostics. They are deliberately
*not* greenboot rollback triggers: a greeter-only boot (no user session yet)
must not quarantine a deployment, and portal/PipeWire units are user-scoped.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Callable, Sequence

from kyth_shared.commands import run_text

# Plasma 6 may expose either unit name depending on packaging generation.
PORTAL_KDE_UNITS = (
    "plasma-xdg-desktop-portal-kde.service",
    "xdg-desktop-portal-kde.service",
)
PORTAL_UNITS = ("xdg-desktop-portal.service",)
PIPEWIRE_UNITS = ("pipewire.service", "wireplumber.service")

# Image-level binaries/packages we expect on a Kyth desktop image.
REQUIRED_PATHS = (
    "/usr/libexec/xdg-desktop-portal",
    "/usr/libexec/xdg-desktop-portal-kde",
)
# Some Fedora builds install the portal under /usr/libexec/xdg-desktop-portal*
# while older trees used different paths — also accept the package binaries.
OPTIONAL_PORTAL_BINS = (
    "xdg-desktop-portal",
    "xdg-desktop-portal-kde",
)


@dataclass(frozen=True, slots=True)
class StackCheck:
    name: str
    passed: bool
    detail: str
    advisory: bool = False


def _user_unit_active(unit: str) -> bool:
    result = run_text(["systemctl", "--user", "is-active", unit], timeout=8)
    return result is not None and result.stdout.strip() == "active"


def _any_user_unit_active(units: Sequence[str], unit_active: Callable[[str], bool]) -> bool:
    return any(unit_active(unit) for unit in units)


def _has_session_bus() -> bool:
    return bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS"))


def _session_type() -> str:
    return os.environ.get("XDG_SESSION_TYPE", "").strip().lower()


def _portal_binaries_present(
    *,
    path_exists: Callable[[str], bool],
    which: Callable[[str], str | None],
) -> tuple[bool, str]:
    present = [path for path in REQUIRED_PATHS if path_exists(path)]
    if present:
        return True, ", ".join(present)
    found_bins = [name for name in OPTIONAL_PORTAL_BINS if which(name)]
    if found_bins:
        return True, "bins: " + ", ".join(found_bins)
    # libexec path may differ by Fedora release; treat missing as soft fail
    # when we cannot prove absence of the KDE portal package layout.
    kde_alt = "/usr/lib64/libexec/xdg-desktop-portal-kde"
    if path_exists(kde_alt) or path_exists("/usr/lib/xdg-desktop-portal-kde"):
        return True, "kde portal libexec present"
    return False, "xdg-desktop-portal / kde backend not found on image"


def desktop_stack_checks(
    *,
    has_session_bus: Callable[[], bool] = _has_session_bus,
    session_type: Callable[[], str] = _session_type,
    user_unit_active: Callable[[str], bool] = _user_unit_active,
    path_exists: Callable[[str], bool] = os.path.exists,
    which: Callable[[str], str | None] = shutil.which,
    wayland_display: Callable[[], str] = lambda: os.environ.get("WAYLAND_DISPLAY", ""),
) -> tuple[StackCheck, ...]:
    """Probe desktop stack readiness for diagnostics (not greenboot)."""
    checks: list[StackCheck] = []

    bins_ok, bins_detail = _portal_binaries_present(path_exists=path_exists, which=which)
    checks.append(
        StackCheck(
            "Portal packages",
            bins_ok,
            bins_detail if bins_ok else bins_detail + " — install xdg-desktop-portal-kde",
            advisory=False,
        )
    )

    if not has_session_bus():
        checks.append(
            StackCheck(
                "User desktop session",
                True,
                "skipped: no user session bus (greeter / SSH / image build)",
                advisory=True,
            )
        )
        return tuple(checks)

    stype = session_type()
    if stype == "wayland":
        wd = wayland_display().strip()
        checks.append(
            StackCheck(
                "Wayland display",
                bool(wd),
                f"WAYLAND_DISPLAY={wd}" if wd else "Wayland session without WAYLAND_DISPLAY",
                advisory=False,
            )
        )
    elif stype == "x11":
        checks.append(
            StackCheck(
                "Wayland display",
                False,
                "X11 session — KythOS ships Plasma Wayland only",
                advisory=False,
            )
        )
    else:
        checks.append(
            StackCheck(
                "Wayland display",
                True,
                f"session type {stype or 'unknown'} — Wayland checks skipped",
                advisory=True,
            )
        )

    portal_ok = _any_user_unit_active(PORTAL_UNITS, user_unit_active)
    checks.append(
        StackCheck(
            "xdg-desktop-portal",
            portal_ok,
            "xdg-desktop-portal.service active"
            if portal_ok
            else "xdg-desktop-portal.service not active — screen share / Flatpak dialogs may fail",
            advisory=True,
        )
    )

    kde_ok = _any_user_unit_active(PORTAL_KDE_UNITS, user_unit_active)
    checks.append(
        StackCheck(
            "KDE portal backend",
            kde_ok,
            "plasma/xdg-desktop-portal-kde active"
            if kde_ok
            else "KDE portal backend not active — restart: systemctl --user restart xdg-desktop-portal-kde",
            advisory=True,
        )
    )

    for unit in PIPEWIRE_UNITS:
        active = user_unit_active(unit)
        label = "PipeWire" if unit.startswith("pipewire") else "WirePlumber"
        checks.append(
            StackCheck(
                label,
                active,
                f"{unit} active" if active else f"{unit} not active — audio/capture degraded",
                advisory=True,
            )
        )

    return tuple(checks)


def format_desktop_stack_report(checks: Sequence[StackCheck] | None = None) -> str:
    checks = desktop_stack_checks() if checks is None else checks
    lines = ["Desktop stack:"]
    for check in checks:
        mark = "ok" if check.passed else ("warn" if check.advisory else "FAIL")
        lines.append(f" - [{mark}] {check.name}: {check.detail}")
    return "\n".join(lines)
