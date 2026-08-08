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

        def fake_stream(argv, _log, **_kwargs):
            calls.append(argv)

        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "_stream", side_effect=fake_stream):
            fsresize._shrink_ntfs("/dev/sda1", 100 * 1024**3, lambda _m: None)

        size_arg = str(100 * 1024**3)
        self.assertEqual(calls, [
            ["ntfsresize", "--check", "/dev/sda1"],
            ["ntfsresize", "--info", "/dev/sda1"],
            ["ntfsresize", "--no-action", "--size", size_arg, "/dev/sda1"],
            ["ntfsresize", "--size", size_arg, "/dev/sda1"],
        ])

    def test_check_failure_mentions_hibernation_and_fast_startup(self):
        def fake_stream(argv, _log, *, error_factory=None, **_kwargs):
            if argv[:2] == ["ntfsresize", "--check"]:
                raise error_factory(1, [], argv)

        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "_stream", side_effect=fake_stream):
            with self.assertRaisesRegex(RuntimeError, "Fast Startup"):
                fsresize._shrink_ntfs("/dev/sda1", 100 * 1024**3, lambda _m: None)

    def test_dry_run_too_small_gives_specific_message(self):
        def fake_stream(argv, _log, *, error_factory=None, **_kwargs):
            if "--no-action" in argv:
                raise error_factory(1, ["Error: Volume too small"], argv)

        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "_stream", side_effect=fake_stream):
            with self.assertRaisesRegex(RuntimeError, "Not enough free space"):
                fsresize._shrink_ntfs("/dev/sda1", 100 * 1024**3, lambda _m: None)

    def test_dry_run_immovable_files_gives_specific_message(self):
        def fake_stream(argv, _log, *, error_factory=None, **_kwargs):
            if "--no-action" in argv:
                raise error_factory(1, ["Sorry, this partition has immovable files"], argv)

        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "_stream", side_effect=fake_stream):
            with self.assertRaisesRegex(RuntimeError, "Immovable files"):
                fsresize._shrink_ntfs("/dev/sda1", 100 * 1024**3, lambda _m: None)

    def test_real_shrink_sends_y_confirmation_on_stdin(self):
        captured = {}

        def fake_stream(argv, _log, **kwargs):
            if argv == ["ntfsresize", "--size", str(100 * 1024**3), "/dev/sda1"]:
                captured.update(kwargs)

        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "_stream", side_effect=fake_stream):
            fsresize._shrink_ntfs("/dev/sda1", 100 * 1024**3, lambda _m: None)

        self.assertEqual(captured.get("stdin_data"), "y\n")


class ShrinkExtTests(unittest.TestCase):
    """The ext path uses plain run_command for e2fsck (short summary output,
    not worth streaming) and the streamed _stream() helper for resize2fs."""

    def test_uncorrectable_fsck_errors_abort_before_any_resize(self):
        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "run_command", return_value=MagicMock(returncode=4, stdout="uncorrectable")), \
             patch.object(fsresize, "_stream") as mock_stream:
            with self.assertRaisesRegex(RuntimeError, "uncorrectable errors"):
                fsresize._shrink_ext("/dev/sda2", 5 * 1024**3, lambda _m: None)
        mock_stream.assert_not_called()

    def test_corrected_fsck_errors_below_4_still_proceed_to_resize(self):
        # e2fsck exit 1 = "errors corrected" — a normal, successful outcome.
        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "run_command", return_value=MagicMock(returncode=1, stdout="corrected")), \
             patch.object(fsresize, "_stream") as mock_stream:
            fsresize._shrink_ext("/dev/sda2", 5 * 1024**3, lambda _m: None)
        mock_stream.assert_called_once()
        resize_argv = mock_stream.call_args.args[0]
        self.assertEqual(resize_argv[0], "resize2fs")
        self.assertEqual(resize_argv[1], "/dev/sda2")
        self.assertTrue(resize_argv[2].endswith("K"))


class ShrinkBtrfsTests(unittest.TestCase):
    def test_mounts_shrinks_and_always_unmounts_even_on_failure(self):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(argv)
            return MagicMock(returncode=0)

        with patch.object(fsresize, "_require_tools"), \
             patch.object(fsresize, "run_command", side_effect=fake_run), \
             patch.object(fsresize, "_stream", side_effect=RuntimeError("resize failed")), \
             patch.object(fsresize.tempfile, "mkdtemp", return_value="/tmp/kyth-btrfs-resize-test"), \
             patch.object(fsresize.Path, "rmdir"):
            with self.assertRaisesRegex(RuntimeError, "resize failed"):
                fsresize._shrink_btrfs("/dev/sda3", 20 * 1024**3, lambda _m: None)

        # mount happened, and umount was still attempted despite the resize
        # raising — the mount must never be leaked on failure.
        self.assertTrue(any("mount" in c and "/dev/sda3" in c for c in calls))
        self.assertTrue(any("umount" in c for c in calls))


class StreamTests(unittest.TestCase):
    """_stream() is the shared live-output plumbing every shrink path uses —
    exercise it with real (but harmless, allowlisted) subprocesses rather
    than mocking Popen internals."""

    def test_stream_logs_live_output_on_success(self):
        logs = []
        with patch.object(fsresize, "_as_root", side_effect=lambda cmd: cmd):
            fsresize._stream(["echo", "hello from resize"], logs.append, timeout=5)
        self.assertIn("hello from resize", logs)

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
