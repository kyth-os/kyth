import ast
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "build_files" / "kyth-installer" / "kyth_installer"
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer import install, post_routes  # noqa: E402
from kyth_installer.context import InstallLifecycle, InstallerContext  # noqa: E402
from kyth_installer.partition_ops import get_journal, init_journal, reset_journal  # noqa: E402
from kyth_installer.plan import InstallPlan  # noqa: E402
from kyth_installer.streaming import StreamingCommandRunner  # noqa: E402


class InstallerCommandSurfaceTests(unittest.TestCase):
    def test_execution_modules_use_runner_for_process_launches(self):
        forbidden = {"run", "Popen", "check_output", "check_call", "call"}
        execution_modules = sorted(
            path for path in INSTALLER.rglob("*.py") if path.name != "runner.py"
        )

        for path in execution_modules:
            with self.subTest(filename=path.relative_to(INSTALLER)):
                tree = ast.parse(path.read_text())
                calls = []
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "subprocess"
                        and node.func.attr in forbidden
                    ):
                        calls.append(node.lineno)

                self.assertFalse(calls, f"direct process launches at {calls}")

    def test_discovery_modules_keep_subprocess_boundary_explicit(self):
        discovery_modules = {"disk/__init__.py"}
        for filename in discovery_modules:
            with self.subTest(filename=filename):
                text = (INSTALLER / filename).read_text()
                self.assertIn("subprocess", text)

    def test_installer_contexts_do_not_share_state_or_events(self):
        first = InstallerContext()
        second = InstallerContext()

        first.state["disk"] = "/dev/sda"
        first.events.publish({"type": "progress", "value": 10})

        self.assertEqual(second.state["disk"], "")
        self.assertEqual(second.events.events, [])

    def test_installer_contexts_do_not_share_partition_journals(self):
        first = InstallerContext()
        second = InstallerContext()

        with mock.patch(
            "kyth_installer.partition_ops._normal_device_path", side_effect=lambda path: path
        ):
            first_journal = init_journal("/dev/sda", first)
            second_journal = init_journal("/dev/nvme0n1", second)

        first_journal.add_op("new_table", {"table_type": "gpt"})
        self.assertIs(get_journal(first), first_journal)
        self.assertIs(get_journal(second), second_journal)
        self.assertEqual(second_journal.pending(), [])

        reset_journal(first)
        self.assertIsNone(get_journal(first))
        self.assertIs(get_journal(second), second_journal)

    def test_context_tracks_install_lifecycle(self):
        context = InstallerContext()

        self.assertEqual(context.lifecycle, InstallLifecycle.IDLE)
        context.transition(InstallLifecycle.VALIDATED)
        context.transition(InstallLifecycle.INSTALLING)
        context.transition(InstallLifecycle.DONE)

        self.assertEqual(context.lifecycle, InstallLifecycle.DONE)

    def test_partition_mutations_are_blocked_during_installation(self):
        context = InstallerContext()
        service = post_routes.PostRouteService(context)
        context.install_lock.acquire()
        try:
            response = service.dispatch("new_table", {"disk": "/dev/sda"})
        finally:
            context.install_lock.release()

        self.assertEqual(response.status, 409)
        self.assertFalse(response.payload["ok"])

    def test_wipe_storage_phase_returns_root_context(self):
        logs = []
        progress = []
        context = InstallerContext()

        with mock.patch.object(install, "_run_cmd"), \
             mock.patch.object(install, "run_command"), \
             mock.patch.object(install, "unmount_target_disk") as unmount_target_disk, \
             mock.patch.object(install, "get_root_partition", return_value="/dev/sda3"):
            target_part, root_part, alongside_mount = install._prepare_install_storage(
                "/dev/sda",
                "wipe",
                "src",
                "tgt",
                logs.append,
                progress.append,
                "",
                context,
            )

        self.assertEqual((target_part, root_part, alongside_mount), ("", "/dev/sda3", ""))
        unmount_target_disk.assert_called_once_with("/dev/sda", logs.append)

    def test_storage_phase_returns_partition_context_for_non_wipe_modes(self):
        cases = ["alongside", "free-space", "resize-ntfs"]

        for mode in cases:
            with self.subTest(mode=mode):
                logs = []
                progress = []
                context = InstallerContext()
                context.state.update({
                    "install_mode": mode,
                    "target_partition": "/dev/sda2",
                })
                with mock.patch.object(
                    install,
                    "_prepare_install_plan",
                    return_value=InstallPlan(mode=mode, disk="/dev/sda", target_partition="/dev/sda2"),
                ), mock.patch.object(
                    install,
                    "_validate_install_target",
                    return_value=("/dev/sda", "/dev/sda2"),
                ), mock.patch.object(
                    install,
                    "_install_images",
                    return_value=("src", "tgt"),
                ), mock.patch.object(
                    install,
                    "_network_preflight",
                    return_value=None,
                ), mock.patch.object(
                    install,
                    "run_command",
                ) as run_command, mock.patch.object(
                    install,
                    "_run_cmd",
                ), mock.patch.object(
                    install,
                    "get_root_partition",
                    return_value="/dev/sda3",
                ), mock.patch.object(
                    install,
                    "unmount_target_disk",
                ), mock.patch.object(
                    install.Path,
                    "mkdir",
                ):
                    run_command.return_value.stdout = "UUID=abc\n"
                    run_command.return_value.returncode = 0
                    target_part, root_part, alongside_mount = install._prepare_install_storage(
                        "/dev/sda",
                        mode,
                        "src",
                        "tgt",
                        logs.append,
                        progress.append,
                        "",
                        context,
                    )

                self.assertIsInstance(target_part, str)
                self.assertIsInstance(root_part, str)
                self.assertIsInstance(alongside_mount, str)

    def test_wipe_worker_reaches_done_event_with_mocked_side_effects(self):
        context = InstallerContext()
        context.state.update({
            "disk": "/dev/sda",
            "efi_partition": "",
            "hostname": "kyth",
            "install_mode": "wipe",
            "kernel": "fedora",
            "mok_password": "",
            "password_hash": "$6$hash",
            "target_partition": "",
            "timezone": "UTC",
            "username": "user",
        })

        with mock.patch.object(
            install,
            "_prepare_install_plan",
            return_value=InstallPlan(mode="wipe", disk="/dev/sda"),
        ), mock.patch.object(
            install,
            "_validate_install_target",
            return_value=("/dev/sda", None),
        ), mock.patch.object(
            install,
            "_install_images",
            return_value=("src", "tgt"),
        ), mock.patch.object(
            install,
            "_network_preflight",
            return_value=None,
        ), mock.patch.object(
            install,
            "_validate_storage_intent",
            return_value=None,
        ), mock.patch.object(
            install,
            "run_command",
        ) as run_command, mock.patch.object(
            install,
            "_run_cmd",
        ), mock.patch.object(
            install,
            "get_root_partition",
            return_value="/dev/sda3",
        ), mock.patch.object(
            install,
            "find_deploy_etc",
            return_value=Path("/mnt/deploy/etc"),
        ), mock.patch.object(
            install,
            "ensure_system_accounts",
        ), mock.patch.object(
            install,
            "_try_stage_mok_enrollment",
            return_value={},
        ), mock.patch.object(
            install,
            "unmount_target_disk",
        ), mock.patch.object(
            install,
            "require_root",
        ):
            run_command.return_value.stdout = "UUID=abc\n"
            run_command.return_value.returncode = 0
            install._run_install_worker(lambda _msg: None, lambda _pct: None, "", context)

        self.assertTrue(any(event.get("type") == "done" for event in context.events.events))
        self.assertFalse([event for event in context.events.events if event.get("type") == "error"])

    def test_alongside_worker_cleans_temp_mount_after_error(self):
        context = InstallerContext()
        context.state.update({
            "disk": "/dev/sda",
            "efi_partition": "",
            "hostname": "kyth",
            "install_mode": "alongside",
            "kernel": "fedora",
            "mok_password": "",
            "password_hash": "$6$hash",
            "target_partition": "/dev/sda2",
            "timezone": "UTC",
            "username": "user",
        })

        with mock.patch.object(
            install,
            "_prepare_install_plan",
            return_value=InstallPlan(
                mode="alongside",
                disk="/dev/sda",
                target_partition="/dev/sda2",
            ),
        ), mock.patch.object(
            install,
            "_validate_install_target",
            return_value=("/dev/sda", "/dev/sda2"),
        ), mock.patch.object(
            install,
            "_install_images",
            return_value=("src", "tgt"),
        ), mock.patch.object(
            install,
            "_network_preflight",
            return_value=None,
        ), mock.patch.object(
            install,
            "_validate_storage_intent",
            return_value=None,
        ), mock.patch.object(
            install,
            "run_command",
        ) as run_command, mock.patch.object(
            install,
            "_run_cmd",
            side_effect=RuntimeError("install failed"),
        ), mock.patch.object(
            install,
            "unmount_target_disk",
        ), mock.patch.object(
            install,
            "require_root",
        ):
            run_command.return_value.stdout = "UUID=abc\n"
            run_command.return_value.returncode = 0
            install._run_install_worker(lambda _msg: None, lambda _pct: None, "", context)

        cleanup_calls = [
            call
            for call in run_command.call_args_list
            if "/var/tmp/kyth-alongside-target" in repr(call)  # noqa: S108 — fixture string, not a real path opened on disk
        ]
        self.assertTrue(cleanup_calls)
        self.assertTrue([event for event in context.events.events if event.get("type") == "error"])

    def test_bootc_to_disk_command_omits_acknowledge_destructive(self):
        # bootc's `install to-disk` subcommand has no --acknowledge-destructive
        # flag at all (only `to-filesystem` does) — passing it is a hard CLI
        # parse error ("unexpected argument"), so every wipe install fails.
        cmd = install._build_bootc_install_cmd(
            "to-disk", "src", "tgt", "/dev/sda",
            extra_flags=["--filesystem", "btrfs", "--wipe"],
        )
        self.assertNotIn("--acknowledge-destructive", cmd)
        self.assertIn("--wipe", cmd)

    def test_bootc_to_filesystem_command_keeps_acknowledge_destructive(self):
        cmd = install._build_bootc_install_cmd(
            "to-filesystem", "src", "tgt", "/mnt/target",
            extra_flags=["--skip-finalize", "--karg=rootflags=subvol=@"],
        )
        self.assertIn("--acknowledge-destructive", cmd)

    def test_skip_fetch_check_not_duplicated_when_env_toggle_also_set(self):
        # extra_flags may already carry --skip-fetch-check (alongside/manual
        # partition installs, which always need it); the SKIP_FETCH_CHECK env
        # toggle must not append a second copy of the same flag.
        with mock.patch.object(install, "SKIP_FETCH_CHECK", True):
            cmd = install._build_bootc_install_cmd(
                "to-filesystem", "src", "tgt", "/mnt/target",
                extra_flags=["--skip-finalize", "--skip-fetch-check"],
            )
        self.assertEqual(cmd.count("--skip-fetch-check"), 1)

    def test_alongside_install_always_passes_skip_fetch_check(self):
        # bootc install to-filesystem onto an alongside/manual target mounts
        # other partitions (e.g. /boot/efi) under it before running; per
        # plan.py's install_mode docstring this needs --skip-fetch-check
        # unconditionally for the partition CLI as well, regardless
        # of the unrelated SKIP_FETCH_CHECK network-preflight env toggle.
        context = InstallerContext()
        context.state.update({
            "disk": "/dev/sda",
            "efi_partition": "",
            "hostname": "kyth",
            "install_mode": "alongside",
            "kernel": "fedora",
            "mok_password": "",
            "password_hash": "$6$hash",
            "target_partition": "/dev/sda2",
            "timezone": "UTC",
            "username": "user",
        })

        captured_cmd = {}

        def fake_run_cmd(cmd, *args, **kwargs):
            if cmd and cmd[0] == "bootc":
                captured_cmd["argv"] = cmd
                raise RuntimeError("stop after capturing the install command")

        with mock.patch.object(
            install,
            "_prepare_install_plan",
            return_value=InstallPlan(
                mode="alongside",
                disk="/dev/sda",
                target_partition="/dev/sda2",
            ),
        ), mock.patch.object(
            install,
            "_validate_install_target",
            return_value=("/dev/sda", "/dev/sda2"),
        ), mock.patch.object(
            install,
            "_install_images",
            return_value=("src", "tgt"),
        ), mock.patch.object(
            install,
            "_network_preflight",
            return_value=None,
        ), mock.patch.object(
            install,
            "_validate_storage_intent",
            return_value=None,
        ), mock.patch.object(
            install,
            "run_command",
        ) as run_command, mock.patch.object(
            install,
            "_run_cmd",
            side_effect=fake_run_cmd,
        ), mock.patch.object(
            install,
            "unmount_target_disk",
        ), mock.patch.object(
            install,
            "require_root",
        ):
            run_command.return_value.stdout = "UUID=abc\n"
            run_command.return_value.returncode = 0
            install._run_install_worker(lambda _msg: None, lambda _pct: None, "", context)

        self.assertIn("--skip-fetch-check", captured_cmd["argv"])

    def test_streaming_runner_publishes_stats_with_zero_network_baseline(self):
        # output_state was referenced by _net_monitor and emit_line but never
        # assigned anywhere in _run_cmd's scope. emit_line's write hit a bare
        # `except Exception: pass`; _net_monitor's read crashed the daemon
        # thread on its very first loop tick with an unhandled NameError —
        # silently, since nothing joins or checks daemon thread health. The
        # actual bootc install kept running fine; progress/stats just froze
        # at 0 forever with no error anywhere to reveal why. Exercises the
        # real thread (not mocked) so a regression here reproduces the bug.
        logs = []
        progress_values = []
        pushed = []
        cmd = [
            sys.executable, "-c",
            "print('layers already present: 0; layers needed: 1 (1 MB)', flush=True); "
            "import time; time.sleep(1.5)",
        ]
        runner = StreamingCommandRunner(
            rx_bytes=lambda: 0,
            publish=pushed.append,
            monitor_interval=0.01,
        )
        with mock.patch(
            "kyth_installer.runner._validate_executable",
            side_effect=lambda executable: executable,
        ):
            runner.run(
                cmd, 5, 90, logs.append, progress_values.append,
                stall_timeout=10, absolute_timeout=10,
            )

        stats_events = [e for e in pushed if e.get("type") == "stats"]
        self.assertTrue(
            stats_events,
            "net monitor never pushed a stats event — output_state is likely undefined again",
        )
        # Exact fraction is environment-dependent (real /proc/net/dev rx bytes
        # may tick slightly between rx_start capture and the first sample) —
        # what matters is the monitor thread ran at all, not the precise value.
        self.assertTrue(any(5 <= v <= 90 for v in progress_values))

    def test_worker_fails_closed_when_not_root(self):
        context = InstallerContext()
        with mock.patch.object(install, "require_root", side_effect=RuntimeError("must run as root")):
            install._run_install_worker(lambda _msg: None, lambda _pct: None, "", context)
        errors = [e for e in context.events.events if e.get("type") == "error"]
        self.assertTrue(errors)
        self.assertIn("root", errors[0].get("message", "").lower())


class EfiBootEntrySnapshotTests(unittest.TestCase):
    """bootc's bootupd step can rewrite EFI NVRAM boot entries when writing
    the OS image — this is the safety net that warns if a named entry (e.g.
    "Windows Boot Manager") present beforehand goes missing afterward."""

    def test_snapshot_returns_empty_when_efibootmgr_is_unavailable(self):
        with mock.patch.object(install.shutil, "which", return_value=None):
            self.assertEqual(install._snapshot_efi_boot_entries(lambda _m: None), "")

    def test_snapshot_returns_empty_on_nonzero_exit(self):
        with mock.patch.object(install.shutil, "which", return_value="/usr/sbin/efibootmgr"), \
             mock.patch.object(install, "run_command", return_value=mock.MagicMock(returncode=1, stdout="")):
            self.assertEqual(install._snapshot_efi_boot_entries(lambda _m: None), "")

    def test_snapshot_returns_empty_when_efibootmgr_raises(self):
        with mock.patch.object(install.shutil, "which", return_value="/usr/sbin/efibootmgr"), \
             mock.patch.object(install, "run_command", side_effect=RuntimeError("not UEFI")):
            self.assertEqual(install._snapshot_efi_boot_entries(lambda _m: None), "")

    def test_warns_when_a_named_entry_disappears(self):
        before = (
            "BootCurrent: 0001\n"
            "BootOrder: 0000,0001\n"
            "Boot0000* KythOS\tHD(1,GPT,...)\n"
            "Boot0001* Windows Boot Manager\tHD(1,GPT,...)\n"
        )
        after = (
            "BootCurrent: 0000\n"
            "BootOrder: 0000\n"
            "Boot0000* KythOS\tHD(1,GPT,...)\n"
        )
        logs = []
        install._warn_if_efi_boot_entries_disappeared(before, after, logs.append)
        self.assertTrue(any("Windows Boot Manager" in m for m in logs))

    def test_no_warning_when_entries_are_unchanged(self):
        snapshot = "Boot0000* KythOS\tHD(1,GPT,...)\nBoot0001* Windows Boot Manager\tHD(1,GPT,...)\n"
        logs = []
        install._warn_if_efi_boot_entries_disappeared(snapshot, snapshot, logs.append)
        self.assertEqual(logs, [])

    def test_no_warning_when_reordered_but_not_removed(self):
        before = "Boot0000* KythOS\tHD(1,GPT,...)\nBoot0001* Windows Boot Manager\tHD(1,GPT,...)\n"
        after = "Boot0001* Windows Boot Manager\tHD(1,GPT,...)\nBoot0000* KythOS\tHD(1,GPT,...)\n"
        logs = []
        install._warn_if_efi_boot_entries_disappeared(before, after, logs.append)
        self.assertEqual(logs, [])

    def test_no_warning_when_either_snapshot_is_empty(self):
        logs = []
        install._warn_if_efi_boot_entries_disappeared("", "Boot0000* KythOS\n", logs.append)
        install._warn_if_efi_boot_entries_disappeared("Boot0000* KythOS\n", "", logs.append)
        self.assertEqual(logs, [])


if __name__ == "__main__":
    unittest.main()
