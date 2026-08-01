import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED_ROOT = ROOT / "build_files/kyth_shared"
if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))

from kyth_shared.commands import CommandRunner
from kyth_shared.diagnostics import DiagnosticReporter
from kyth_shared.runtime_diagnostics import (
    check_deployment_rollback,
    check_services,
    deployment_id,
    is_live_image,
)


class AvailableReporter(DiagnosticReporter):
    def __init__(self, *commands: str):
        super().__init__("Test")
        self.commands = set(commands)

    def have(self, command: str) -> bool:
        return command in self.commands


def runner_for(results):
    def execute(command, **_kwargs):
        result = results.get(tuple(command), (1, "", "not mocked"))
        return subprocess.CompletedProcess(command, result[0], result[1], result[2])

    return CommandRunner(execute)


class RuntimeDiagnosticsTests(unittest.TestCase):
    def test_live_image_reads_tokenized_kernel_command_line(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cmdline = Path(temp_dir) / "cmdline"
            cmdline.write_text("quiet kyth.live rd.systemd.show_status=false", encoding="utf-8")
            self.assertTrue(is_live_image(cmdline))

    def test_deployment_id_prefers_booted_bootc_digest(self):
        reporter = AvailableReporter("bootc")
        runner = runner_for({
            ("bootc", "status", "--format", "json"): (
                0,
                '{"status":{"booted":{"image":{"imageDigest":"sha256:abc"}}}}',
                "",
            ),
        })
        self.assertEqual(deployment_id(reporter, runner), "sha256:abc")

    def test_deployment_check_reports_missing_tool_as_failure(self):
        failures, warnings = check_deployment_rollback(AvailableReporter())
        self.assertEqual(failures, ["No deployment tool found."])
        self.assertEqual(warnings, [])

    def test_service_probe_handles_user_and_system_managers(self):
        reporter = AvailableReporter("systemctl")
        runner = runner_for({
            ("systemctl", "--user", "is-active", "pipewire.service"): (0, "", ""),
            ("systemctl", "is-active", "bluetooth.service"): (3, "", ""),
        })
        check_services(
            reporter,
            (("pipewire.service", True), ("bluetooth.service", False)),
            runner,
        )
        self.assertEqual(
            [result[:2] for result in reporter.results],
            [("PASS", "PipeWire"), ("WARN", "Bluetooth service")],
        )


if __name__ == "__main__":
    unittest.main()
