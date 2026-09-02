import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_welcome.services.updates import UpdateCheckCoordinator, UpdateProbeResult

class UpdateTimeoutRegressionTests(unittest.TestCase):
    def test_coordinator_timeout_partial(self):
        c = UpdateCheckCoordinator()
        c.begin()
        c.accept(UpdateProbeResult.success("flatpak", value=2, detail=""))
        self.assertTrue(c.has_partial())
        r = c.as_result(timeout_detail="Check timed out — showing partial result.")
        self.assertEqual(r.system_state, "error")
        self.assertIn("timed out", r.system_detail.lower())

    def test_coordinator_timeout_both_missing(self):
        c = UpdateCheckCoordinator()
        c.begin()
        self.assertFalse(c.has_partial())
        r = c.as_result(timeout_detail="Check timed out after 45 s.")
        self.assertEqual(r.system_state, "error")
        self.assertEqual(r.flatpak_count, 0)

    def test_coordinator_completes_when_both_arrive(self):
        c = UpdateCheckCoordinator()
        c.begin()
        self.assertIsNone(c.accept(UpdateProbeResult.success("system", value="available", detail="ok")))
        r = c.accept(UpdateProbeResult.success("flatpak", value=3))
        self.assertIsNotNone(r)
        self.assertEqual(r.system_state, "available")
        self.assertEqual(r.flatpak_count, 3)

if __name__ == "__main__":
    unittest.main()
