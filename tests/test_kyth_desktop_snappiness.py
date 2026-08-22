"""Guards for desktop snappiness: no GUI-thread probes, coalesced cache, sentinels."""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.session import default_flatpaks_done, default_flatpaks_sentinel  # noqa: E402
from kyth_shared.system import probe as probe_mod  # noqa: E402
from kyth_welcome.services import welcome  # noqa: E402


class DefaultFlatpaksSentinelTests(unittest.TestCase):
    def test_picks_newest_versioned_stamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "default-flatpaks-v10-done").touch()
            (root / "default-flatpaks-v12-done").touch()
            (root / "unrelated").touch()
            sentinel = default_flatpaks_sentinel(root)
            self.assertIsNotNone(sentinel)
            self.assertEqual(sentinel.name, "default-flatpaks-v12-done")
            self.assertTrue(default_flatpaks_done(root))

    def test_missing_dir_is_not_done(self) -> None:
        self.assertFalse(default_flatpaks_done(pathlib.Path("/no/such/kyth-flatpaks-dir")))
        self.assertIsNone(default_flatpaks_sentinel(pathlib.Path("/no/such/kyth-flatpaks-dir")))


class FirstWeekChecklistTests(unittest.TestCase):
    def test_gather_uses_current_sentinel_and_helpers(self) -> None:
        with (
            mock.patch("kyth_shared.session.default_flatpaks_done", return_value=True),
            mock.patch("kyth_welcome.services.welcome.browser_integration_native_ready", return_value=True),
            mock.patch("kyth_welcome.services.welcome.controller_seen", return_value=False),
            mock.patch("kyth_welcome.services.welcome.kdeconnect_configured", return_value=False),
            mock.patch("kyth_welcome.services.welcome.cloud_storage_configured", return_value=True),
            mock.patch("kyth_welcome.services.welcome.printer_configured", return_value=False),
            mock.patch("kyth_welcome.services.flatpak.is_installed", side_effect=lambda app_id: app_id.endswith("Steam")),
            mock.patch("kyth_welcome.services.bootc.has_rollback_deployment", return_value=True),
        ):
            flags = welcome.gather_first_week_checklist()
        self.assertEqual(len(flags), len(welcome.FIRST_WEEK_ITEMS))
        self.assertEqual(
            flags,
            [True, False, True, True, False, False, True, False, True],
        )

    def test_browser_integration_prefers_host_path(self) -> None:
        with (
            mock.patch("kyth_welcome.services.welcome.path_exists", return_value=True),
            mock.patch("kyth_welcome.services.welcome.run_command") as run,
        ):
            self.assertTrue(welcome.browser_integration_native_ready())
            run.assert_not_called()


class ProbeSingleflightTests(unittest.TestCase):
    def test_concurrent_misses_share_one_fetch(self) -> None:
        svc = probe_mod.ProbeService()
        calls = {"n": 0}
        started = threading.Event()
        release = threading.Event()

        def fetch():
            calls["n"] += 1
            started.set()
            self.assertTrue(release.wait(timeout=2))
            return "once"

        results: list[str] = []

        def worker():
            results.append(svc.cached("sf-test-key", 30.0, fetch))

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        self.assertTrue(started.wait(timeout=2))
        t2.start()
        deadline = time.monotonic() + 2
        attached = False
        while time.monotonic() < deadline:
            with svc._lock:
                if "sf-test-key" in svc._inflight:
                    attached = True
                    break
            time.sleep(0.01)
        self.assertTrue(attached)
        release.set()
        t1.join(timeout=2)
        t2.join(timeout=2)
        self.assertFalse(t1.is_alive())
        self.assertFalse(t2.is_alive())
        self.assertEqual(calls["n"], 1)
        self.assertEqual(results, ["once", "once"])


class WaitForDisplaySetupTests(unittest.TestCase):
    def test_returns_immediately_when_helper_is_not_running(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from kyth_welcome.core_base import wait_for_display_setup
        except Exception as exc:  # noqa: BLE001 — Qt may be missing on this runner
            raise unittest.SkipTest(f"Qt not available: {exc}") from exc

        with (
            mock.patch("kyth_welcome.core_base.run_command", return_value=mock.Mock(returncode=1, stdout="")) as run,
            mock.patch("kyth_welcome.core_base.time.sleep") as slept,
            mock.patch("os.path.exists", return_value=True),
        ):
            wait_for_display_setup(timeout=8.0, interval=0.25)
        run.assert_called()
        slept.assert_not_called()


class AppstreamCatalogGuiTests(unittest.TestCase):
    def test_cold_catalog_does_not_parse_xml(self) -> None:
        try:
            from kyth_welcome.page_software_flatpak._catalog import _CatalogMixin
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"Qt not available: {exc}") from exc

        class Harness(_CatalogMixin):
            def __init__(self):
                self._fp_appstream_cache = None

        harness = Harness()
        self.assertEqual(harness._fp_appstream_catalog(), {})
        harness._fp_appstream_cache = {"com.example.App": {"name": "Example"}}
        self.assertEqual(harness._fp_appstream_catalog()["com.example.App"]["name"], "Example")


class SessionDefaultsTests(unittest.TestCase):
    def test_firstboot_status_default_delay_is_short(self) -> None:
        import inspect

        from kyth_shared.session import check_firstboot_app_status

        delay = inspect.signature(check_firstboot_app_status).parameters["delay"].default
        self.assertLessEqual(delay, 2)


if __name__ == "__main__":
    unittest.main()
