"""ISO publish (publish-release.py) must be idempotent.

build-live-iso cancels in progress, so a superseded run's publish job can
create the immutable release moments before the replacement run reaches
the same step. The replacement used to die on `gh release create`
("already exists") and take the whole ISO publish down with it
(2026-10-12). These tests drive main() with a recording run_command
stand-in and pin the convergent behavior.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "build_files/scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("publish_release", SCRIPTS / "publish-release.py")
assert SPEC and SPEC.loader
publish_release = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = publish_release
SPEC.loader.exec_module(publish_release)


def _completed(returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr="")


class RecordingRunner:
    """Stands in for run_command; records argv, answers `release view`."""

    def __init__(self, immutable_exists: bool):
        self.immutable_exists = immutable_exists
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        self.calls.append(list(args))
        if args[:3] == ["gh", "release", "view"]:
            return _completed(0 if self.immutable_exists else 1)
        return _completed(0)

    def find(self, *prefix: str) -> list[list[str]]:
        return [c for c in self.calls if c[: len(prefix)] == list(prefix)]


class IsoPublishIdempotencyTests(unittest.TestCase):
    def run_main(self, runner: RecordingRunner) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            changelog = tmp_path / "changelog.md"
            changelog.write_text("notes", encoding="utf-8")
            argv = [
                "publish-release.py",
                "--repo", "kyth-os/kyth",
                "--source-tag", "testing",
                "--channel-tag", "iso-testing",
                "--immutable-tag", "iso-testing-20261012-abcdef0-948-1",
                "--release-id", "20261012-abcdef0-948-1",
                "--source-sha", "a" * 40,
                "--source-digest", "sha256:" + "b" * 64,
                "--attestation-url", "",
                "--iso-basename", "kyth-live-testing.iso",
                "--channel-basename", "kyth-live-testing.iso",
                "--iso-changelog", str(changelog),
                "--source-dir", str(tmp_path),
                "--run-id", "123",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                publish_release, "run_command", runner
            ), mock.patch.object(Path, "cwd", return_value=tmp_path):
                # Notes files are written next to the CWD; run inside tmp.
                import os

                old_cwd = os.getcwd()
                os.chdir(tmp)
                try:
                    self.assertEqual(publish_release.main(), 0)
                finally:
                    os.chdir(old_cwd)

    def test_existing_immutable_release_is_edited_not_recreated(self):
        runner = RecordingRunner(immutable_exists=True)
        self.run_main(runner)
        self.assertEqual(runner.find("gh", "release", "create", "iso-testing-20261012-abcdef0-948-1"), [])
        edits = runner.find("gh", "release", "edit", "iso-testing-20261012-abcdef0-948-1")
        self.assertEqual(len(edits), 1)
        self.assertIn("--notes-file", edits[0])

    def test_missing_immutable_release_is_created(self):
        runner = RecordingRunner(immutable_exists=False)
        self.run_main(runner)
        creates = runner.find("gh", "release", "create", "iso-testing-20261012-abcdef0-948-1")
        self.assertEqual(len(creates), 1)
        self.assertEqual(runner.find("gh", "release", "edit"), [])

    def test_immutable_upload_clobbers_so_reruns_converge(self):
        runner = RecordingRunner(immutable_exists=True)
        self.run_main(runner)
        uploads = runner.find("gh", "release", "upload", "iso-testing-20261012-abcdef0-948-1")
        self.assertEqual(len(uploads), 1)
        self.assertIn("--clobber", uploads[0])


class RunCommandDiagnosticsTests(unittest.TestCase):
    def test_failure_surfaces_gh_stderr_before_raising(self):
        fake = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="release already exists"
        )
        with mock.patch.object(publish_release.subprocess, "run", return_value=fake):
            with self.assertRaises(subprocess.CalledProcessError):
                publish_release.run_command(["gh", "release", "create", "x"])

    def test_unchecked_failure_returns_result(self):
        fake = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="nope")
        with mock.patch.object(publish_release.subprocess, "run", return_value=fake):
            result = publish_release.run_command(["gh", "release", "view", "x"], check=False)
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
