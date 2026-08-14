import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer.context import InstallerContext  # noqa: E402
from kyth_installer.post_routes import PostRouteService  # noqa: E402


class PostRouteCoverageTests(unittest.TestCase):
    def setUp(self):
        self.context = InstallerContext()
        self.routes = PostRouteService(self.context)

    def test_dispatch_rejects_unknown_and_locked_partition_routes(self):
        self.assertEqual(self.routes.dispatch("missing", {}).status, 404)
        self.context.install_lock.acquire()
        try:
            response = self.routes.dispatch("new_table", {})
        finally:
            self.context.install_lock.release()
        self.assertEqual(response.status, 409)

    def test_route_status_translation(self):
        cases = (
            ("new_table", "new_table", {"ok": True}, 200),
            ("new_table", "new_table", {"ok": False}, 400),
            ("commit_partitions", "commit_partitions", {"ok": False, "errors": []}, 400),
            ("commit_partitions", "commit_partitions", {"ok": False}, 500),
            ("rollback_partitions", "rollback_partitions", {"ok": False}, 500),
            ("cancel", "cancel_install", {"ok": False}, 409),
            ("reboot", "reboot", {"ok": False}, 500),
        )
        for route, method, result, status in cases:
            with self.subTest(route=route, result=result):
                with mock.patch.object(self.routes.installer_service, method, return_value=result):
                    self.assertEqual(self.routes.dispatch(route, {}).status, status)

    def test_start_maps_success_conflict_and_validation_failure(self):
        for result, status in (
            ({"started": True}, 200),
            ({"started": False, "message": "An installation is already running."}, 409),
            ({"started": False, "message": "bad request"}, 400),
        ):
            with mock.patch.object(
                self.routes.installer_service, "start_install", return_value=result
            ):
                self.assertEqual(self.routes.start({}).status, status)

    def test_rescue_logs_copies_only_safe_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            mount = Path(tmp) / "usb"
            mount.mkdir()
            log_file = Path(tmp) / "install.log"
            log_file.write_text("log")
            missing = Path(tmp) / "missing"
            run = mock.Mock()
            with (
                mock.patch("kyth_installer.config.LOG_FILE", log_file),
                mock.patch("kyth_installer.config.TRANSACTION_FILE", missing),
                mock.patch("kyth_installer.config.FAILURE_SUMMARY_FILE", missing),
                mock.patch("kyth_installer.runner.run_command", run),
                mock.patch("kyth_installer.system._as_root", side_effect=lambda argv: argv),
            ):
                response = self.routes.rescue_logs_to_usb({"usb_mount": str(mount)})
        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload["copied"], ["install.log"])

    def test_rescue_logs_reports_missing_media_empty_logs_and_copy_failure(self):
        self.assertEqual(
            self.routes.rescue_logs_to_usb({"usb_mount": "/definitely/missing"}).status, 400
        )
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            with (
                mock.patch("kyth_installer.config.LOG_FILE", missing),
                mock.patch("kyth_installer.config.TRANSACTION_FILE", missing),
                mock.patch("kyth_installer.config.FAILURE_SUMMARY_FILE", missing),
                mock.patch("kyth_installer.runner.run_command"),
            ):
                self.assertEqual(
                    self.routes.rescue_logs_to_usb({"usb_mount": tmp}).status, 500
                )
            with mock.patch(
                "kyth_installer.runner.run_command", side_effect=RuntimeError("copy failed")
            ):
                response = self.routes.rescue_logs_to_usb({"usb_mount": tmp})
            self.assertEqual(response.status, 500)
            self.assertIn("copy failed", response.payload["message"])

    def test_rescue_logs_auto_detect_covers_rglob_and_findmnt_branches(self):
        # success: rglob finds USB, findmnt confirms it, copy succeeds
        with tempfile.TemporaryDirectory() as tmp:
            mount = Path(tmp) / "usb"
            mount.mkdir()
            log_file = Path(tmp) / "install.log"
            log_file.write_text("log")
            fake_usb = Path("/run/media/user/USB")
            mock_path_instance = mock.MagicMock()
            mock_path_instance.rglob.return_value = [fake_usb]
            # pathlib.Path("/run/media") returns mock_path_instance
            def fake_path(arg):
                if arg == "/run/media":
                    return mock_path_instance
                return Path(arg)

            mock_run = mock.Mock(return_value=mock.Mock(returncode=0))
            with (
                mock.patch("pathlib.Path", side_effect=fake_path),
                mock.patch("kyth_installer.runner.run_command", mock_run),
                mock.patch("kyth_installer.system._as_root", side_effect=lambda argv: argv),
                mock.patch("kyth_installer.config.LOG_FILE", log_file),
                mock.patch("kyth_installer.config.TRANSACTION_FILE", Path(tmp) / "missing"),
                mock.patch("kyth_installer.config.FAILURE_SUMMARY_FILE", Path(tmp) / "missing"),
                mock.patch("os.path.isdir", return_value=True),
            ):
                # need to also patch the local Path import inside function - pathlib.Path is already patched
                # provide mount via auto-detect: body has no usb_mount
                response = self.routes.rescue_logs_to_usb({})
                self.assertEqual(response.status, 200)
                mock_run.assert_any_call(["findmnt", "-n", str(fake_usb)], capture_output=True, timeout=3)

        # per-item exception is swallowed and next candidate is tried
        with tempfile.TemporaryDirectory() as tmp:
            candidates = [Path("/run/media/a"), Path("/run/media/b")]
            mock_path_instance = mock.MagicMock()
            mock_path_instance.rglob.return_value = candidates

            def fake_path2(arg):
                if arg == "/run/media":
                    return mock_path_instance
                return Path(arg)

            calls = []

            def run_side_effect(argv, **kwargs):
                calls.append(argv)
                if argv[0] == "findmnt":
                    if str(candidates[0]) in argv:
                        raise RuntimeError("findmnt boom")
                    return mock.Mock(returncode=0)
                return mock.Mock(returncode=0)

            log_file = Path(tmp) / "install.log"
            log_file.write_text("log")
            with (
                mock.patch("pathlib.Path", side_effect=fake_path2),
                mock.patch("kyth_installer.runner.run_command", side_effect=run_side_effect),
                mock.patch("kyth_installer.system._as_root", side_effect=lambda argv: argv),
                mock.patch("kyth_installer.config.LOG_FILE", log_file),
                mock.patch("kyth_installer.config.TRANSACTION_FILE", Path(tmp) / "missing"),
                mock.patch("kyth_installer.config.FAILURE_SUMMARY_FILE", Path(tmp) / "missing"),
                mock.patch("os.path.isdir", return_value=True),
            ):
                response = self.routes.rescue_logs_to_usb({})
                self.assertEqual(response.status, 200)

        # outer rglob exception is swallowed -> 400 (no USB found)
        mock_path_instance = mock.MagicMock()
        mock_path_instance.rglob.side_effect = OSError("rglob failed")

        def fake_path3(arg):
            if arg == "/run/media":
                return mock_path_instance
            return Path(arg)

        with mock.patch("pathlib.Path", side_effect=fake_path3), mock.patch("os.path.isdir", return_value=False):
            response = self.routes.rescue_logs_to_usb({})
            self.assertEqual(response.status, 400)
            self.assertIn("No USB", response.payload["message"])

        # findmnt returns non-zero for all candidates -> 400
        mock_path_instance = mock.MagicMock()
        mock_path_instance.rglob.return_value = [Path("/run/media/x")]

        def fake_path4(arg):
            if arg == "/run/media":
                return mock_path_instance
            return Path(arg)

        with (
            mock.patch("pathlib.Path", side_effect=fake_path4),
            mock.patch("kyth_installer.runner.run_command", return_value=mock.Mock(returncode=1)),
            mock.patch("os.path.isdir", return_value=False),
        ):
            response = self.routes.rescue_logs_to_usb({})
            self.assertEqual(response.status, 400)


if __name__ == "__main__":
    unittest.main()
