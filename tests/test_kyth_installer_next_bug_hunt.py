from __future__ import annotations

import contextlib
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer import assurance, execution, fsresize, plan_commit, recovery  # noqa: E402
from kyth_installer.cleanup import unmount_configuration  # noqa: E402
from kyth_installer.context import InstallLifecycle, InstallRequest, InstallerContext  # noqa: E402
from kyth_installer.mountpoint import normalize_manual_mountpoint  # noqa: E402
from kyth_installer.phases.finalize_configure import configure_installed_system  # noqa: E402
from kyth_installer.streaming import StreamingCommandRunner, _kill_tree  # noqa: E402


class InstallerNextBugHuntTests(unittest.TestCase):
    def test_manual_mountpoints_reject_escape_and_fstab_ambiguous_paths(self):
        for value in ("/../../etc", "/data/../etc", "/data//etc", "/data/./etc", "/data with space"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_manual_mountpoint(value)
        self.assertEqual(normalize_manual_mountpoint("/data/"), "/data")
        self.assertEqual(normalize_manual_mountpoint(""), "")

    def test_unexpected_worker_exception_publishes_failed_terminal_state(self):
        context = InstallerContext()

        class ImmediateThread:
            def __init__(self, *, target, daemon):
                self.target = target

            def start(self):
                self.target()

        with mock.patch.object(execution.threading, "Thread", ImmediateThread):
            self.assertTrue(execution.start_installation(
                context, InstallRequest(), lambda _ctx: (_ for _ in ()).throw(TypeError("bad response shape")),
            ))
        self.assertEqual(context.lifecycle, InstallLifecycle.FAILED)
        self.assertIn(
            {"type": "error", "message": "Unexpected installer failure: bad response shape"},
            context.events.events,
        )
        self.assertFalse(context.install_lock.locked())

    def test_worker_terminal_transition_failure_still_publishes_error_and_releases_lock(self):
        context = InstallerContext()

        class ImmediateThread:
            def __init__(self, *, target, daemon):
                self.target = target

            def start(self):
                self.target()

        with mock.patch.object(execution.threading, "Thread", ImmediateThread), \
             mock.patch.object(context, "transition", side_effect=[None, None, RuntimeError("transition failed")]):
            self.assertTrue(execution.start_installation(
                context, InstallRequest(), lambda _ctx: (_ for _ in ()).throw(TypeError("unexpected")),
            ))
        self.assertTrue(any(event.get("type") == "error" for event in context.events.events))
        self.assertFalse(context.install_lock.locked())

    def test_worker_preserves_completed_state_when_late_error_occurs(self):
        context = InstallerContext()

        class ImmediateThread:
            def __init__(self, *, target, daemon):
                self.target = target

            def start(self):
                self.target()

        def finish_then_raise(ctx):
            ctx.transition(InstallLifecycle.DONE)
            raise RuntimeError("late cleanup failure")

        with mock.patch.object(execution.threading, "Thread", ImmediateThread):
            execution.start_installation(context, InstallRequest(), finish_then_raise)
        self.assertEqual(context.lifecycle, InstallLifecycle.DONE)
        self.assertTrue(any(event.get("type") == "error" for event in context.events.events))

    def test_cancel_after_command_exit_does_not_report_a_false_cancel(self):
        runner = StreamingCommandRunner(rx_bytes=lambda: 0, publish=lambda _event: None)
        proc = mock.Mock()
        proc.pid = 1234
        proc.stdout = mock.Mock()
        proc.stdout.fileno.return_value = 9
        proc.poll.return_value = 0
        proc.returncode = 0
        cancelled = threading.Event()
        cancelled.set()
        progress = []
        with mock.patch("kyth_installer.streaming.spawn_command", return_value=proc), \
             mock.patch("kyth_installer.streaming.select.select", return_value=([9], [], [])), \
             mock.patch("kyth_installer.streaming.os.read", return_value=b""):
            runner.run(["echo", "done"], 0, 100, lambda _msg: None, progress.append, cancel_event=cancelled)
        proc.terminate.assert_not_called()
        self.assertEqual(progress[-1], 100)

    def test_cancel_kills_process_group_even_when_leader_exits_on_term(self):
        proc = mock.Mock()
        proc.pid = 4123
        with mock.patch("kyth_installer.streaming.os.killpg") as killpg:
            _kill_tree(proc)
        killpg.assert_called_once_with(4123, mock.ANY)

    def test_ntfs_filesystem_shrink_and_geometry_check_run_inside_disk_lease(self):
        state = {"locked": False}
        def hold(_disk, _log):
            @contextlib.contextmanager
            def entered():
                state["locked"] = True
                try:
                    yield
                finally:
                    state["locked"] = False
            return entered()

        validate = mock.Mock(return_value=("/dev/sda", "/dev/sda2", 20))
        shrink = mock.Mock(side_effect=lambda *_args, **_kwargs: self.assertTrue(state["locked"]))
        sizes = mock.Mock(side_effect=[100, 100, 80])
        starts = mock.Mock(side_effect=[1000, 1000])
        def commit(*args, **kwargs):
            self.assertFalse(state["locked"])
            with hold(args[0], args[3]):
                kwargs["before_partition"]()
            return "/dev/sda3"

        with tempfile.TemporaryDirectory() as marker_dir:
            result = plan_commit.prepare_ntfs_resize_target(
                {"resize_partition": "/dev/sda2"}, mock.Mock(),
                normal_device_path=lambda value: value or "",
                validate_target=validate,
                required_tools=("ntfsresize", "parted"),
                which=lambda _tool: "/usr/bin/tool",
                unmount_target_disk=mock.Mock(), partition_size=sizes,
                partition_number=lambda _part: 2, block_size=lambda _disk: 1,
                partition_start=starts,
                shrink_filesystem_guarded=shrink,
                run_command=mock.Mock(), as_root=lambda argv: argv,
                settle=mock.Mock(), commit_partition=commit,
                marker_root=Path(marker_dir), ntfs_fs_size=lambda _part: 100,
            )
        self.assertEqual(result, ("/dev/sda", "/dev/sda3"))
        shrink.assert_called_once()
        self.assertEqual(validate.call_count, 3)

    def test_btrfs_resize_mount_stays_registered_when_both_unmounts_fail(self):
        registered = []
        released = []
        calls = [SimpleNamespace(returncode=0), SimpleNamespace(returncode=1), SimpleNamespace(returncode=1)]
        with mock.patch.object(fsresize, "_require_tools"), \
             mock.patch.object(fsresize.tempfile, "mkdtemp", return_value="/tmp/kyth-test-mount"), \
             mock.patch.object(fsresize, "_run_typed", side_effect=calls), \
             mock.patch.object(fsresize, "_stream_typed"), \
             mock.patch.object(Path, "rmdir"):
            fsresize._shrink_btrfs(
                "/dev/sda2", 100, lambda _message: None,
                register_mount=registered.append, release_mount=released.append,
            )
        self.assertEqual(registered, ["/tmp/kyth-test-mount"])
        self.assertEqual(released, [])

    def test_configuration_does_not_release_mount_after_failed_unmount(self):
        context = InstallerContext()
        context.register_mount("/run/kyth-target")
        with tempfile.TemporaryDirectory() as tmp:
            etc = Path(tmp) / "etc"
            etc.mkdir()
            (etc / "fstab").write_text("before\n")
            configure_installed_system(
                target_part="/dev/sda2", install_mode="wipe", config_root=tmp,
                alongside_mount="", log=lambda _message: None, progress=lambda _pct: None,
                context=context, request=InstallRequest(username="pat", password_hash="hash"),
                find_deploy_etc=lambda _root: str(etc), ensure_system_accounts=lambda *_a: None,
                configure_alongside_fstab=lambda *_a: None,
                configure_manual_mounts=lambda *_a: None,
                configure_hostname_timezone=lambda *_a: None,
                create_installer_user=lambda *_a: None,
                validate_installed_target=lambda *_a, **_kw: [],
                persist_artifacts=lambda *_a: None,
                unmount_configuration=lambda *_a, **_kw: (), run_command=mock.Mock(),
            )
        self.assertEqual(context.cleanup_mounts, ["/run/kyth-target"])

    def test_registered_mount_cleanup_continues_after_command_exception(self):
        context = InstallerContext()
        context.register_mount("/mnt/first")
        context.register_mount("/mnt/second")
        with mock.patch(
            "kyth_installer.system.unmount_filesystem",
            side_effect=[RuntimeError("umount helper failed"), SimpleNamespace(returncode=0)],
        ) as unmount:
            recovery.cleanup_registered_mounts(context, run=mock.Mock())
        self.assertEqual(unmount.call_count, 2)
        self.assertEqual(context.cleanup_mounts, ["/mnt/second"])

    def test_configuration_unmount_reports_only_successful_mounts(self):
        with mock.patch(
            "kyth_installer.cleanup.unmount_filesystem",
            side_effect=[SimpleNamespace(returncode=1), SimpleNamespace(returncode=0)],
        ):
            result = unmount_configuration("/unused", "/run/target", run=mock.Mock())
        self.assertEqual(result, ("/run/target",))

    def test_configuration_unmount_keeps_failed_mounts_and_handles_exceptions(self):
        with mock.patch(
            "kyth_installer.cleanup.unmount_filesystem",
            side_effect=[RuntimeError("child busy"), SimpleNamespace(returncode=1)],
        ):
            self.assertEqual(unmount_configuration("/unused", "/run/target", run=mock.Mock()), ())
        with mock.patch(
            "kyth_installer.cleanup.unmount_filesystem", side_effect=OSError("mount busy"),
        ):
            self.assertEqual(unmount_configuration("/target", "", run=mock.Mock()), ())

    def test_shrink_refuses_to_continue_when_encryption_probe_fails(self):
        with mock.patch("kyth_installer.assurance._battery_check"), \
             mock.patch("kyth_installer.disk._parent_disk", return_value="/dev/sda"), \
             mock.patch("kyth_installer.assurance._encryption_check", side_effect=RuntimeError("lsblk failed")):
            with self.assertRaisesRegex(RuntimeError, "refusing to shrink blind"):
                fsresize.validate_shrink_request("/dev/sda2", "ntfs")

    def test_encryption_probe_failure_on_in_use_ntfs_is_not_treated_as_clear(self):
        with mock.patch(
            "kyth_installer.disk.list_partitions",
            return_value=[{"name": "/dev/sda2", "fstype": "ntfs", "in_use": True}],
        ), mock.patch("kyth_installer.runner.run_command", side_effect=OSError("blkid unavailable")):
            with self.assertRaisesRegex(OSError, "blkid unavailable"):
                assurance._encryption_check(disk="/dev/sda", strict=True)

    def test_strict_encryption_scan_requires_partitions_and_reports_clear_scan(self):
        with mock.patch("kyth_installer.disk.list_partitions", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "No partitions could be verified"):
                assurance._encryption_check(disk="/dev/sda", strict=True)
        with mock.patch(
            "kyth_installer.disk.list_partitions",
            return_value=[{"name": "/dev/sda1", "fstype": "ext4", "in_use": False}],
        ):
            result = assurance._encryption_check(disk="/dev/sda", strict=True)
        self.assertEqual(result.status, "pass")


if __name__ == "__main__":
    unittest.main()
