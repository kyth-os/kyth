import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.services import setup_state  # noqa: E402


class SetupStateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        state_path = str(Path(self._tmp.name) / "setup-state.json")
        legacy_path = str(Path(self._tmp.name) / "kyth-welcome-done")
        self._state_patch = patch.object(setup_state, "_STATE_PATH", state_path)
        self._legacy_patch = patch.object(setup_state, "_LEGACY_SENTINEL", legacy_path)
        self._state_patch.start()
        self._legacy_patch.start()
        self.addCleanup(self._state_patch.stop)
        self.addCleanup(self._legacy_patch.stop)

    def test_fresh_install_is_first_run_and_all_pending(self):
        self.assertTrue(setup_state.is_first_run())
        state = setup_state.load_state()
        self.assertEqual(set(state), set(setup_state.STEP_KEYS))
        self.assertTrue(all(v == setup_state.STATUS_PENDING for v in state.values()))

    def test_mark_step_persists_and_is_no_longer_first_run(self):
        setup_state.mark_step("apps", setup_state.STATUS_DONE)
        self.assertFalse(setup_state.is_first_run())
        state = setup_state.load_state()
        self.assertEqual(state["apps"], setup_state.STATUS_DONE)
        self.assertEqual(state["machine"], setup_state.STATUS_PENDING)

    def test_mark_step_ignores_unknown_key_or_status(self):
        setup_state.mark_step("not-a-real-step", setup_state.STATUS_DONE)
        setup_state.mark_step("apps", "not-a-real-status")
        self.assertTrue(setup_state.is_first_run())

    def test_relevant_steps_excludes_gaming_for_everyday_profile(self):
        self.assertNotIn("gaming", setup_state.relevant_steps("everyday"))
        self.assertIn("gaming", setup_state.relevant_steps("gaming"))

    def test_incomplete_steps_only_lists_non_done_relevant_steps(self):
        setup_state.mark_step("machine", setup_state.STATUS_DONE)
        setup_state.mark_step("apps", setup_state.STATUS_SKIPPED)
        setup_state.mark_step("work", setup_state.STATUS_DONE)
        incomplete = dict(setup_state.incomplete_steps("everyday"))
        self.assertNotIn("machine", incomplete)
        self.assertEqual(incomplete.get("apps"), setup_state.STATUS_SKIPPED)
        self.assertNotIn("work", incomplete)
        self.assertNotIn("gaming", incomplete)  # not relevant for this profile

    def test_mark_wizard_closed_records_untouched_steps_as_skipped(self):
        setup_state.mark_step("machine", setup_state.STATUS_DONE)
        setup_state.mark_wizard_closed("everyday")
        state = setup_state.load_state()
        self.assertEqual(state["machine"], setup_state.STATUS_DONE)
        self.assertEqual(state["apps"], setup_state.STATUS_SKIPPED)
        self.assertEqual(state["work"], setup_state.STATUS_SKIPPED)
        # gaming isn't relevant for the everyday profile — left untouched.
        self.assertEqual(state["gaming"], setup_state.STATUS_PENDING)

    def test_legacy_sentinel_migrates_to_all_done(self):
        Path(setup_state._LEGACY_SENTINEL).touch()
        self.assertFalse(setup_state.is_first_run())
        state = setup_state.load_state()
        self.assertTrue(all(v == setup_state.STATUS_DONE for v in state.values()))
        # Migration is persisted so subsequent loads don't need the legacy file.
        self.assertTrue(Path(setup_state._STATE_PATH).exists())

    def test_work_is_a_tracked_resume_step(self):
        self.assertIn("work", setup_state.STEP_KEYS)
        self.assertEqual(setup_state.STEP_RESUME_PAGE["work"], "Work Setup")
        self.assertIn("work", setup_state.relevant_steps("everyday"))

    def test_existing_state_without_work_does_not_resurface(self):
        setup_state.save_state({
            "machine": setup_state.STATUS_DONE,
            "apps": setup_state.STATUS_DONE,
            "gaming": setup_state.STATUS_SKIPPED,
        })
        state = setup_state.load_state()
        self.assertEqual(state["work"], setup_state.STATUS_SKIPPED)


if __name__ == "__main__":
    unittest.main()
