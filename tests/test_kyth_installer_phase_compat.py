import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer import install  # noqa: E402
from kyth_installer.phases import compat, finalize_identity  # noqa: E402


class PhaseCompatibilityTests(unittest.TestCase):
    def test_facade_patch_is_resolved_dynamically(self):
        replacement = mock.MagicMock()
        with mock.patch.object(install, "run_command", replacement):
            self.assertIs(compat.phase_dependency("run_command"), replacement)

    def test_missing_facade_attribute_uses_canonical_provider(self):
        from kyth_installer import runner

        self.assertIs(compat._canonical_dependency("run_command"), runner.run_command)
        with self.assertRaisesRegex(AttributeError, "Unknown installer phase dependency"):
            compat.phase_dependency("does_not_exist")

    def test_identity_configuration_formats_os_errors(self):
        formatter = mock.MagicMock(return_value="formatted")
        with mock.patch.object(install, "run_command", side_effect=OSError("write")):
            with self.assertRaisesRegex(OSError, "formatted"):
                finalize_identity.configure_hostname_timezone(
                    "/etc", {"hostname": "kyth", "timezone": "UTC"}, mock.Mock(),
                    format_error=formatter,
                )
        formatter.assert_called_once()

    def test_identity_configuration_uses_typed_rust_executor(self):
        run = mock.MagicMock(return_value=mock.MagicMock(returncode=0))
        with (
            mock.patch.object(install, "run_command", run),
            mock.patch.object(install, "_as_root", side_effect=lambda command: command),
            mock.patch.object(
                finalize_identity.shutil,
                "which",
                return_value="/usr/bin/kyth-installer-exec",
            ),
        ):
            finalize_identity.configure_hostname_timezone(
                "/target/etc",
                {
                    "hostname": "kyth",
                    "timezone": "UTC",
                    "locale": "en_US.UTF-8",
                    "keymap": "us",
                },
                mock.Mock(),
                format_error=str,
            )
        self.assertEqual(
            run.call_args.args[0],
            ["kyth-installer-exec", "--operation", "configuration-write"],
        )
        payload = json.loads(run.call_args.kwargs["input"])
        self.assertEqual(payload["target_root"], "/target")
        self.assertEqual(payload["timezone"], "UTC")


if __name__ == "__main__":
    unittest.main()
