import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files/kyth-installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from kyth_installer import fsresize  # noqa: E402


class ShrinkFilesystemDispatchTests(unittest.TestCase):
    """shrink_filesystem() must route to the right filesystem-specific
    shrink path — or refuse outright — before any partition boundary change
    happens. Getting this dispatch wrong silently corrupts data."""

    def test_ntfs_dispatches_to_shrink_ntfs(self):
        with patch.object(fsresize, "_shrink_ntfs") as mock_shrink:
            fsresize.shrink_filesystem("/dev/sda1", "ntfs", 10 * 1024**3, lambda _m: None)
        mock_shrink.assert_called_once_with("/dev/sda1", 10 * 1024**3, unittest.mock.ANY)

    def test_ntfs3_dispatches_to_shrink_ntfs(self):
        with patch.object(fsresize, "_shrink_ntfs") as mock_shrink:
            fsresize.shrink_filesystem("/dev/sda1", "NTFS3", 10 * 1024**3, lambda _m: None)
        mock_shrink.assert_called_once()

    def test_ext4_dispatches_to_shrink_ext(self):
        with patch.object(fsresize, "_shrink_ext") as mock_shrink:
            fsresize.shrink_filesystem("/dev/sda2", "ext4", 5 * 1024**3, lambda _m: None)
        mock_shrink.assert_called_once_with("/dev/sda2", 5 * 1024**3, unittest.mock.ANY)

    def test_ext2_and_ext3_also_dispatch_to_shrink_ext(self):
        for fstype in ("ext2", "ext3"):
            with self.subTest(fstype=fstype), patch.object(fsresize, "_shrink_ext") as mock_shrink:
                fsresize.shrink_filesystem("/dev/sda2", fstype, 5 * 1024**3, lambda _m: None)
            mock_shrink.assert_called_once()

    def test_btrfs_dispatches_to_shrink_btrfs(self):
        with patch.object(fsresize, "_shrink_btrfs") as mock_shrink:
            fsresize.shrink_filesystem("/dev/sda3", "btrfs", 20 * 1024**3, lambda _m: None)
        mock_shrink.assert_called_once_with("/dev/sda3", 20 * 1024**3, unittest.mock.ANY)

    def test_bitlocker_is_rejected_with_a_targeted_message(self):
        with patch.object(fsresize, "_shrink_ntfs") as mock_shrink:
            with self.assertRaisesRegex(RuntimeError, "BitLocker"):
                fsresize.shrink_filesystem("/dev/sda1", "BitLocker", 10 * 1024**3, lambda _m: None)
        mock_shrink.assert_not_called()

    def test_xfs_is_rejected_it_cannot_shrink(self):
        with self.assertRaisesRegex(RuntimeError, "not supported"):
            fsresize.shrink_filesystem("/dev/sda1", "xfs", 10 * 1024**3, lambda _m: None)

    def test_unknown_fstype_is_rejected_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, "not supported"):
            fsresize.shrink_filesystem("/dev/sda1", "reiserfs", 10 * 1024**3, lambda _m: None)

    def test_empty_fstype_is_rejected_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, "not supported"):
            fsresize.shrink_filesystem("/dev/sda1", "", 10 * 1024**3, lambda _m: None)

    def test_encryption_warn_on_parent_disk_blocks_shrink(self):
        from kyth_installer.assurance import AssuranceCheck

        warn = AssuranceCheck("encryption", "warn", "Partition /dev/sda1 appears BitLocker-locked")
        with patch("kyth_installer.disk._parent_disk", return_value="/dev/sda"), \
             patch("kyth_installer.assurance._encryption_check", return_value=warn), \
             patch.object(fsresize, "_shrink_ntfs") as mock_shrink:
            with self.assertRaisesRegex(RuntimeError, "BitLocker"):
                fsresize.shrink_filesystem("/dev/sda1", "ntfs", 10 * 1024**3, lambda _m: None)
        mock_shrink.assert_not_called()


class RequireToolsTests(unittest.TestCase):
    def test_raises_listing_every_missing_tool(self):
        with patch.object(fsresize.shutil, "which", side_effect=lambda t: None if t == "resize2fs" else "/usr/sbin/" + t):
            with self.assertRaisesRegex(RuntimeError, "resize2fs"):
                fsresize._require_tools("e2fsck", "resize2fs")

    def test_passes_when_all_tools_present(self):
        with patch.object(fsresize.shutil, "which", return_value="/usr/bin/tool"):
            fsresize._require_tools("ntfsresize")  # does not raise


class ShrinkNtfsTests(unittest.TestCase):
    """The NTFS path runs check -> info -> dry-run -> real shrink, in that
    order, and translates dry-run failure text into specific guidance."""

    def test_full_sequence_runs_in_order_with_correct_argv(self):
        calls = []

        def fake_stream(payload, _log, **_kwargs):
            calls.append(payload)

        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "_stream_typed", side_effect=fake_stream):
            fsresize._shrink_ntfs("/dev/sda1", 100 * 1024**3, lambda _m: None)

        self.assertEqual(calls, [
            {"operation": "filesystem_resize", "device": "/dev/sda1", "fs": "ntfs",
             "new_size_bytes": 100 * 1024**3, "stage": "check"},
            {"operation": "filesystem_resize", "device": "/dev/sda1", "fs": "ntfs",
             "new_size_bytes": 100 * 1024**3, "stage": "info"},
            {"operation": "filesystem_resize", "device": "/dev/sda1", "fs": "ntfs",
             "new_size_bytes": 100 * 1024**3, "stage": "dry_run"},
            {"operation": "filesystem_resize", "device": "/dev/sda1", "fs": "ntfs",
             "new_size_bytes": 100 * 1024**3, "stage": "resize"},
        ])

    def test_check_failure_mentions_hibernation_and_fast_startup(self):
        def fake_stream(payload, _log, *, error_factory=None, **_kwargs):
            if payload["stage"] == "check":
                raise error_factory(1, [], payload)

        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "_stream_typed", side_effect=fake_stream):
            with self.assertRaisesRegex(RuntimeError, "Fast Startup"):
                fsresize._shrink_ntfs("/dev/sda1", 100 * 1024**3, lambda _m: None)

    def test_dry_run_too_small_gives_specific_message(self):
        def fake_stream(payload, _log, *, error_factory=None, **_kwargs):
            if payload["stage"] == "dry_run":
                raise error_factory(1, ["Error: Volume too small"], payload)

        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "_stream_typed", side_effect=fake_stream):
            with self.assertRaisesRegex(RuntimeError, "Not enough free space"):
                fsresize._shrink_ntfs("/dev/sda1", 100 * 1024**3, lambda _m: None)

    def test_dry_run_immovable_files_gives_specific_message(self):
        def fake_stream(payload, _log, *, error_factory=None, **_kwargs):
            if payload["stage"] == "dry_run":
                raise error_factory(1, ["Sorry, this partition has immovable files"], payload)

        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "_stream_typed", side_effect=fake_stream):
            with self.assertRaisesRegex(RuntimeError, "Immovable files"):
                fsresize._shrink_ntfs("/dev/sda1", 100 * 1024**3, lambda _m: None)

    def test_real_shrink_leaves_confirmation_to_rust_helper(self):
        captured = {}

        def fake_stream(payload, _log, **kwargs):
            if payload["stage"] == "resize":
                captured.update(payload=payload, kwargs=kwargs)

        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "_stream_typed", side_effect=fake_stream):
            fsresize._shrink_ntfs("/dev/sda1", 100 * 1024**3, lambda _m: None)

        self.assertEqual(captured["payload"]["stage"], "resize")
        self.assertNotIn("stdin_data", captured["kwargs"])


class ShrinkExtTests(unittest.TestCase):
    """The ext path uses the typed helper for check and resize stages."""

    def test_uncorrectable_fsck_errors_abort_before_any_resize(self):
        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "_run_typed", return_value=MagicMock(returncode=4, stdout="uncorrectable")), \
             patch.object(fsresize, "_stream_typed") as mock_stream:
            with self.assertRaisesRegex(RuntimeError, "uncorrectable errors"):
                fsresize._shrink_ext("/dev/sda2", 5 * 1024**3, lambda _m: None)
        mock_stream.assert_not_called()

    def test_corrected_fsck_errors_below_4_still_proceed_to_resize(self):
        # e2fsck exit 1 = "errors corrected" — a normal, successful outcome.
        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "_run_typed", return_value=MagicMock(returncode=1, stdout="corrected")), \
             patch.object(fsresize, "_stream_typed") as mock_stream:
            fsresize._shrink_ext("/dev/sda2", 5 * 1024**3, lambda _m: None)
        mock_stream.assert_called_once()
        resize_payload = mock_stream.call_args.args[0]
        self.assertEqual(resize_payload["operation"], "filesystem_resize")
        self.assertEqual(resize_payload["device"], "/dev/sda2")
        self.assertEqual(resize_payload["fs"], "ext4")
        self.assertEqual(resize_payload["stage"], "resize")


class ShrinkBtrfsTests(unittest.TestCase):
    def test_mounts_shrinks_and_always_unmounts_even_on_failure(self):
        calls = []

        def fake_run(payload, **kwargs):
            calls.append(payload)
            return MagicMock(returncode=0)

        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "_run_typed", side_effect=fake_run), \
             patch.object(fsresize, "_stream_typed", side_effect=RuntimeError("resize failed")), \
             patch.object(fsresize.tempfile, "mkdtemp", return_value="/tmp/kyth-btrfs-resize-test"), \
             patch.object(fsresize.Path, "rmdir"):
            with self.assertRaisesRegex(RuntimeError, "resize failed"):
                fsresize._shrink_btrfs("/dev/sda3", 20 * 1024**3, lambda _m: None)

        # mount happened, and umount was still attempted despite the resize
        # raising — the mount must never be leaked on failure.
        self.assertTrue(any(c["operation"] == "mount_filesystem" and c["device"] == "/dev/sda3" for c in calls))
        self.assertTrue(any(c["operation"] == "unmount_filesystem" for c in calls))


class StreamTests(unittest.TestCase):
    """_stream() is the shared live-output plumbing every shrink path uses —
    exercise it with real (but harmless, allowlisted) subprocesses rather
    than mocking Popen internals."""

    def test_stream_logs_live_output_on_success(self):
        logs = []
        with patch.object(fsresize, "_as_root", side_effect=lambda cmd: cmd):
            fsresize._stream(["echo", "hello from resize"], logs.append, timeout=5)
        self.assertIn("hello from resize", logs)

    def test_typed_stream_wraps_request_for_rust_process_lifecycle(self):
        payload = {
            "operation": "filesystem_resize",
            "device": "/dev/sda1",
            "fs": "ntfs",
            "new_size_bytes": 10 * 1024**3,
            "stage": "resize",
        }
        with patch.object(fsresize, "_stream") as stream:
            fsresize._stream_typed(payload, lambda _message: None)

        self.assertEqual(stream.call_args.args[0], fsresize._STREAM_HELPER)
        self.assertEqual(
            json.loads(stream.call_args.kwargs["stdin_data"]),
            {"kind": "disk", "request": payload},
        )

    def test_stream_pipes_input_to_the_process(self):
        logs = []
        with patch.object(fsresize, "_as_root", side_effect=lambda cmd: cmd):
            fsresize._stream(["cat"], logs.append, stdin_data="confirmed\n", timeout=5)
        self.assertIn("confirmed", logs)

    def test_stream_failure_raises_via_error_factory(self):
        logs = []
        with patch.object(fsresize, "_as_root", side_effect=lambda cmd: cmd):
            with self.assertRaisesRegex(RuntimeError, "custom failure message"):
                fsresize._stream(
                    ["false"], logs.append, timeout=5,
                    error_factory=lambda *_: RuntimeError("custom failure message"),
                )

    def test_stream_failure_without_error_factory_raises_generic_error(self):
        logs = []
        with patch.object(fsresize, "_as_root", side_effect=lambda cmd: cmd):
            with self.assertRaises(RuntimeError):
                fsresize._stream(["false"], logs.append, timeout=5)


if __name__ == "__main__":
    unittest.main()
