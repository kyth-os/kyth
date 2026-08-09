"""S16: stability banner gate — enforces update-safety always leave a way back."""
import unittest
from kyth_shared.system.recovery_status import RecoveryStatus, recovery_banner

class StabilityBannerTests(unittest.TestCase):
    def test_banner_covers_all_combos(self):
        for staged in (False, True):
            for rollback in (False, True):
                for quarantined in ("", "abc123"):
                    s = RecoveryStatus(has_staged=staged, has_rollback=rollback, quarantined_digest=quarantined)
                    banner = recovery_banner(s)
                    self.assertIsInstance(banner, str)
                    self.assertTrue(banner)

    def test_quarantined_requires_clear_retry(self):
        s = RecoveryStatus(has_staged=False, has_rollback=False, quarantined_digest="abc")
        self.assertIn("clear-quarantine", recovery_banner(s))

    def test_rollback_available_when_no_staged(self):
        s = RecoveryStatus(has_staged=False, has_rollback=True, quarantined_digest="")
        self.assertEqual(recovery_banner(s), "rollback available")
# S16 distinct commit marker
