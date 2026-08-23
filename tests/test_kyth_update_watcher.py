import importlib.util
from importlib.machinery import SourceFileLoader
import subprocess  # nosec B404 # nosemgrep
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _load_update_watcher():
    path = Path(__file__).resolve().parents[1] / "build_files" / "kyth-update-watcher"
    loader = SourceFileLoader("kyth_update_watcher", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UpdateWatcherMeteredTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.watcher = _load_update_watcher()

    def _check_metered_for_nm_value(self, value: int):
        result = subprocess.CompletedProcess(  # nosemgrep
            args=["busctl"],
            returncode=0,
            stdout=f"u {value}\n",
            stderr="",
        )
        with patch.object(self.watcher.subprocess, "run", return_value=result):
            return self.watcher.check_metered({"skip_if_metered": True})

    def test_explicit_and_guessed_metered_values_skip_updates(self):
        self.assertEqual(self._check_metered_for_nm_value(1), "network connection is metered")
        self.assertEqual(self._check_metered_for_nm_value(3), "network connection is metered")

    def test_unmetered_values_do_not_skip_updates(self):
        self.assertIsNone(self._check_metered_for_nm_value(2))
        self.assertIsNone(self._check_metered_for_nm_value(4))


class UpdateWatcherOptimizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.watcher = _load_update_watcher()

    def test_get_bootc_image_reference(self):
        status_data = {
            "status": {
                "booted": {
                    "image": {
                        "reference": "ghcr.io/kyth-os/kyth:latest"
                    }
                }
            }
        }
        self.assertEqual(
            self.watcher.get_bootc_image_reference(status_data),
            "ghcr.io/kyth-os/kyth:latest"
        )

    def test_get_bootc_image_reference_spec_fallback(self):
        status_data = {
            "spec": {
                "image": {
                    "image": "ghcr.io/kyth-os/kyth:testing"
                }
            }
        }
        self.assertEqual(
            self.watcher.get_bootc_image_reference(status_data),
            "ghcr.io/kyth-os/kyth:testing"
        )

    @patch("subprocess.run")
    def test_get_remote_digest_v1(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=b'{"mediaType": "application/vnd.oci.image.manifest.v1+json", "annotations": {"foo": "bar"}}',
            stderr=b""
        )
        import hashlib
        expected = "sha256:" + hashlib.sha256(mock_run.return_value.stdout).hexdigest()
        self.assertEqual(
            self.watcher.get_remote_digest("ghcr.io/kyth-os/kyth:latest"),
            expected
        )

    @patch("subprocess.run")
    def test_get_remote_digest_multiarch(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=b'{"manifests": [{"platform": {"architecture": "amd64", "os": "linux"}, "digest": "sha256:1111111111111111111111111111111111111111111111111111111111111111"}]}',
            stderr=b""
        )
        self.assertEqual(
            self.watcher.get_remote_digest("ghcr.io/kyth-os/kyth:latest"),
            "sha256:1111111111111111111111111111111111111111111111111111111111111111"
        )

    def test_quarantined_remote_digest_is_not_staged(self):
        remote_digest = "sha256:" + "a" * 64
        status = {
            "status": {
                "booted": {
                    "image": {
                        "reference": "ghcr.io/kyth-os/kyth:testing",
                        "imageDigest": "sha256:" + "b" * 64,
                    }
                }
            }
        }
        quarantine = SimpleNamespace(
            quarantined={
                remote_digest: SimpleNamespace(
                    failures=3, reason="greenboot required check failed"
                )
            }
        )

        with (
            patch.object(self.watcher.os, "geteuid", return_value=0),
            patch.object(self.watcher, "check_startup_grace", return_value=None),
            patch.object(self.watcher, "check_quiet_hours", return_value=None),
            patch.object(self.watcher, "check_gaming", return_value=None),
            patch.object(self.watcher, "check_metered", return_value=None),
            patch.object(self.watcher, "check_flatpak_updates", return_value=0),
            # poll() consults this 90s on-disk cache BEFORE get_bootc_status(), and
            # a fresh entry left by an earlier test/run would make it win over the
            # fixture below — force a miss so get_bootc_status() is what's exercised.
            patch.object(self.watcher, "bootc_status_data_cached", return_value=None),
            patch.object(self.watcher, "flatpak_updates_cached", return_value=0),
            patch.object(self.watcher, "get_bootc_status", return_value=status),
            patch.object(self.watcher, "get_remote_digest", return_value=remote_digest),
            patch.object(self.watcher, "read_boot_health_state", return_value=quarantine),
            patch.object(self.watcher, "write_status") as write_status,
            patch.object(self.watcher, "run_bootc_upgrade") as upgrade,
            # poll() also WRITES this status back to the real, shared, on-disk
            # cache (/var/cache/kyth/probe-cache.json when run as root) — block
            # that too, or this run leaves state that poisons the next one.
            patch("kyth_shared.system.probe.update_sections"),
        ):
            result = self.watcher.UpdateWatcherDaemon().run()

        self.assertEqual(result, 0)
        upgrade.assert_not_called()
        self.assertEqual(write_status.call_args.args[0], "quarantined")

    @patch("subprocess.run")
    @patch("sys.exit")
    def test_main_skips_when_staged_matches_remote(self, mock_exit, mock_run):
        status_json = b'{"status": {"booted": {"image": {"reference": "ghcr.io/kyth-os/kyth:latest", "imageDigest": "sha256:booted"}}, "staged": {"image": {"imageDigest": "sha256:latest"}}}}'
        manifest_json = b'{"manifests": [{"platform": {"architecture": "amd64", "os": "linux"}, "digest": "sha256:latest"}]}'
        
        def run_side_effect(args, **kwargs):
            if "bootc" in args and "status" in args:
                return subprocess.CompletedProcess(args, 0, status_json, b"")
            if "skopeo" in args:
                return subprocess.CompletedProcess(args, 0, manifest_json, b"")
            if "flatpak" in args:
                return subprocess.CompletedProcess(args, 0, b"", b"")
            return subprocess.CompletedProcess(args, 0, b"", b"")
            
        mock_run.side_effect = run_side_effect
        mock_exit.side_effect = SystemExit
        
        with patch.object(self.watcher, "write_status") as mock_write_status, \
             patch.object(self.watcher, "_notify_updates") as mock_notify, \
             patch.object(self.watcher, "check_startup_grace", return_value=None), \
             patch.object(self.watcher, "check_quiet_hours", return_value=None), \
             patch.object(self.watcher, "os") as mock_os, \
             patch.object(self.watcher, "bootc_status_data_cached", return_value=None), \
             patch("kyth_shared.system.probe.update_sections"):
            mock_os.geteuid.return_value = 0
            with self.assertRaises(SystemExit):
                self.watcher.main()

            mock_write_status.assert_called_once_with(
                "no_change",
                "Update already staged and matches latest registry version",
                "",
                unittest.mock.ANY,
                0
            )
            mock_notify.assert_called_once_with(os_staged=True, flatpak_count=0)
            mock_exit.assert_called_once_with(0)

    @patch("subprocess.run")
    @patch("sys.exit")
    def test_main_skips_when_booted_matches_remote(self, mock_exit, mock_run):
        status_json = b'{"status": {"booted": {"image": {"reference": "ghcr.io/kyth-os/kyth:latest", "imageDigest": "sha256:latest"}}}}'
        manifest_json = b'{"manifests": [{"platform": {"architecture": "amd64", "os": "linux"}, "digest": "sha256:latest"}]}'
        
        def run_side_effect(args, **kwargs):
            if "bootc" in args and "status" in args:
                return subprocess.CompletedProcess(args, 0, status_json, b"")
            if "skopeo" in args:
                return subprocess.CompletedProcess(args, 0, manifest_json, b"")
            if "flatpak" in args:
                return subprocess.CompletedProcess(args, 0, b"", b"")
            return subprocess.CompletedProcess(args, 0, b"", b"")
            
        mock_run.side_effect = run_side_effect
        mock_exit.side_effect = SystemExit
        
        with patch.object(self.watcher, "write_status") as mock_write_status, \
             patch.object(self.watcher, "_notify_updates") as mock_notify, \
             patch.object(self.watcher, "check_startup_grace", return_value=None), \
             patch.object(self.watcher, "check_quiet_hours", return_value=None), \
             patch.object(self.watcher, "os") as mock_os, \
             patch.object(self.watcher, "bootc_status_data_cached", return_value=None), \
             patch("kyth_shared.system.probe.update_sections"):
            mock_os.geteuid.return_value = 0
            with self.assertRaises(SystemExit):
                self.watcher.main()

            mock_write_status.assert_called_once_with(
                "no_change",
                None,
                "Already up to date",
                unittest.mock.ANY,
                0
            )
            mock_notify.assert_not_called()
            mock_exit.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
