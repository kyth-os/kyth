"""Shared stream-contract cases for the Rust model and Python executor."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer.streaming import StreamingCommandRunner  # noqa: E402


FIXTURE = ROOT / "src" / "kyth-installer-web" / "src-tauri" / "testdata" / "stream_cases.json"


class InstallerStreamParityTests(unittest.TestCase):
    def test_python_executor_matches_shared_stream_cases(self):
        for case in json.loads(FIXTURE.read_text(encoding="utf-8")):
            logs: list[str] = []
            chunks = case["chunks_hex"]
            script = "import sys;" + ";".join(
                f"sys.stdout.buffer.write(bytes.fromhex({chunk!r})); sys.stdout.flush()"
                for chunk in chunks
            )
            if case["exit_code"]:
                script += f";sys.exit({case['exit_code']})"
            runner = StreamingCommandRunner(rx_bytes=lambda: 0, publish=lambda _event: None)
            with self.subTest(case=case["name"]), mock.patch(
                "kyth_installer.runner._validate_executable", side_effect=lambda value: value
            ):
                if case["exit_code"]:
                    with self.assertRaisesRegex(RuntimeError, r"Command failed \(exit 2\)") as raised:
                        runner.run(
                            [sys.executable, "-c", script],
                            0,
                            100,
                            logs.append,
                            lambda _progress: None,
                        )
                    for needle in case["expected_error_contains"]:
                        self.assertIn(needle, str(raised.exception))
                    for needle in case["expected_error_excludes"]:
                        self.assertNotIn(needle, str(raised.exception))
                else:
                    runner.run(
                        [sys.executable, "-c", script],
                        0,
                        100,
                        logs.append,
                        lambda _progress: None,
                    )
                self.assertEqual(
                    [line for line in logs if not line.startswith("$ ")],
                    case["expected_python_events"],
                )


if __name__ == "__main__":
    unittest.main()
