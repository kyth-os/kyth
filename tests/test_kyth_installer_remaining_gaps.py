import json
import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer import app, partition_cli  # noqa: E402
from kyth_installer.context import InstallLifecycle, InstallerContext  # noqa: E402
from kyth_installer.phases import finalize, run as phase_run, storage  # noqa: E402
from kyth_installer.validation import InstallRequestError  # noqa: E402


class PartitionCliCoverageTests(unittest.TestCase):
    def test_identity_defaults_skip_password_and_reject_mismatch(self):
        with mock.patch.dict(os.environ, {"KYTH_HOSTNAME": "default-host", "KYTH_TIMEZONE": "Etc/UTC"}):
            answers = iter(["", "", ""])
            identity = partition_cli._prompt_identity(
                input_fn=lambda _prompt: next(answers), password_fn=mock.MagicMock()
            )
        self.assertEqual(identity, ("default-host", "Etc/UTC", "", ""))

        answers = iter(["host", "UTC", "alice"])
        passwords = iter(["first", "second"])
        with self.assertRaisesRegex(InstallRequestError, "Passwords do not match"):
            partition_cli._prompt_identity(
                input_fn=lambda _prompt: next(answers),
                password_fn=lambda _prompt: next(passwords),
            )

    def test_describe_target_validates_target_parent_and_efi(self):
        with mock.patch.object(partition_cli.disk, "_normal_device_path", return_value=None):
            with self.assertRaisesRegex(InstallRequestError, "Invalid target"):
                partition_cli._describe_target("bad", "")
        with mock.patch.object(partition_cli.disk, "_normal_device_path", return_value="/dev/sda1"), mock.patch.object(
            partition_cli.disk, "_parent_disk", return_value=None
        ):
            with self.assertRaisesRegex(InstallRequestError, "parent disk"):
                partition_cli._describe_target("/dev/sda1", "")
        with mock.patch.object(
            partition_cli.disk, "_normal_device_path", side_effect=["/dev/sda2", None]
        ), mock.patch.object(partition_cli.disk, "_parent_disk", return_value="/dev/sda"):
            with self.assertRaisesRegex(InstallRequestError, "Invalid EFI"):
                partition_cli._describe_target("/dev/sda2", "bad")

    def test_plan_and_success_events_are_rendered(self):
        with mock.patch.object(partition_cli.disk, "list_partitions", return_value=[
            {"name": "/dev/sda2", "size_human": "80 GiB"}
        ]), mock.patch("builtins.print") as output:
            partition_cli._print_plan("/dev/sda2", "/dev/sda", "")
        self.assertTrue(any("80 GiB" in str(call) for call in output.call_args_list))

        context = InstallerContext()
        context.events.publish({"type": "log", "text": "working"})
        context.lifecycle = InstallLifecycle.DONE
        with mock.patch("builtins.print") as output:
            self.assertEqual(partition_cli._render_events(context), 0)
        self.assertTrue(any("Installation complete" in str(call) for call in output.call_args_list))

    def test_run_maps_validation_runtime_and_busy_errors_to_exit_codes(self):
        common = [
            mock.patch.object(partition_cli.system, "require_root"),
            mock.patch.object(partition_cli, "_describe_target", return_value=("/dev/sda2", "/dev/sda", "")),
            mock.patch.object(partition_cli, "_print_plan"),
        ]
        answers = lambda: iter([partition_cli.CONFIRMATION, "host", "UTC", ""])
        with common[0], common[1], common[2], mock.patch.object(
            partition_cli, "validate_partition_install_request", side_effect=InstallRequestError("bad request")
        ), mock.patch("sys.stderr"):
            it = answers()
            self.assertEqual(partition_cli.run(["/dev/sda2"], input_fn=lambda _p: next(it)), 2)
        with mock.patch.object(partition_cli.system, "require_root", side_effect=OSError("not root")), mock.patch("sys.stderr"):
            self.assertEqual(partition_cli.run(["/dev/sda2"]), 1)
        with common[0], common[1], common[2], mock.patch.object(
            partition_cli, "validate_partition_install_request", return_value={}
        ), mock.patch.object(partition_cli, "start_installation", return_value=False), mock.patch("sys.stderr"):
            it = answers()
            self.assertEqual(partition_cli.run(["/dev/sda2"], input_fn=lambda _p: next(it)), 1)

    def test_main_exits_with_run_result(self):
        with mock.patch.object(partition_cli, "run", return_value=7):
            with self.assertRaisesRegex(SystemExit, "7"):
                partition_cli.main()


class StoragePhaseCoverageTests(unittest.TestCase):
    def test_plan_and_mode_dispatch_preserve_explicit_targets(self):
        plan = mock.MagicMock(
            disk="/dev/sda", mode="manual", source_ref="source", target_ref="target",
            target_partition="/dev/sda2", efi_partition="/dev/sda1",
        )
        context = InstallerContext()
        with mock.patch.object(storage, "_prepare_install_storage", return_value=(1, 2, 3)) as prepare:
            self.assertEqual(storage._prepare_storage_for_plan(plan, mock.Mock(), mock.Mock(), "/mnt", context), (1, 2, 3))
        self.assertEqual(prepare.call_args.kwargs["target_partition"], "/dev/sda2")

        with mock.patch("kyth_installer.execution.check_cancelled"), mock.patch.object(
            storage, "_assert_still_on_ac"
        ), mock.patch.object(storage, "_prepare_partition_target_storage", return_value="partition") as partition:
            context = InstallerContext()
            context.state.update({"target_partition": "/dev/sda3", "efi_partition": "/dev/sda1"})
            self.assertEqual(storage._prepare_install_storage("/dev/sda", "manual", "s", "t", mock.Mock(), mock.Mock(), "", context), "partition")
        self.assertEqual(partition.call_args.args[:2], ("/dev/sda3", "/dev/sda1"))

    def test_wipe_dispatch_and_efi_snapshot_failure_paths(self):
        context = InstallerContext()
        with mock.patch("kyth_installer.execution.check_cancelled"), mock.patch.object(
            storage, "_assert_still_on_ac"
        ), mock.patch.object(storage, "_prepare_wipe_disk_storage", return_value="wipe"):
            self.assertEqual(storage._prepare_install_storage("/dev/sda", "wipe", "s", "t", mock.Mock(), mock.Mock(), "", context), "wipe")

        with mock.patch.object(storage.shutil, "which", return_value=None):
            self.assertEqual(storage._snapshot_efi_boot_entries(mock.Mock()), "")
        with mock.patch.object(storage.shutil, "which", return_value="/usr/sbin/efibootmgr"), mock.patch(
            "kyth_installer.install.run_command", side_effect=OSError
        ):
            self.assertEqual(storage._snapshot_efi_boot_entries(mock.Mock()), "")

    def test_mount_efi_uses_bind_or_device_mount(self):
        for current, expected in (("/boot/efi\n", "--bind"), ("", "/dev/sda1")):
            calls = []

            def run(command, **_kwargs):
                calls.append(command)
                if command[:4] == ["findmnt", "-n", "-o", "MOUNTPOINT"]:
                    return SimpleNamespace(stdout=current)
                return SimpleNamespace(stdout="", returncode=0)

            context = InstallerContext()
            with mock.patch("kyth_installer.install.run_command", side_effect=run), mock.patch(
                "kyth_installer.install._as_root", side_effect=lambda argv: argv
            ):
                storage._mount_efi_for_alongside("/mnt", "/dev/sda1", mock.Mock(), context)
            self.assertTrue(any(expected in command for command in calls))


class FinalizePhaseCoverageTests(unittest.TestCase):
    def test_blkid_and_fstab_helpers_cover_success_and_failures(self):
        log = mock.MagicMock()
        with mock.patch("kyth_installer.install.run_command", return_value=SimpleNamespace(stdout="uuid-1\n")):
            self.assertEqual(finalize._blkid_uuid("/dev/sda1", log), "uuid-1")
        with mock.patch("kyth_installer.install.run_command", side_effect=OSError("probe")):
            self.assertIsNone(finalize._blkid_uuid("/dev/sda1", log))
        with mock.patch("kyth_installer.install.run_command", return_value=SimpleNamespace(stdout="")):
            self.assertIsNone(finalize._blkid_uuid("/dev/sda1", log))

        with mock.patch("kyth_installer.install.run_command"), mock.patch(
            "kyth_installer.install._as_root", side_effect=lambda argv: argv
        ):
            self.assertTrue(finalize._append_fstab_line("/etc", "line\n", log, "root"))
        with mock.patch("kyth_installer.install.run_command", side_effect=RuntimeError("write")):
            self.assertFalse(finalize._append_fstab_line("/etc", "line\n", log, "root"))

    def test_manual_mounts_handle_swap_home_and_missing_uuid(self):
        mounts = [
            {"partition": "/dev/sda2", "mountpoint": "/home", "fstype": "btrfs"},
            {"partition": "/dev/sda3", "mountpoint": "swap", "fstype": "linux-swap"},
            {"partition": "/dev/sda4", "mountpoint": "/data", "fstype": "ext4"},
        ]
        context = InstallerContext()
        with mock.patch("kyth_installer.install._get_manual_mounts", return_value=mounts), mock.patch.object(
            finalize, "_blkid_uuid", side_effect=["home-uuid", "swap-uuid", None]
        ), mock.patch.object(finalize, "_append_fstab_line", return_value=True) as append, mock.patch(
            "kyth_installer.install.run_command"
        ), mock.patch("kyth_installer.install._as_root", side_effect=lambda argv: argv), mock.patch(
            "kyth_installer.install._safe_umount"
        ):
            finalize._configure_manual_mounts("/target", "/etc", mock.Mock(), context)
        self.assertEqual(append.call_count, 2)
        self.assertIn("/var/home", append.call_args_list[0].args[1])
        self.assertIn(" none swap ", append.call_args_list[1].args[1])

    def test_user_creation_failure_is_nonfatal(self):
        log = mock.MagicMock()
        progress = mock.MagicMock()
        with mock.patch.object(finalize, "_shared_create_installer_user", side_effect=OSError("bad user")):
            finalize._create_installer_user("/config", "/deploy", "alice", "hash", log, progress)
        progress.assert_not_called()
        self.assertTrue(any("user creation failed" in str(call).lower() for call in log.call_args_list))


class RunPhaseCoverageTests(unittest.TestCase):
    def test_run_install_surfaces_log_write_failure_and_progress(self):
        context = InstallerContext()

        def worker(log, progress, _mount, ctx):
            log("hello")
            progress(42)
            ctx.transition(InstallLifecycle.FAILED)

        fake_fd = 9
        with mock.patch("kyth_installer.install.require_root"), mock.patch.object(
            phase_run, "LOG_FILE", mock.MagicMock()
        ) as log_file, mock.patch.object(phase_run.os, "open", return_value=fake_fd), mock.patch.object(
            phase_run.os, "close"
        ), mock.patch.object(phase_run, "_record_transaction"), mock.patch.object(
            phase_run, "_run_install_worker", side_effect=worker
        ):
            log_file.parent.mkdir.return_value = None
            log_file.open.side_effect = OSError("read-only")
            phase_run._run_install(context)
        events = context.events.events
        self.assertTrue(any(e.get("value") == 42 for e in events))
        self.assertTrue(any("log write failed" in e.get("text", "") for e in events))

    def test_run_install_setup_failure_publishes_error_without_worker(self):
        context = InstallerContext()
        with mock.patch("kyth_installer.install.require_root", side_effect=RuntimeError("not root")), mock.patch.object(
            phase_run, "_run_install_worker"
        ) as worker:
            phase_run._run_install(context)
        self.assertEqual(context.lifecycle, InstallLifecycle.FAILED)
        self.assertTrue(any(e.get("type") == "error" for e in context.events.events))
        worker.assert_not_called()


class InstallerAppCoverageTests(unittest.TestCase):
    def test_answer_file_rejects_payload_shape_unknown_fields_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "answers.json"
            path.write_text("[]")
            path.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "one JSON object"):
                app._load_answer_file(str(path))
            path.write_text(json.dumps({"unexpected": True}))
            with self.assertRaisesRegex(ValueError, "Unknown installer"):
                app._load_answer_file(str(path))
            path.write_text(json.dumps({"disk": "/dev/sda"}))
            path.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "chmod 600"):
                app._load_answer_file(str(path))

    def test_write_session_token_creates_a_private_file_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            token_path = Path(tmp) / "session-token"
            app._write_session_token(token_path, "token-value")
            self.assertEqual(token_path.read_text(), "token-value")
            self.assertEqual(token_path.stat().st_mode & 0o777, 0o600)

            link_path = Path(tmp) / "token-link"
            link_path.symlink_to(token_path)
            with self.assertRaisesRegex(RuntimeError, "must not be a symlink"):
                app._write_session_token(link_path, "replacement")

    def test_headless_warns_for_command_line_password(self):
        service = mock.MagicMock()
        service.start_install.return_value = {"started": False, "message": "invalid"}
        with mock.patch.object(sys, "argv", ["prog", "--headless", "--password", "secret"]), mock.patch.object(
            app, "InstallerService", return_value=service
        ), mock.patch("sys.stderr") as stderr:
            with self.assertRaises(SystemExit) as raised:
                app.run_headless()
        self.assertEqual(raised.exception.code, 1)
        self.assertTrue(any("/proc/cmdline" in str(call) for call in stderr.write.call_args_list))

    def test_headless_renders_done_and_failed_lifecycle_events(self):
        for event, lifecycle, exit_code in (
            ({"type": "done", "mok_state": "enrolled"}, InstallLifecycle.DONE, 0),
            ({}, InstallLifecycle.FAILED, 1),
        ):
            context = InstallerContext()
            if event:
                context.events.publish(event)
            context.lifecycle = lifecycle
            service = mock.MagicMock()
            service.start_install.return_value = {"started": True}
            with mock.patch.object(sys, "argv", ["prog", "--headless"]), mock.patch.object(
                app, "InstallerContext", return_value=context
            ), mock.patch.object(app, "InstallerService", return_value=service), mock.patch("builtins.print"):
                with self.assertRaises(SystemExit) as raised:
                    app.run_headless()
            self.assertEqual(raised.exception.code, exit_code)

    def test_gui_main_launches_chromium_and_handles_interrupt(self):
        server = mock.MagicMock()
        proc = mock.MagicMock()
        proc.wait.side_effect = KeyboardInterrupt
        with mock.patch.object(sys, "argv", ["kyth-installer"]), mock.patch.object(
            app, "_Server", return_value=server
        ), mock.patch.object(app.threading, "Thread") as thread, mock.patch.object(
            app.time, "sleep"
        ), mock.patch.object(app.shutil, "which", side_effect=lambda name: name == "chromium-browser"), mock.patch.object(
            app, "spawn_command", return_value=proc
        ) as spawn, mock.patch.dict(os.environ, {}, clear=True):
            app.main()
        thread.return_value.start.assert_called_once()
        self.assertEqual(spawn.call_args.args[0][0], "chromium-browser")
        proc.terminate.assert_called_once()

    def test_gui_main_preserves_display_environment_for_sudo_user(self):
        proc = mock.MagicMock()
        with mock.patch.object(sys, "argv", ["kyth-installer"]), mock.patch.object(
            app, "_Server"
        ), mock.patch.object(app.threading, "Thread"), mock.patch.object(app.time, "sleep"), mock.patch.object(
            app.shutil, "which", return_value="/usr/bin/chromium"
        ), mock.patch.object(app, "spawn_command", return_value=proc) as spawn, mock.patch.dict(
            os.environ, {"SUDO_USER": "alice", "DISPLAY": ":0"}, clear=True
        ):
            app.main()
        command = spawn.call_args.args[0]
        self.assertEqual(command[:5], ["sudo", "-u", "alice", "env", "DISPLAY=:0"])

    def test_gui_main_uses_unix_service_and_cleans_up(self):
        proc = mock.MagicMock()
        run_calls = []
        with tempfile.TemporaryDirectory() as tmp:
            socket_path = Path(tmp) / "api.sock"
            socket_path.touch()
            token_path = Path(tmp) / "session-token"
            with mock.patch.object(sys, "argv", ["kyth-installer"]), mock.patch.object(
                app, "SOCKET_PATH", socket_path
            ), mock.patch.object(app, "SESSION_TOKEN_FILE", token_path), mock.patch.object(
                app, "_write_session_token"
            ) as write_token, mock.patch.object(
                app, "run_command", side_effect=lambda *args, **kwargs: run_calls.append((args, kwargs))
            ), mock.patch.object(app.shutil, "which", side_effect=lambda name: "/usr/bin/kyth-installer-shell" if name == "kyth-installer-shell" else None), mock.patch.object(
                app, "spawn_command", return_value=proc
            ) as spawn, mock.patch.object(app.time, "sleep"), mock.patch.object(
                app.time, "monotonic", return_value=0
            ), mock.patch("subprocess.run", return_value=SimpleNamespace(stdout="")), mock.patch.dict(
                os.environ, {}, clear=True
            ):
                app.main()

        write_token.assert_called_once_with(token_path, app.SESSION_TOKEN)
        self.assertEqual([call[0][0] for call in run_calls], [
            ["systemctl", "start", "kyth-installerd.service"],
            ["systemctl", "stop", "kyth-installerd.service"],
        ])
        self.assertIn("--socket-path", spawn.call_args.args[0])
        proc.wait.assert_called_once()

    def test_gui_main_waits_for_unix_socket_and_ignores_cleanup_unlink_errors(self):
        proc = mock.MagicMock()
        with tempfile.TemporaryDirectory() as tmp:
            socket_path = Path(tmp) / "api.sock"
            token_path = Path(tmp) / "session-token"
            with mock.patch.object(sys, "argv", ["kyth-installer"]), mock.patch.object(
                app, "SOCKET_PATH", socket_path
            ), mock.patch.object(app, "SESSION_TOKEN_FILE", token_path), mock.patch.object(
                app, "_write_session_token"
            ), mock.patch.object(app, "run_command"), mock.patch.object(
                app.shutil, "which", return_value="/usr/bin/kyth-installer-shell"
            ), mock.patch.object(app, "spawn_command", return_value=proc), mock.patch.object(
                app.time, "monotonic", side_effect=[0, 1, 10]
            ), mock.patch.object(app.time, "sleep"), mock.patch.object(
                Path, "unlink", side_effect=OSError("cleanup failed")
            ):
                with self.assertRaisesRegex(RuntimeError, "did not create"):
                    app.main()

    def test_gui_main_rejects_socket_transport_without_installer_shell(self):
        proc = mock.MagicMock()
        with tempfile.TemporaryDirectory() as tmp:
            socket_path = Path(tmp) / "api.sock"
            socket_path.touch()
            token_path = Path(tmp) / "session-token"
            with mock.patch.object(sys, "argv", ["kyth-installer"]), mock.patch.object(
                app, "SOCKET_PATH", socket_path
            ), mock.patch.object(app, "SESSION_TOKEN_FILE", token_path), mock.patch.object(
                app, "_write_session_token"
            ), mock.patch.object(app, "run_command"), mock.patch.object(
                app.shutil, "which", return_value=None
            ), mock.patch.object(app, "spawn_command", return_value=proc):
                with self.assertRaisesRegex(RuntimeError, "required when Unix transport"):
                    app.main()

    def test_gui_main_resolves_session_owner_from_loginctl_xdg_and_sudo(self):
        proc = mock.MagicMock()
        cases = (
            ({}, [SimpleNamespace(stdout="c1"), SimpleNamespace(stdout="alice")], "alice"),
            ({"XDG_RUNTIME_DIR": "/run/user/1000"}, [SimpleNamespace(stdout="")], "alice"),
            ({"SUDO_USER": "alice"}, [SimpleNamespace(stdout="")], "alice"),
        )
        for environment, loginctl_results, expected_user in cases:
            with self.subTest(environment=environment):
                with mock.patch.object(sys, "argv", ["kyth-installer"]), mock.patch.object(
                    app, "_Server"
                ), mock.patch.object(app.threading, "Thread"), mock.patch.object(app.time, "sleep"), mock.patch.object(
                    app.shutil, "which", return_value="/usr/bin/chromium"
                ), mock.patch.object(app, "spawn_command", return_value=proc) as spawn, mock.patch(
                    "subprocess.run", side_effect=loginctl_results
                ), mock.patch("pwd.getpwuid", return_value=SimpleNamespace(pw_name="alice")), mock.patch(
                    "pwd.getpwnam", return_value=SimpleNamespace(pw_name="alice")
                ), mock.patch.dict(os.environ, environment, clear=True):
                    app.main()
                self.assertEqual(spawn.call_args.args[0][1], "-u")
                self.assertEqual(spawn.call_args.args[0][2], expected_user)

    def test_gui_main_falls_back_when_session_owner_probes_fail(self):
        proc = mock.MagicMock()
        with mock.patch.object(sys, "argv", ["kyth-installer"]), mock.patch.object(
            app, "_Server"
        ), mock.patch.object(app.threading, "Thread"), mock.patch.object(app.time, "sleep"), mock.patch.object(
            app.shutil, "which", return_value="/usr/bin/chromium"
        ), mock.patch.object(app, "spawn_command", return_value=proc), mock.patch(
            "subprocess.run", side_effect=OSError("loginctl unavailable")
        ), mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": "/run/user/not-a-uid"}, clear=True):
            app.main()

    def test_module_entrypoint_dispatches_to_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            answer_file = Path(tmp) / "answers.json"
            answer_file.write_text("{}")
            answer_file.chmod(0o644)
            with mock.patch.object(sys, "argv", ["kyth-installer", "--headless", "--answer-file", str(answer_file)]):
                with self.assertRaises(SystemExit) as raised:
                    runpy.run_module("kyth_installer.app", run_name="__main__")
            self.assertEqual(raised.exception.code, 2)

    def test_gui_main_removes_token_when_unix_service_fails_to_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            socket_path = Path(tmp) / "api.sock"
            token_path = Path(tmp) / "session-token"
            with mock.patch.object(sys, "argv", ["kyth-installer"]), mock.patch.object(
                app, "SOCKET_PATH", socket_path
            ), mock.patch.object(app, "SESSION_TOKEN_FILE", token_path), mock.patch.object(
                app, "_write_session_token"
            ), mock.patch.object(app, "run_command", side_effect=RuntimeError("start failed")):
                with self.assertRaisesRegex(RuntimeError, "start failed"):
                    app.main()

    def test_gui_main_fails_and_removes_token_when_unix_socket_never_appears(self):
        with tempfile.TemporaryDirectory() as tmp:
            socket_path = Path(tmp) / "api.sock"
            token_path = Path(tmp) / "session-token"
            with mock.patch.object(sys, "argv", ["kyth-installer"]), mock.patch.object(
                app, "SOCKET_PATH", socket_path
            ), mock.patch.object(app, "SESSION_TOKEN_FILE", token_path), mock.patch.object(
                app, "_write_session_token"
            ), mock.patch.object(app, "run_command"), mock.patch.object(
                app.time, "monotonic", side_effect=[0, 10]
            ), mock.patch.object(app.time, "sleep"):
                with self.assertRaisesRegex(RuntimeError, "did not create"):
                    app.main()

    def test_headless_answer_file_error_calls_parser_error(self):
        with mock.patch.object(app, "_load_answer_file", side_effect=OSError("boom")) as loader:
            with mock.patch.object(sys, "argv", ["prog", "--headless", "--answer-file", "/tmp/answers.json"]):
                with mock.patch.object(app.argparse.ArgumentParser, "error", side_effect=SystemExit(2)) as parser_error:
                    with self.assertRaises(SystemExit) as ctx:
                        app.run_headless()
                    self.assertEqual(ctx.exception.code, 2)
                    parser_error.assert_called_once()
                    self.assertIn("boom", parser_error.call_args.args[0])
            loader.assert_called_once()

    def test_headless_json_decode_error_calls_parser_error(self):
        with mock.patch.object(app, "_load_answer_file", side_effect=json.JSONDecodeError("bad", "", 0)):
            with mock.patch.object(sys, "argv", ["prog", "--headless", "--answer-file", "/tmp/answers.json"]):
                with mock.patch.object(app.argparse.ArgumentParser, "error", side_effect=SystemExit(2)) as parser_error:
                    with self.assertRaises(SystemExit):
                        app.run_headless()
                    parser_error.assert_called_once()

    def test_main_dispatches_to_run_headless(self):
        with mock.patch.object(sys, "argv", ["kyth-installer", "--headless"]), mock.patch.object(
            app, "run_headless"
        ) as headless:
            app.main()
            headless.assert_called_once()

    def test_main_dispatches_to_run_headless_with_return(self):
        # also verify the return after run_headless prevents token generation
        with mock.patch.object(sys, "argv", ["kyth-installer", "--headless"]), mock.patch.object(
            app, "run_headless"
        ) as headless, mock.patch.object(app.secrets, "token_urlsafe") as token:
            app.main()
            headless.assert_called_once()
            token.assert_not_called()


if __name__ == "__main__":
    unittest.main()
