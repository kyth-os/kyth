import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.user_polish import (
    OperationStatus,
    _run_operation,
    apply_desktop_layout_step,
    apply_foundation,
    apply_places,
    cleanup_autostart,
    should_refresh_pulse_desktop_shortcut,
)


class UserPolishTests(unittest.TestCase):
    def test_foundation_is_idempotent_in_isolated_home(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "kyth_shared.user_polish.shutil.which", return_value=None
        ):
            first = apply_foundation(tmp)
            second = apply_foundation(tmp)

            self.assertTrue((Path(tmp) / "Games/.directory").is_file())
            self.assertTrue((Path(tmp) / "Templates/Plain Text.txt").is_file())
            self.assertEqual(first[0].status, OperationStatus.APPLIED)
            self.assertEqual(second[0].status, OperationStatus.APPLIED)

    def test_partial_failure_does_not_stop_later_operations(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "kyth_shared.user_polish._ensure_user_folders",
            side_effect=OSError("read only"),
        ), mock.patch(
            "kyth_shared.user_polish.shutil.which", return_value=None
        ):
            results = apply_foundation(tmp)

        self.assertEqual(results[0].status, OperationStatus.FAILED)
        self.assertEqual(results[1].status, OperationStatus.UNAVAILABLE)
        self.assertEqual(results[2].status, OperationStatus.UNAVAILABLE)

    def test_places_are_xml_aware_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            places = Path(tmp) / ".local/share/user-places.xbel"
            places.parent.mkdir(parents=True)
            places.write_text(
                '<?xml version="1.0"?><xbel version="1.0">'
                '<bookmark href="smb://server/share"><title>Work</title></bookmark>'
                "</xbel>",
                encoding="utf-8",
            )

            first = apply_places(tmp)
            second = apply_places(tmp)
            content = places.read_text(encoding="utf-8")

        self.assertEqual(first.status, OperationStatus.APPLIED)
        self.assertEqual(second.status, OperationStatus.SKIPPED)
        self.assertEqual(content.count('href="smb://server/share"'), 1)
        self.assertEqual(content.count(f'href="file://{tmp}/Downloads"'), 1)
        self.assertEqual(content.count('href="trash:/"'), 1)

    def test_malformed_places_is_a_structured_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            places = Path(tmp) / ".local/share/user-places.xbel"
            places.parent.mkdir(parents=True)
            places.write_text("<xbel>", encoding="utf-8")

            result = _run_operation("places-v1", lambda: apply_places(tmp))

        self.assertEqual(result.status, OperationStatus.FAILED)
        self.assertIn("no element found", result.detail)

    def test_autostart_cleanup_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            autostart = Path(tmp) / ".config/autostart"
            autostart.mkdir(parents=True)
            obsolete = autostart / "kyth-windows-friendly-defaults.desktop"
            current = autostart / "kyth-user-polish.desktop"
            unrelated = autostart / "keep.desktop"
            for path in (obsolete, current, unrelated):
                path.touch()

            first = cleanup_autostart(tmp)
            second = cleanup_autostart(tmp)

            self.assertEqual(first.status, OperationStatus.APPLIED)
            self.assertEqual(second.status, OperationStatus.SKIPPED)
            self.assertTrue(unrelated.exists())

    def test_layout_step_skips_when_helper_missing(self):
        with mock.patch("kyth_shared.user_polish.shutil.which", return_value=None):
            result = apply_desktop_layout_step(force=False, first_polish=True)
        self.assertEqual(result.status, OperationStatus.UNAVAILABLE)

    def test_layout_step_failure_is_not_success(self):
        failed = mock.Mock(returncode=1)
        with mock.patch(
            "kyth_shared.user_polish.shutil.which",
            return_value="/usr/bin/kyth-apply-desktop-layout",
        ), mock.patch("kyth_shared.user_polish.run_command", return_value=failed):
            result = apply_desktop_layout_step(force=False, first_polish=True)
        self.assertEqual(result.status, OperationStatus.FAILED)
        self.assertIn("exit 1", result.detail)

    def test_layout_step_skips_when_already_polished(self):
        with mock.patch(
            "kyth_shared.user_polish.shutil.which",
            return_value="/usr/bin/kyth-apply-desktop-layout",
        ), mock.patch("kyth_shared.user_polish.run_command") as run:
            result = apply_desktop_layout_step(force=False, first_polish=False)
        self.assertEqual(result.status, OperationStatus.SKIPPED)
        run.assert_not_called()

    def test_stale_system_hub_desktop_shortcut_is_refreshed(self):
        stale = "[Desktop Entry]\nName=KythOS System Hub\nComment=Helper\nExec=/usr/bin/kyth-welcome-launch\n"
        shipped = "[Desktop Entry]\nName=Kyth Pulse\nGenericName=System Hub\nComment=Health, games, apps, and this PC\nExec=/usr/bin/kyth-welcome-launch\n"
        self.assertTrue(should_refresh_pulse_desktop_shortcut(stale, shipped))
        self.assertFalse(should_refresh_pulse_desktop_shortcut(shipped, shipped))
        self.assertFalse(should_refresh_pulse_desktop_shortcut("", shipped))
        self.assertFalse(
            should_refresh_pulse_desktop_shortcut(
                "[Desktop Entry]\nName=Notes\nExec=kate\n",
                shipped,
            )
        )


if __name__ == "__main__":
    unittest.main()
