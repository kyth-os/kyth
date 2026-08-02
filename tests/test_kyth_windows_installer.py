"""Windows installer inspection and seamless Bottles workflow tests."""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.desktop.windows_installer import (  # noqa: E402
    BOTTLES_ID,
    Compatibility,
    InstallerKind,
    WindowsInstallerWorkflow,
    WorkflowFailure,
    WorkflowFailureKind,
    assess_compatibility,
    bottle_names,
    bottles_cli,
    inspect_installer,
    plan_bottle,
    stage_installer,
)


def _write_pe(path: pathlib.Path, machine: int = 0x8664) -> None:
    data = bytearray(0x86)
    data[:2] = b"MZ"
    data[0x3C:0x40] = (0x80).to_bytes(4, "little")
    data[0x80:0x84] = b"PE\0\0"
    data[0x84:0x86] = machine.to_bytes(2, "little")
    path.write_bytes(data)


class FakeRunner:
    def __init__(
        self,
        *,
        installed: bool,
        bottles: list[str] | None = None,
        fail_on: str | None = None,
        fail_spawn: bool = False,
    ) -> None:
        self.installed = installed
        self.bottles = bottles or []
        self.fail_on = fail_on
        self.fail_spawn = fail_spawn
        self.commands: list[list[str]] = []
        self.spawned: list[tuple[list[str], dict]] = []

    def run(self, command, **_kwargs):
        command = list(command)
        self.commands.append(command)
        if self.fail_on and self.fail_on in command:
            return subprocess.CompletedProcess(command, 1, "", "simulated failure")
        if command[:2] == ["flatpak", "info"]:
            return subprocess.CompletedProcess(command, 0 if self.installed else 1, "", "")
        if command == bottles_cli("--json", "list", "bottles"):
            return subprocess.CompletedProcess(command, 0, str(self.bottles).replace("'", '"'), "")
        if "install" in command:
            self.installed = True
        return subprocess.CompletedProcess(command, 0, "", "")

    def spawn(self, command, **kwargs):
        command = list(command)
        self.spawned.append((command, kwargs))
        if self.fail_spawn:
            raise OSError("simulated launch failure")
        return object()


class InstallerInspectionTests(unittest.TestCase):
    def test_validates_pe_content_and_architecture(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "Example Setup.exe"
            _write_pe(path)
            request = inspect_installer(path)
            self.assertEqual(InstallerKind.EXE, request.kind)
            self.assertEqual("win64", request.architecture)
            self.assertEqual(64, len(request.sha256))

    def test_validates_msi_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "Example.msi"
            path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 64)
            request = inspect_installer(path)
            self.assertEqual(InstallerKind.MSI, request.kind)

    def test_rejects_extension_only_fake_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            fake = root / "fake.exe"
            fake.write_text("not a Windows program", encoding="utf-8")
            with self.assertRaisesRegex(WorkflowFailure, "valid Windows executable"):
                inspect_installer(fake)
            link = root / "linked.exe"
            link.symlink_to(fake)
            with self.assertRaisesRegex(WorkflowFailure, "non-symbolic-link"):
                inspect_installer(link)

    def test_marks_arm_and_system_components_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            arm = root / "Example.exe"
            _write_pe(arm, 0xAA64)
            self.assertEqual(
                Compatibility.UNSUPPORTED,
                assess_compatibility(inspect_installer(arm)).level,
            )
            driver = root / "Device Driver Setup.exe"
            _write_pe(driver)
            self.assertEqual(
                Compatibility.UNSUPPORTED,
                assess_compatibility(inspect_installer(driver)).level,
            )

    def test_bottle_plan_is_stable_and_selects_gaming_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "Game Launcher Setup.exe"
            _write_pe(path)
            request = inspect_installer(path)
            first = plan_bottle(request)
            self.assertEqual(first, plan_bottle(request))
            self.assertEqual("gaming", first.environment)
            self.assertRegex(first.name, r"^Kyth-game-launcher-[0-9a-f]{8}$")

    def test_staging_detects_source_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = root / "Example.exe"
            _write_pe(path)
            request = inspect_installer(path)
            path.write_bytes(path.read_bytes() + b"changed")
            with self.assertRaises(WorkflowFailure) as caught:
                stage_installer(request, root / "home")
            self.assertEqual(WorkflowFailureKind.FILE_CHANGED, caught.exception.kind)

    def test_staging_uses_bottles_private_flatpak_cache_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = root / "Example Setup.exe"
            _write_pe(path)
            request = inspect_installer(path)

            staged = stage_installer(request, root / "home")

            expected_parent = (
                root
                / "home"
                / ".var"
                / "app"
                / BOTTLES_ID
                / "cache"
                / "kyth-installers"
                / request.sha256[:16]
            )
            self.assertEqual(expected_parent / path.name, staged.host_path)
            self.assertEqual(staged.host_path, staged.sandbox_path)


class BottlesWorkflowTests(unittest.TestCase):
    def test_bottle_list_parser_handles_supported_shapes(self):
        self.assertEqual({"One", "Two"}, bottle_names('["One", "Two"]'))
        self.assertEqual({"One"}, bottle_names('[{"Name": "One"}]'))
        self.assertEqual({"One"}, bottle_names('{"bottles": {"One": {}}}'))

    def test_missing_bottles_is_installed_and_original_request_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            home = root / "home"
            home.mkdir()
            path = root / "Example Setup.exe"
            _write_pe(path)
            request = inspect_installer(path)
            runner = FakeRunner(installed=False)
            progress: list[str] = []

            result = WindowsInstallerWorkflow(runner, home=home).execute(request, progress.append)

            self.assertTrue(runner.installed)
            self.assertTrue(result.staged.host_path.is_file())
            self.assertIn("Preparing Flathub…", progress)
            self.assertIn("Installing Bottles…", progress)
            self.assertIn("Opening the Windows installer…", progress)
            self.assertTrue(any(command[:3] == ["flatpak", "remote-add", "--if-not-exists"] for command in runner.commands))
            self.assertTrue(any(command[:2] == ["flatpak", "install"] for command in runner.commands))
            self.assertEqual(1, len(runner.spawned))
            launch, kwargs = runner.spawned[0]
            self.assertEqual(bottles_cli("run", "-b", result.bottle.name, "-e", str(result.staged.sandbox_path)), launch)
            self.assertTrue(kwargs["start_new_session"])

    def test_existing_bottle_skips_install_and_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            home = root / "home"
            home.mkdir()
            path = root / "Example.exe"
            _write_pe(path)
            request = inspect_installer(path)
            plan = plan_bottle(request)
            runner = FakeRunner(installed=True, bottles=[plan.name])

            WindowsInstallerWorkflow(runner, home=home).execute(request)

            flattened = [part for command in runner.commands for part in command]
            self.assertNotIn("install", flattened)
            self.assertNotIn("new", flattened)
            self.assertEqual(1, len(runner.spawned))

    def test_install_failure_is_classified_for_actionable_ui(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = root / "Example.exe"
            _write_pe(path)
            runner = FakeRunner(installed=False, fail_on="install")

            with self.assertRaises(WorkflowFailure) as caught:
                WindowsInstallerWorkflow(runner, home=root / "home").execute(
                    inspect_installer(path)
                )

            self.assertEqual(
                WorkflowFailureKind.BOTTLES_INSTALL,
                caught.exception.kind,
            )

    def test_launch_failure_is_classified_for_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            path = root / "Example.exe"
            _write_pe(path)
            request = inspect_installer(path)
            runner = FakeRunner(
                installed=True,
                bottles=[plan_bottle(request).name],
                fail_spawn=True,
            )

            with self.assertRaises(WorkflowFailure) as caught:
                WindowsInstallerWorkflow(runner, home=root / "home").execute(request)

            self.assertEqual(WorkflowFailureKind.LAUNCH, caught.exception.kind)


if __name__ == "__main__":
    unittest.main()
