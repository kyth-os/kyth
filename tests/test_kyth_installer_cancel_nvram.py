import unittest
from unittest import mock  # pylint: disable=unused-import
from kyth_installer.context import InstallerContext, InstallLifecycle
from kyth_installer import execution
from kyth_installer.install import _warn_if_efi_boot_entries_disappeared


class InstallerCancelTests(unittest.TestCase):
    def test_request_cancel_fails_when_idle(self):
        ctx = InstallerContext()
        self.assertFalse(execution.request_cancel(ctx))
        self.assertFalse(ctx.cancel_requested.is_set())

    def test_request_cancel_succeeds_when_installing(self):
        ctx = InstallerContext()
        ctx.install_lock.acquire()
        ctx.lifecycle = InstallLifecycle.INSTALLING
        try:
            self.assertTrue(execution.request_cancel(ctx))
            self.assertTrue(ctx.cancel_requested.is_set())
            self.assertTrue(any(e["type"] == "log" and "Cancellation" in e["text"] for e in ctx.events.events))
        finally:
            ctx.install_lock.release()
            ctx.cancel_requested.clear()
            ctx.lifecycle = InstallLifecycle.IDLE

    def test_check_cancelled_raises(self):
        ctx = InstallerContext()
        ctx.cancel_requested.set()
        with self.assertRaises(execution.InstallCancelled) as raised:
            execution.check_cancelled(ctx)
        self.assertIn("before disk changes were committed", str(raised.exception))

    def test_check_cancelled_after_storage_mentions_disk_changes(self):
        from kyth_installer.context import InstallPhase
        ctx = InstallerContext()
        ctx.phase = InstallPhase.IMAGE
        ctx.cancel_requested.set()
        with self.assertRaises(execution.InstallCancelled) as raised:
            execution.check_cancelled(ctx)
        self.assertIn("Disk changes may have already started", str(raised.exception))

    def test_nvram_warns_when_entry_lost_without_aborting(self):
        logs = []
        before = "Boot0001* Windows Boot Manager\nBoot0002* KythOS\n"
        after = "Boot0002* KythOS\n"
        _warn_if_efi_boot_entries_disappeared(before, after, logs.append)
        self.assertTrue(any("Windows Boot Manager" in m for m in logs))

    def test_nvram_no_warning_when_same(self):
        logs = []
        text = "Boot0001* Windows Boot Manager\n"
        _warn_if_efi_boot_entries_disappeared(text, text, logs.append)
        self.assertEqual(logs, [])

    def test_nvram_no_warning_when_empty(self):
        logs = []
        _warn_if_efi_boot_entries_disappeared("", "", logs.append)
        self.assertEqual(logs, [])
