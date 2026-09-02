import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kyth_shared.system.firmware import (
    check_firmware_updates,
    firmware_refresh_commands,
    firmware_update_command,
    firmware_updates_command,
    run_firmware_refresh,
    run_firmware_update,
    stage_firmware_batch,
    stage_firmware_updates,
)

ROOT = Path(__file__).resolve().parents[1]


class FirmwareCommandsTests(unittest.TestCase):
    def test_refresh_commands(self):
        self.assertEqual(firmware_refresh_commands(), [["fwupdmgr", "refresh", "--force"]])

    def test_updates_command(self):
        self.assertEqual(firmware_updates_command(), ["fwupdmgr", "get-updates"])

    def test_update_command(self):
        self.assertEqual(firmware_update_command(), ["fwupdmgr", "update", "--assume-yes", "--no-reboot-check"])


class RunFirmwareRefreshTests(unittest.TestCase):
    def test_ok(self):
        with patch("kyth_shared.system.firmware.subprocess.run") as mr:
            mr.return_value = subprocess.CompletedProcess(args=["fwupdmgr"], returncode=0, stdout="ok", stderr="")
            ok, out = run_firmware_refresh()
            self.assertTrue(ok)
            self.assertIn("ok", out)

    def test_missing(self):
        with patch("kyth_shared.system.firmware.subprocess.run", side_effect=FileNotFoundError):
            ok, out = run_firmware_refresh()
            self.assertFalse(ok)
            self.assertIn("not found", out.lower())

    def test_timeout(self):
        with patch("kyth_shared.system.firmware.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="fwupdmgr", timeout=60)):
            ok, out = run_firmware_refresh()
            self.assertFalse(ok)
            self.assertIn("timed out", out.lower())


class CheckFirmwareUpdatesTests(unittest.TestCase):
    def test_counts_device_ids(self):
        with patch("kyth_shared.system.firmware.subprocess.run") as mr:
            mr.return_value = subprocess.CompletedProcess(args=["fwupdmgr"], returncode=0, stdout="Device ID: a\nDevice ID: b\n", stderr="")
            self.assertEqual(check_firmware_updates(), 2)

    def test_returncode_2_means_no_updates(self):
        with patch("kyth_shared.system.firmware.subprocess.run") as mr:
            mr.return_value = subprocess.CompletedProcess(args=["fwupdmgr"], returncode=2, stdout="", stderr="")
            self.assertEqual(check_firmware_updates(), 0)

    def test_empty_stdout_means_no_updates(self):
        with patch("kyth_shared.system.firmware.subprocess.run") as mr:
            mr.return_value = subprocess.CompletedProcess(args=["fwupdmgr"], returncode=0, stdout="  \n", stderr="")
            self.assertEqual(check_firmware_updates(), 0)

    def test_nonzero_other_means_no_updates(self):
        with patch("kyth_shared.system.firmware.subprocess.run") as mr:
            mr.return_value = subprocess.CompletedProcess(args=["fwupdmgr"], returncode=1, stdout="error", stderr="")
            self.assertEqual(check_firmware_updates(), 0)

    def test_missing_binary(self):
        with patch("kyth_shared.system.firmware.subprocess.run", side_effect=FileNotFoundError):
            self.assertEqual(check_firmware_updates(), 0)


class RunFirmwareUpdateTests(unittest.TestCase):
    def test_ok(self):
        with patch("kyth_shared.system.firmware.subprocess.run") as mr:
            mr.return_value = subprocess.CompletedProcess(args=["fwupdmgr"], returncode=0, stdout="queued", stderr="")
            ok, _out = run_firmware_update()
            self.assertTrue(ok)

    def test_timeout(self):
        with patch("kyth_shared.system.firmware.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="fwupdmgr", timeout=600)):
            ok, _out = run_firmware_update()
            self.assertFalse(ok)


class StageFirmwareUpdatesTests(unittest.TestCase):
    def test_stages_when_pending(self):
        with patch("kyth_shared.system.firmware.run_firmware_refresh", return_value=(True, "")) as rf, \
             patch("kyth_shared.system.firmware.check_firmware_updates", return_value=2) as cf, \
             patch("kyth_shared.system.firmware.run_firmware_update", return_value=(True, "queued")) as ru:
            updated, count, out = stage_firmware_updates()
            self.assertTrue(updated)
            self.assertEqual(count, 2)
            self.assertEqual(out, "queued")
            rf.assert_called_once()
            cf.assert_called_once()
            ru.assert_called_once()

    def test_no_stage_when_none_pending(self):
        with patch("kyth_shared.system.firmware.run_firmware_refresh", return_value=(True, "")), \
             patch("kyth_shared.system.firmware.check_firmware_updates", return_value=0), \
             patch("kyth_shared.system.firmware.run_firmware_update") as ru:
            updated, count, _out = stage_firmware_updates()
            self.assertFalse(updated)
            self.assertEqual(count, 0)
            ru.assert_not_called()


class StageFirmwareBatchTests(unittest.TestCase):
    """stage_firmware_batch() is the thundering-herd guard: kyth-update-watcher,
    kyth-full-update (via flock), and the Hub's firmware button all need to
    agree on one /run/kyth-fwupd.lock so two callers never fwupdmgr-write the
    same device concurrently.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._lock_path = str(Path(self._tmpdir.name) / "fwupd.lock")

    def test_contended_lock_skips_without_running_batch(self):
        with patch("kyth_shared.system.firmware.stage_firmware_updates") as su, \
             patch("fcntl.flock", side_effect=OSError):
            updated, count, out = stage_firmware_batch(lock_path=self._lock_path)
            self.assertFalse(updated)
            self.assertEqual(count, 0)
            self.assertEqual(out, "")
            su.assert_not_called()

    def test_acquired_lock_runs_batch(self):
        with patch("kyth_shared.system.firmware.stage_firmware_updates", return_value=(True, 1, "queued")) as su:
            updated, count, out = stage_firmware_batch(lock_path=self._lock_path)
            self.assertTrue(updated)
            self.assertEqual(count, 1)
            self.assertEqual(out, "queued")
            su.assert_called_once()

    def test_default_lock_path_is_the_shared_run_path(self):
        # Every caller (kyth-update-watcher, kyth-full-update, the Hub button)
        # must resolve to this exact path or the lock does not actually
        # serialize them against each other.
        source = (ROOT / "build_files" / "kyth_shared" / "kyth_shared" / "system" / "firmware.py").read_text(encoding="utf-8")
        self.assertIn('"/run/kyth-fwupd.lock"', source)


class FwupdLockPreCreationTests(unittest.TestCase):
    def test_tmpfiles_precreates_the_lock_world_readable(self):
        """flock(2) only needs an open fd, not write access, but /run itself
        is not world-writable for *creating* new files — so an unprivileged
        caller (Hub button, kyth-full-update) can only flock the shared lock
        if it already exists. Must be recreated every boot since /run is tmpfs.
        """
        source = (ROOT / "build_files" / "scripts" / "branding" / "27-performance-daemons.sh").read_text(encoding="utf-8")
        self.assertIn("/usr/lib/tmpfiles.d/kyth-fwupd-lock.conf", source)
        self.assertIn("f /run/kyth-fwupd.lock 0644 root root -", source)


class FullUpdateAndHubUseTheSharedLockTests(unittest.TestCase):
    def test_kyth_full_update_flocks_before_sudo_fwupdmgr(self):
        source = (ROOT / "build_files" / "kyth-full-update").read_text(encoding="utf-8")
        self.assertIn("flock -w 60 /run/kyth-fwupd.lock sudo -n /usr/bin/fwupdmgr refresh --force", source)
        self.assertIn("flock -w 60 /run/kyth-fwupd.lock sudo -n /usr/bin/fwupdmgr update --assume-yes --no-reboot-check", source)


if __name__ == "__main__":
    unittest.main()
