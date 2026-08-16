"""Tests for runtime boot assertions used by greenboot's required checks."""
from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.system.boot_runtime import (  # noqa: E402
    CRITICAL_UNITS,
    RuntimeCheck,
    runtime_checks,
)


class FakeClock:
    """Monotonic clock that only advances when the code under test sleeps."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def probe(
    *,
    booted=True,
    target="graphical.target",
    active_units=("graphical.target", "sddm.service"),
    failed=(),
    devices=("card0",),
    clock=None,
    deadline=120.0,
):
    clock = clock or FakeClock()
    return runtime_checks(
        systemd_booted=lambda: booted,
        unit_active=lambda unit: unit in active_units,
        default_target=lambda: target,
        failed_units=lambda: frozenset(failed),
        drm_devices=lambda: devices,
        deadline=deadline,
        interval=2.0,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )


def by_name(checks, name: str) -> RuntimeCheck:
    return next(check for check in checks if check.name == name)


class HealthyBootTests(unittest.TestCase):
    def test_graphical_boot_with_drm_passes_every_check(self):
        checks = probe()

        self.assertTrue(all(check.passed for check in checks), checks)
        self.assertEqual(
            {"Graphical session", "Display device", "Critical units"},
            {check.name for check in checks},
        )

    def test_healthy_boot_does_not_wait(self):
        clock = FakeClock()

        probe(clock=clock)

        self.assertEqual(0.0, clock.now)


class RollbackTriggerTests(unittest.TestCase):
    def test_graphical_target_never_reached_fails(self):
        checks = probe(active_units=())

        session = by_name(checks, "Graphical session")
        self.assertFalse(session.passed)
        self.assertIn("not reached within 120s", session.detail)

    def test_missing_drm_device_fails(self):
        """The akmod-nvidia build failure: system is up, nothing can display."""
        checks = probe(devices=())

        display = by_name(checks, "Display device")
        self.assertFalse(display.passed)
        self.assertIn("GPU driver did not load", display.detail)

    def test_failed_critical_unit_fails(self):
        checks = probe(failed=("sddm.service", "cups.service"))

        units = by_name(checks, "Critical units")
        self.assertFalse(units.passed)
        self.assertIn("sddm.service", units.detail)

    def test_unrelated_failed_unit_is_tolerated(self):
        """A failed printer daemon is not worth discarding the deployment."""
        checks = probe(failed=("cups.service", "fstrim.service"))

        self.assertTrue(by_name(checks, "Critical units").passed)

    def test_wait_gives_up_at_the_deadline(self):
        clock = FakeClock()

        probe(active_units=(), clock=clock, deadline=10.0)

        self.assertGreaterEqual(clock.now, 10.0)
        self.assertLess(clock.now, 20.0)


class LateReadinessTests(unittest.TestCase):
    def test_display_stack_that_settles_during_the_poll_passes(self):
        """greenboot runs before graphical.target; the check must wait for it."""
        clock = FakeClock()
        state = {"active": False}

        def unit_active(unit: str) -> bool:
            # Becomes reachable only after the poll loop has slept a while.
            if clock.now >= 6.0:
                state["active"] = True
            return state["active"] and unit in (
                "graphical.target",
                "sddm.service",
                "display-manager.service",
            )

        checks = runtime_checks(
            systemd_booted=lambda: True,
            unit_active=unit_active,
            default_target=lambda: "graphical.target",
            failed_units=frozenset,
            drm_devices=lambda: ("card0",),
            deadline=120.0,
            interval=2.0,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

        self.assertTrue(by_name(checks, "Graphical session").passed)
        self.assertLess(clock.now, 120.0)


class GraphicalTargetOrderingTests(unittest.TestCase):
    """greenboot-healthcheck.service is WantedBy=multi-user.target, and systemd
    gives target units an implicit After= on everything they Wants=/Requires=.
    That means graphical.target (which Requires=multi-user.target) cannot go
    active until *this check's own service* finishes — so asserting on
    graphical.target's activation state deadlocks every healthy boot. Regression
    for that: the check must pass promptly on display-manager + DRM alone, even
    when graphical.target itself never reports active.
    """

    def test_passes_without_waiting_when_graphical_target_never_reports_active(self):
        clock = FakeClock()

        checks = probe(
            active_units=("sddm.service",),  # graphical.target deliberately absent
            clock=clock,
        )

        session = by_name(checks, "Graphical session")
        self.assertTrue(session.passed, checks)
        self.assertEqual(0.0, clock.now)

    def test_display_manager_service_name_also_satisfies_the_check(self):
        checks = probe(active_units=("display-manager.service",))

        self.assertTrue(by_name(checks, "Graphical session").passed)


class NonRollbackContextTests(unittest.TestCase):
    def test_non_systemd_context_is_skipped(self):
        """Image build/container: no boot to assess, so nothing to quarantine."""
        checks = probe(booted=False, devices=(), active_units=())

        self.assertTrue(all(check.passed for check in checks))
        self.assertIn("not a systemd boot", checks[0].detail)

    def test_headless_default_target_skips_graphical_assertion(self):
        checks = probe(target="multi-user.target", active_units=())

        session = by_name(checks, "Graphical session")
        self.assertTrue(session.passed)
        self.assertIn("multi-user.target", session.detail)

    def test_headless_still_requires_critical_units(self):
        checks = probe(
            target="multi-user.target", active_units=(), failed=("NetworkManager.service",)
        )

        self.assertFalse(by_name(checks, "Critical units").passed)


class CriticalUnitPolicyTests(unittest.TestCase):
    def test_display_manager_matched_under_both_names(self):
        """sddm.service carries the display-manager.service alias."""
        self.assertIn("sddm.service", CRITICAL_UNITS)
        self.assertIn("display-manager.service", CRITICAL_UNITS)


if __name__ == "__main__":
    unittest.main()
