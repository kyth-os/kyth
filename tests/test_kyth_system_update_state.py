from __future__ import annotations

import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.system import update_availability as availability  # noqa: E402
from kyth_shared.system import update_status as status  # noqa: E402


class UpdateStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        status.invalidate_update_status()

    def tearDown(self) -> None:
        status.invalidate_update_status()

    @mock.patch("kyth_shared.system.bootc.has_rollback_deployment", return_value=True)
    @mock.patch("kyth_shared.system.bootc.has_staged_update", return_value=True)
    @mock.patch("kyth_shared.system.bootc.bootc_status_data", return_value={"digest": "sha256:old"})
    def test_fetch_reports_available_and_deployment_flags(self, _bootc, _staged, _rollback):
        with mock.patch.object(
            status,
            "probe_cached",
            return_value={"digest": "sha256:new"},
        ):
            result = status.get_update_status(force_refresh=True)

        self.assertEqual(result.check_state, "available")
        self.assertEqual(result.booted, "sha256:old")
        self.assertEqual(result.remote_digest, "sha256:new")
        self.assertTrue(result.staged)
        self.assertTrue(result.rollback)
        self.assertIsNone(result.retry_cmd)

    @mock.patch("kyth_shared.system.bootc.has_rollback_deployment", return_value=False)
    @mock.patch("kyth_shared.system.bootc.has_staged_update", return_value=False)
    @mock.patch("kyth_shared.system.bootc.bootc_status_data", return_value={"digest": "sha256:same"})
    def test_matching_or_missing_remote_digest_is_uptodate(self, _bootc, _staged, _rollback):
        for remote in ({"digest": "sha256:same"}, {}, None):
            with self.subTest(remote=remote), mock.patch.object(
                status, "probe_cached", return_value=remote
            ):
                result = status._fetch_status()
                self.assertEqual(result.check_state, "uptodate")
                self.assertIsNone(result.blocked_reason)

    @mock.patch("kyth_shared.system.bootc.has_rollback_deployment", return_value=False)
    @mock.patch("kyth_shared.system.bootc.has_staged_update", return_value=False)
    @mock.patch("kyth_shared.system.bootc.bootc_status_data", return_value={"digest": "sha256:old"})
    def test_registry_failure_becomes_retryable_terminal_error(self, _bootc, _staged, _rollback):
        with mock.patch.object(status, "probe_cached", side_effect=TimeoutError("registry timed out")):
            result = status._fetch_status()

        self.assertEqual(result.check_state, "error")
        self.assertEqual(result.blocked_reason, "registry timed out")
        self.assertEqual(result.retry_cmd, "bootc upgrade --check")

    @mock.patch("kyth_shared.system.bootc.bootc_status_data", side_effect=OSError("bootc unavailable"))
    def test_outer_probe_failure_becomes_terminal_error(self, _bootc):
        result = status._fetch_status()
        self.assertEqual(result.check_state, "error")
        self.assertEqual(result.detail, "bootc unavailable")
        self.assertEqual(result.blocked_reason, "bootc unavailable")

    def test_ttl_cache_force_refresh_and_invalidation(self):
        first = status.UpdateStatus(check_state="uptodate")
        second = status.UpdateStatus(check_state="available")
        with mock.patch.object(status, "_fetch_status", side_effect=[first, second, first]) as fetch:
            self.assertIs(status.get_update_status(), first)
            self.assertIs(status.get_update_status(), first)
            self.assertIs(status.get_update_status(force_refresh=True), second)
            status.invalidate_update_status()
            self.assertIs(status.get_update_status(), first)
        self.assertEqual(fetch.call_count, 3)


class UpdateAvailabilityTests(unittest.TestCase):
    def _registry_result(self, state="uptodate", detail="Current", manifest=b"manifest"):
        return SimpleNamespace(state=state, detail=detail, manifest_raw=manifest)

    def test_staged_update_takes_precedence_without_registry_call(self):
        with (
            mock.patch.object(availability, "has_staged_update", return_value=True),
            mock.patch.object(availability, "_flatpak_count_cached", return_value=2),
            mock.patch.object(availability, "check_registry_update") as registry,
        ):
            result = availability.collect_availability()

        self.assertEqual(result.state, "staged")
        self.assertTrue(result.staged)
        self.assertEqual(result.flatpak_count, 2)
        registry.assert_not_called()

    def test_staged_probe_failure_falls_through_to_normal_check(self):
        with (
            mock.patch.object(availability, "has_staged_update", side_effect=OSError("bad status")),
            mock.patch("kyth_shared.system.bootc.current_branch", return_value="testing"),
            mock.patch.object(availability, "bootc_status_data", return_value={"digest": "old"}),
            mock.patch.object(
                availability,
                "check_registry_update",
                return_value=self._registry_result(state="available", detail="New image"),
            ),
            mock.patch.object(availability, "_flatpak_count_cached", return_value=0),
        ):
            result = availability.collect_availability()
        self.assertEqual(result.state, "available")

    def test_bootc_failure_is_terminal_error(self):
        with (
            mock.patch.object(availability, "has_staged_update", return_value=False),
            mock.patch("kyth_shared.system.bootc.current_branch", side_effect=OSError("bootc failed")),
        ):
            result = availability.collect_availability()
        self.assertEqual(result.state, "error")
        self.assertEqual(result.detail, "bootc failed")

    def test_registry_error_result_and_exception_are_terminal(self):
        cases = (
            self._registry_result(state="error", detail="registry rejected", manifest=b""),
            TimeoutError("registry timeout"),
        )
        for outcome in cases:
            with (
                self.subTest(outcome=outcome),
                mock.patch.object(availability, "has_staged_update", return_value=False),
                mock.patch("kyth_shared.system.bootc.current_branch", return_value="latest"),
                mock.patch.object(availability, "bootc_status_data", return_value={}),
                mock.patch.object(
                    availability,
                    "check_registry_update",
                    side_effect=outcome if isinstance(outcome, Exception) else None,
                    return_value=None if isinstance(outcome, Exception) else outcome,
                ),
            ):
                result = availability.collect_availability()
            self.assertEqual(result.state, "error")
            self.assertIn("registry", result.detail)

    def test_available_result_preserves_manifest_and_flatpak_count(self):
        with (
            mock.patch.object(availability, "has_staged_update", return_value=False),
            mock.patch("kyth_shared.system.bootc.current_branch", return_value="testing"),
            mock.patch.object(availability, "bootc_status_data", return_value={"digest": "old"}),
            mock.patch.object(
                availability,
                "check_registry_update",
                return_value=self._registry_result(state="available", detail="New image", manifest=b"\xffjson"),
            ) as registry,
            mock.patch.object(availability, "_flatpak_count_cached", return_value=3),
        ):
            result = availability.collect_availability(branch="latest")

        self.assertEqual(result.state, "available")
        self.assertEqual(result.flatpak_count, 3)
        self.assertEqual(result.manifest_raw, "json")
        self.assertFalse(result.staged)
        self.assertEqual(registry.call_args.kwargs["branch"], "latest")

    def test_flatpak_failure_does_not_hide_system_result(self):
        with (
            mock.patch.object(availability, "has_staged_update", return_value=False),
            mock.patch("kyth_shared.system.bootc.current_branch", return_value="latest"),
            mock.patch.object(availability, "bootc_status_data", return_value={}),
            mock.patch.object(
                availability,
                "check_registry_update",
                return_value=self._registry_result(state="uptodate"),
            ),
            mock.patch.object(availability, "_flatpak_count_cached", side_effect=OSError("flatpak failed")),
        ):
            result = availability.collect_availability()
        self.assertEqual(result.state, "uptodate")
        self.assertEqual(result.flatpak_count, 0)
        self.assertEqual(result.flatpak_detail, "flatpak failed")

    def test_uncached_staged_check_skips_flatpak_probe(self):
        with (
            mock.patch.object(availability, "has_staged_update", return_value=True),
            mock.patch.object(availability, "_flatpak_count_cached") as flatpak,
        ):
            result = availability.collect_availability(use_cached=False)
        self.assertEqual(result.flatpak_count, 0)
        flatpak.assert_not_called()

    def test_flatpak_count_combines_successful_scopes_and_ignores_failures(self):
        results = [
            SimpleNamespace(returncode=0, stdout="org.one\norg.two\n"),
            SimpleNamespace(returncode=1, stdout="ignored\n"),
        ]
        with (
            mock.patch("kyth_shared.system.process.run_command", side_effect=results),
            mock.patch.object(availability, "probe_cached", side_effect=lambda _key, _ttl, fetch: fetch()),
        ):
            self.assertEqual(availability._flatpak_count_cached(), 2)

    def test_flatpak_count_returns_none_when_both_scopes_fail(self):
        with (
            mock.patch("kyth_shared.system.process.run_command", return_value=None),
            mock.patch.object(availability, "probe_cached", side_effect=lambda _key, _ttl, fetch: fetch()),
        ):
            self.assertIsNone(availability._flatpak_count_cached())

    def test_availability_view_delegates_all_state(self):
        current = availability.AvailabilityStatus(
            state="available",
            detail="New image",
            flatpak_count=4,
            staged=False,
        )
        expected = object()
        with mock.patch.object(availability, "update_availability_view", return_value=expected) as adapter:
            result = availability.availability_view(current, check_ts="now", staged_ts=None)
        self.assertIs(result, expected)
        adapter.assert_called_once_with(
            staged=False,
            check_state="available",
            flatpak_count=4,
            check_ts="now",
            check_ts_details="New image",
            staged_ts=None,
        )


if __name__ == "__main__":
    unittest.main()
