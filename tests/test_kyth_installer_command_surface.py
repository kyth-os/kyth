import ast
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "build_files" / "kyth-installer" / "kyth_installer"
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer import install  # noqa: E402
from kyth_installer.plan import InstallPlan  # noqa: E402


class InstallerCommandSurfaceTests(unittest.TestCase):
    def test_execution_modules_use_runner_for_subprocess_run(self):
        execution_modules = {
            "imagesrc.py",
            "install.py",
            "plan.py",
            "system.py",
        }

        for filename in execution_modules:
            with self.subTest(filename=filename):
                tree = ast.parse((INSTALLER / filename).read_text())
                calls = []
                imports_runner = False
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module == "runner":
                        imports_runner = True
                    if isinstance(node, ast.ImportFrom) and node.module == ".runner":
                        imports_runner = True
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "subprocess"
                        and node.func.attr == "run"
                    ):
                        calls.append(node.lineno)

                self.assertFalse(calls, f"direct subprocess.run calls at {calls}")
                self.assertIn(
                    "from .runner import run_command",
                    (INSTALLER / filename).read_text(),
                )

    def test_discovery_modules_keep_subprocess_boundary_explicit(self):
        discovery_modules = {"disk.py"}
        for filename in discovery_modules:
            with self.subTest(filename=filename):
                text = (INSTALLER / filename).read_text()
                self.assertIn("subprocess", text)

    def test_install_progress_runner_is_module_level(self):
        tree = ast.parse((INSTALLER / "install.py").read_text())
        module_functions = {
            node.name for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        self.assertTrue(
            {
                "_run_cmd",
                "_prepare_install_context",
                "_prepare_install_storage",
                "_configure_installed_system",
                "_run_install_worker",
            }.issubset(module_functions)
        )

        run_install = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_run_install"
        )
        nested_functions = {
            node.name for node in run_install.body if isinstance(node, ast.FunctionDef)
        }
        self.assertNotIn("run_cmd", nested_functions)

        worker = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_run_install_worker"
        )
        self.assertLessEqual(worker.end_lineno - worker.lineno + 1, 60)

    def test_wipe_storage_phase_returns_root_context(self):
        logs = []
        progress = []

        with mock.patch.object(install, "_run_cmd") as run_cmd, \
             mock.patch.object(install, "run_command") as run_command, \
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
            )

        self.assertEqual((target_part, root_part, alongside_mount), ("", "/dev/sda3", ""))
        unmount_target_disk.assert_called_once_with("/dev/sda", logs.append)

    def test_storage_phase_returns_partition_context_for_non_wipe_modes(self):
        cases = ["alongside", "free-space", "resize-ntfs"]

        for mode in cases:
            with self.subTest(mode=mode):
                logs = []
                progress = []
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
                    )

                self.assertIsInstance(target_part, str)
                self.assertIsInstance(root_part, str)
                self.assertIsInstance(alongside_mount, str)

    def test_wipe_worker_reaches_done_event_with_mocked_side_effects(self):
        install._events.clear()
        install._state.update({
            "disk": "/dev/sda",
            "efi_partition": "",
            "hostname": "kyth",
            "install_mode": "wipe",
            "kernel": "/dev/sda2",
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
            install.Path,
            "mkdir",
        ):
            run_command.return_value.stdout = "UUID=abc\n"
            run_command.return_value.returncode = 0
            install._run_install_worker(lambda _msg: None, lambda _pct: None, "")

        self.assertTrue(any(event.get("type") == "done" for event in install._events))
        self.assertFalse([event for event in install._events if event.get("type") == "error"])

    def test_alongside_worker_cleans_temp_mount_after_error(self):
        install._events.clear()
        install._state.update({
            "disk": "/dev/sda",
            "efi_partition": "",
            "hostname": "kyth",
            "install_mode": "alongside",
            "kernel": "/dev/sda2",
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
            "run_command",
        ) as run_command, mock.patch.object(
            install,
            "_run_cmd",
            side_effect=RuntimeError("install failed"),
        ), mock.patch.object(
            install,
            "unmount_target_disk",
        ), mock.patch.object(
            install.Path,
            "mkdir",
        ):
            run_command.return_value.stdout = "UUID=abc\n"
            run_command.return_value.returncode = 0
            install._run_install_worker(lambda _msg: None, lambda _pct: None, "")

        cleanup_calls = [
            call
            for call in run_command.call_args_list
            if "/var/tmp/kyth-alongside-target" in repr(call)
        ]
        self.assertTrue(cleanup_calls)
        self.assertTrue([event for event in install._events if event.get("type") == "error"])


if __name__ == "__main__":
    unittest.main()
