import json
import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services.updates import (  # noqa: E402
    booted_image_digest,
    check_registry_update,
    firmware_check_commands,
)


class UpdateServiceTests(unittest.TestCase):
    def test_booted_image_digest_reads_nested_status(self):
        status = {
            "status": {
                "booted": {
                    "image": {
                        "imageDigest": "sha256:" + "1" * 64,
                    }
                }
            }
        }

        self.assertEqual(booted_image_digest(status), "sha256:" + "1" * 64)

    def test_check_registry_update_reports_uptodate_digest(self):
        digest = "sha256:" + "2" * 64
        status = {"status": {"booted": {"imageDigest": digest}}}
        manifest = {
            "manifests": [
                {
                    "digest": digest,
                    "platform": {"architecture": "amd64", "os": "linux"},
                }
            ]
        }

        def runner(ref):
            self.assertEqual(ref, "ghcr.io/example/os:stable")
            return subprocess.CompletedProcess([], 0, json.dumps(manifest).encode(), b"")

        result = check_registry_update(
            status_data=status,
            branch="stable",
            registry="ghcr.io/example/os",
            inspect_runner=runner,
        )

        self.assertEqual(result.state, "uptodate")

    def test_check_registry_update_reports_inspect_failure(self):
        status = {"status": {"booted": {"digest": "sha256:" + "3" * 64}}}

        def runner(_ref):
            return subprocess.CompletedProcess([], 1, b"", b"denied")

        result = check_registry_update(
            status_data=status,
            branch="stable",
            registry="ghcr.io/example/os",
            inspect_runner=runner,
        )

        self.assertEqual(result.state, "error")
        self.assertEqual(result.detail, "denied")

    def test_firmware_check_commands_refreshes_before_checking(self):
        self.assertEqual(
            firmware_check_commands(refresh=True),
            [["fwupdmgr", "refresh"], ["fwupdmgr", "get-updates"]],
        )


if __name__ == "__main__":
    unittest.main()
