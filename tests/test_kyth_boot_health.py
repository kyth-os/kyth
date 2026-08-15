"""Tests for digest-aware boot health, quarantine, and rollout policy."""
from __future__ import annotations

import json
import pathlib
import subprocess  # nosec B404 - fixture return object only
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.boot_health import (  # noqa: E402
    BootHealthState,
    clear_quarantine,
    image_ring,
    mark_healthy,
    quarantine_reason,
    QuarantineRecord,
    read_state,
    record_failure,
    record_staged,
    required_checks,
    rollout_policy_reason,
    write_state,
)
from kyth_shared.system.boot_runtime import RuntimeCheck  # noqa: E402
from kyth_shared import safe_upgrade  # noqa: E402


DIGEST = "sha256:" + "a" * 64
OTHER_DIGEST = "sha256:" + "b" * 64


class BootHealthStateTests(unittest.TestCase):
    def test_atomic_round_trip_is_support_readable(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "boot-health.json"
            expected = record_staged(
                BootHealthState(), DIGEST, rollout_ring="testing", now=100
            )

            write_state(expected, path)

            self.assertEqual(read_state(path), expected)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(json.loads(path.read_text())["schema_version"], 1)

    def test_failures_are_counted_once_per_boot_and_then_quarantined(self):
        state = BootHealthState()
        state = record_failure(state, DIGEST, "boot-1", "display failed", now=1)
        duplicate = record_failure(state, DIGEST, "boot-1", "display failed", now=2)
        second = record_failure(duplicate, DIGEST, "boot-2", "display failed", now=3)
        third = record_failure(second, DIGEST, "boot-3", "display failed", now=4)

        self.assertEqual(duplicate.failures, 1)
        self.assertEqual(second.failures, 2)
        self.assertEqual(third.failures, 3)
        self.assertEqual(third.status, "quarantined")
        self.assertIn("3 unhealthy boots", quarantine_reason(third, DIGEST))

    def test_healthy_boot_resets_failures_and_clears_its_quarantine(self):
        state = BootHealthState()
        for index in range(3):
            state = record_failure(
                state, DIGEST, f"boot-{index}", "failed", now=index
            )

        healthy = mark_healthy(state, DIGEST, now=10)

        self.assertEqual(healthy.status, "healthy")
        self.assertEqual(healthy.failures, 0)
        self.assertEqual(healthy.last_healthy_digest, DIGEST)
        self.assertIsNone(quarantine_reason(healthy, DIGEST))

    def test_healthy_rollback_records_the_digest_it_recovered_from(self):
        state = BootHealthState()
        for index in range(3):
            state = record_failure(
                state, DIGEST, f"boot-{index}", "failed", now=index
            )

        recovered = mark_healthy(state, OTHER_DIGEST, now=10)

        self.assertEqual(recovered.status, "recovered")
        self.assertEqual(recovered.last_recovered_digest, DIGEST)
        self.assertIn(DIGEST, recovered.last_reason)

    def test_failure_count_restarts_for_a_different_digest(self):
        first = record_failure(
            BootHealthState(), DIGEST, "boot-1", "failed", now=1
        )

        second = record_failure(
            first, OTHER_DIGEST, "boot-2", "different failure", now=2
        )

        self.assertEqual(second.failures, 1)
        self.assertEqual(second.current_digest, OTHER_DIGEST)

    def test_quarantine_can_be_cleared_explicitly(self):
        state = BootHealthState()
        for index in range(3):
            state = record_failure(
                state, DIGEST, f"boot-{index}", "failed", now=index
            )

        cleared = clear_quarantine(state, DIGEST, now=10)

        self.assertNotIn(DIGEST, cleared.quarantined)
        self.assertEqual(cleared.status, "unhealthy")


class RolloutPolicyTests(unittest.TestCase):
    def test_image_tags_map_to_release_rings(self):
        self.assertEqual(image_ring("ghcr.io/example/kyth:latest"), "stable")
        self.assertEqual(image_ring("ghcr.io/example/kyth:testing-cachy"), "testing")
        self.assertEqual(image_ring("ghcr.io/example/kyth:canary@sha256:abc"), "canary")

    def test_follow_image_accepts_current_channel(self):
        self.assertIsNone(
            rollout_policy_reason(
                "ghcr.io/example/kyth:testing", "follow-image"
            )
        )

    def test_explicit_ring_rejects_accidental_channel_drift(self):
        reason = rollout_policy_reason(
            "ghcr.io/example/kyth:testing", "stable"
        )

        self.assertIn("testing ring", reason)
        self.assertIn("configured for stable", reason)

    def test_invalid_ring_fails_closed(self):
        self.assertIn(
            "invalid rollout ring",
            rollout_policy_reason("ghcr.io/example/kyth:latest", "nightly"),
        )

    def test_explicit_ring_rejects_untagged_reference(self):
        self.assertIn(
            "cannot determine rollout ring",
            rollout_policy_reason(
                "ghcr.io/example/kyth@sha256:abc", "stable"
            ),
        )


class RequiredHealthCheckTests(unittest.TestCase):
    # Runtime assertions shell out to systemctl and poll for the display stack;
    # they are injected here so these stay tree-completeness tests. Their own
    # behaviour is covered by tests/test_kyth_boot_runtime.py.
    @staticmethod
    def _runtime(*checks):
        return lambda: checks

    def test_complete_immutable_deployment_passes(self):
        status = {
            "status": {"booted": {"image": {"imageDigest": DIGEST}}}
        }

        checks = required_checks(
            status_data=status,
            os_release='NAME="KythOS"\nID="kythos"\n',
            path_exists=lambda _path: True,
            kernel_release="6.0-fixture",
            runtime_probe=self._runtime(
                RuntimeCheck("Graphical session", True, "graphical.target active")
            ),
        )

        self.assertTrue(all(check.passed for check in checks))

    def test_missing_image_component_fails(self):
        missing = "/usr/bin/plasmashell"

        checks = required_checks(
            status_data={
                "status": {"booted": {"image": {"imageDigest": DIGEST}}}
            },
            os_release="ID=kythos\n",
            path_exists=lambda path: str(path) != missing,
            kernel_release="6.0-fixture",
            runtime_probe=self._runtime(
                RuntimeCheck("Graphical session", True, "graphical.target active")
            ),
        )

        plasma = next(check for check in checks if check.name == "Plasma shell")
        self.assertFalse(plasma.passed)

    def test_runtime_failure_fails_the_required_set(self):
        """A complete tree that never reached a desktop must still score red."""
        checks = required_checks(
            status_data={
                "status": {"booted": {"image": {"imageDigest": DIGEST}}}
            },
            os_release="ID=kythos\n",
            path_exists=lambda _path: True,
            kernel_release="6.0-fixture",
            runtime_probe=self._runtime(
                RuntimeCheck(
                    "Display device", False, "no DRM card device — GPU driver did not load"
                )
            ),
        )

        self.assertFalse(all(check.passed for check in checks))
        display = next(check for check in checks if check.name == "Display device")
        self.assertFalse(display.passed)

    def test_real_runtime_probe_is_used_by_default(self):
        """Default path must reach boot_runtime, not silently check nothing."""
        with patch(
            "kyth_shared.system.boot_runtime.runtime_checks",
            return_value=(RuntimeCheck("Critical units", False, "failed: sddm.service"),),
        ):
            checks = required_checks(
                status_data={
                    "status": {"booted": {"image": {"imageDigest": DIGEST}}}
                },
                os_release="ID=kythos\n",
                path_exists=lambda _path: True,
                kernel_release="6.0-fixture",
            )

        units = next(check for check in checks if check.name == "Critical units")
        self.assertFalse(units.passed)


class SafeUpgradeTests(unittest.TestCase):
    def test_quarantined_remote_digest_blocks_bootc(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_path = pathlib.Path(temporary) / "health.json"
            state = BootHealthState()
            for index in range(3):
                state = record_failure(
                    state, DIGEST, f"boot-{index}", "failed", now=index
                )
            write_state(state, state_path)
            status = {
                "status": {
                    "booted": {
                        "image": {
                            "reference": "ghcr.io/example/kyth:testing",
                            "imageDigest": OTHER_DIGEST,
                        }
                    }
                }
            }
            with (
                patch.object(safe_upgrade.os, "geteuid", return_value=0),
                patch.object(safe_upgrade, "fetch_status_data", return_value=status),
                patch.object(safe_upgrade, "remote_digest_for_ref", return_value=DIGEST),
                patch.object(safe_upgrade, "run") as run,
            ):
                result = safe_upgrade.upgrade(
                    state_path=state_path,
                    config_path=pathlib.Path(temporary) / "missing.toml",
                )

            self.assertEqual(result, 5)
            run.assert_not_called()

    def test_allowed_upgrade_records_pending_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_path = pathlib.Path(temporary) / "health.json"
            status = {
                "status": {
                    "booted": {
                        "image": {
                            "reference": "ghcr.io/example/kyth:testing",
                            "imageDigest": OTHER_DIGEST,
                        }
                    }
                }
            }
            completed = subprocess.CompletedProcess(["bootc", "upgrade"], 0)
            with (
                patch.object(safe_upgrade.os, "geteuid", return_value=0),
                patch.object(safe_upgrade, "fetch_status_data", return_value=status),
                patch.object(safe_upgrade, "remote_digest_for_ref", return_value=DIGEST),
                patch.object(safe_upgrade, "run", return_value=completed) as run,
            ):
                result = safe_upgrade.upgrade(
                    state_path=state_path,
                    config_path=pathlib.Path(temporary) / "missing.toml",
                )

            self.assertEqual(result, 0)
            run.assert_called_once_with(["bootc", "upgrade"], check=False)
            self.assertEqual(read_state(state_path).pending_digest, DIGEST)


class BootHealthPackagingTests(unittest.TestCase):
    def test_offline_desktops_do_not_use_required_dns_health_check(self):
        package_script = (
            ROOT / "build_files/scripts/packages/22-greenboot.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("dnf5 install -y greenboot", package_script)
        install_line = next(
            line for line in package_script.splitlines()
            if line.startswith("dnf5 install")
        )
        self.assertNotIn("greenboot-default-health-checks", install_line)

    def test_greenboot_hooks_are_installed_in_lifecycle_directories(self):
        install = (
            ROOT / "build_files/scripts/branding/35-diagnostic-script-installs.sh"
        ).read_text(encoding="utf-8")
        for directory in (
            "/etc/greenboot/check/required.d",
            "/etc/greenboot/green.d",
            "/etc/greenboot/red.d",
        ):
            self.assertIn(directory, install)

    def test_greenboot_hooks_parse_and_use_shared_cli(self):
        for name in (
            "kyth-greenboot-required",
            "kyth-greenboot-success",
            "kyth-greenboot-failure",
        ):
            text = (ROOT / "build_files" / name).read_text(encoding="utf-8")
            self.assertIn("/usr/bin/kyth-boot-health", text)

    def test_invariants_hold_after_all_state_transitions(self):
        """S7 exhaustive: every public state transition preserves invariants & round-trip."""
        states: list[BootHealthState] = [BootHealthState()]
        states.append(record_staged(states[-1], DIGEST, rollout_ring="testing", now=1))
        states.append(record_failure(states[-1], DIGEST, "boot-1", "failed", now=2))
        states.append(record_failure(states[-1], DIGEST, "boot-2", "failed", now=3))
        states.append(record_failure(states[-1], DIGEST, "boot-3", "failed", now=4))  # quarantined
        states.append(mark_healthy(states[-1], DIGEST, now=5))
        states.append(clear_quarantine(states[-1], DIGEST, now=6))
        states.append(record_failure(states[-1], OTHER_DIGEST, "boot-9", "failed", now=7))
        for idx, st in enumerate(states):
            with self.subTest(idx=idx, status=st.status):
                self.assertEqual(st.invariants(), [], f"invariants failed at step {idx}: {st.invariants()}")
                restored = BootHealthState.from_dict(st.to_dict())
                self.assertEqual(restored, st)
                self.assertEqual(restored.invariants(), [])

    def test_invariants_catch_corrupt_quarantine(self):
        corrupt = BootHealthState(
            status="healthy",
            last_healthy_digest="",  # violates healthy invariant
            failures=-1,
            quarantined={
                DIGEST: QuarantineRecord(digest=OTHER_DIGEST, failures=1, reason="x", first_failed_at=1, last_failed_at=2)
            },
        )
        errs = corrupt.invariants()
        self.assertIn("failures<0", errs)
        self.assertIn("healthy but last_healthy_digest empty", errs)
        self.assertTrue(any("key" in e and "!=" in e for e in errs))
        self.assertTrue(any("failures 1 < threshold" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
