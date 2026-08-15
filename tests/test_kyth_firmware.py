import subprocess
import unittest
from unittest.mock import patch

from kyth_shared.system.firmware import (
    check_firmware_updates,
    firmware_refresh_commands,
    firmware_update_command,
    firmware_updates_command,
    run_firmware_refresh,
    run_firmware_update,
    stage_firmware_updates,
)


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


if __name__ == "__main__":
    unittest.main()
