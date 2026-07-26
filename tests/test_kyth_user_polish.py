import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.user_polish import OperationStatus, apply_foundation


class UserPolishTests(unittest.TestCase):
    def test_foundation_is_idempotent_in_isolated_home(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "kyth_shared.user_polish.shutil.which", return_value=None
        ):
            first = apply_foundation(tmp)
            second = apply_foundation(tmp)

            self.assertTrue((Path(tmp) / "Games/.directory").is_file())
            self.assertTrue((Path(tmp) / "Templates/Plain Text.txt").is_file())
            self.assertEqual(first[0].status, OperationStatus.APPLIED)
            self.assertEqual(second[0].status, OperationStatus.APPLIED)

    def test_partial_failure_does_not_stop_later_operations(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "kyth_shared.user_polish._ensure_user_folders",
            side_effect=OSError("read only"),
        ), mock.patch(
            "kyth_shared.user_polish.shutil.which", return_value=None
        ):
            results = apply_foundation(tmp)

        self.assertEqual(results[0].status, OperationStatus.FAILED)
        self.assertEqual(results[1].status, OperationStatus.UNAVAILABLE)
        self.assertEqual(results[2].status, OperationStatus.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
