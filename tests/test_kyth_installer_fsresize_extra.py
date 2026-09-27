"""Extra coverage for fsresize branches missing from main tests."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files/kyth-installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from kyth_installer import fsresize  # noqa: E402


class DryRunFallbackTests(unittest.TestCase):
    def test_generic_dryrun_error_falls_through_to_generic_message(self):
        def fake_stream(payload, _log, *, error_factory=None, **_kwargs):
            if payload["stage"] == "dry_run":
                # no "too small" nor "immovable" -> hits generic branch
                raise error_factory(1, ["unexpected ntfsresize output"], payload)
        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "_stream_typed", side_effect=fake_stream):
            with self.assertRaisesRegex(RuntimeError, "Boot Windows, shrink the volume"):
                fsresize._shrink_ntfs("/dev/sda1", 100 * 1024**3, lambda _m: None)


class PreShrinkGuardTests(unittest.TestCase):
    def test_encryption_warn_status_raises(self):
        def fake_battery(): return None
        warn = MagicMock(status="warn", detail="encryption warn detail")
        with patch.dict("sys.modules", {}):
            with patch("kyth_installer.assurance._battery_check", fake_battery, create=True):
                with patch("kyth_installer.assurance._encryption_check", return_value=warn, create=True):
                    with self.assertRaisesRegex(RuntimeError, "encryption warn detail"):
                        fsresize.shrink_filesystem("/dev/sda1", "ntfs", 10 * 1024**3, lambda _m: None)

    def test_battery_oserror_is_logged_and_ignored(self):
        # OSError from _battery_check hits except (OSError...) debug path 178-180
        def bad_battery():
            raise OSError("battery probe failed")
        with patch("kyth_installer.assurance._battery_check", bad_battery, create=True):
            with patch("kyth_installer.assurance._encryption_check", return_value=None, create=True):
                with patch.object(fsresize, "_shrink_ntfs") as mock:
                    fsresize.shrink_filesystem("/dev/sda1", "ntfs", 10 * 1024**3, lambda _m: None)
                mock.assert_called_once()

    def test_btrfs_rmdir_oserror_is_ignored(self):
        # lines 154-155: rmdir OSError swallowed
        def fake_run(payload, **kwargs):
            return MagicMock(returncode=0)
        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "_run_typed", side_effect=fake_run), \
             patch.object(fsresize, "_stream_typed", return_value=None), \
             patch.object(fsresize.tempfile, "mkdtemp", return_value="/tmp/kyth-btrfs-rmdir-test"), \
             patch.object(fsresize.Path, "rmdir", side_effect=OSError("rmdir failed")):
            # should not raise despite rmdir failure
            fsresize._shrink_btrfs("/dev/sda3", 20 * 1024**3, lambda _m: None)


if __name__ == "__main__":
    unittest.main()
