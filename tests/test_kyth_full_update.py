"""Contract tests for the KythOS-owned full updater."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "build_files" / "kyth-full-update"


class FullUpdateTests(unittest.TestCase):
    def test_full_updater_is_executable_shell_script(self):
        self.assertTrue(SCRIPT.stat().st_mode & 0o111)
        self.assertTrue(SCRIPT.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash\n"))

    def test_full_updater_limits_scope_to_owned_surfaces(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for expected in ("fwupdmgr", "flatpak update", "kyth-safe-upgrade", "kyth-rclone-update"):
            self.assertIn(expected, source)
        for excluded in ("pipx", "pip3", "npm ", "code --", "gh extension", "topgrade"):
            self.assertNotIn(excluded, source)

    def test_only_core_update_failures_are_fatal(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('run_step critical "Flatpak user packages"', source)
        self.assertIn('run_step critical "Flatpak system packages"', source)
        self.assertIn('run_step critical "KythOS system image"', source)
        self.assertIn('run_step optional "Firmware upgrades"', source)
        self.assertIn('run_step optional "KythOS rclone"', source)

    def test_firmware_steps_flock_the_shared_fwupd_lock(self):
        """kyth-update-watcher's stage_firmware_batch() and the Hub's firmware
        button both take /run/kyth-fwupd.lock — a manual `kyth-full-update`
        run must take the same lock or it can fire a concurrent fwupdmgr
        write against a device the watcher is mid-flashing on.
        """
        source = SCRIPT.read_text(encoding="utf-8")
        for expected in (
            'run_step optional "Firmware metadata" flock -w 60 /run/kyth-fwupd.lock sudo -n /usr/bin/fwupdmgr refresh --force',
            'run_step optional "Firmware upgrades" flock -w 60 /run/kyth-fwupd.lock sudo -n /usr/bin/fwupdmgr update --assume-yes --no-reboot-check',
        ):
            self.assertIn(expected, source)


if __name__ == "__main__":
    unittest.main()
