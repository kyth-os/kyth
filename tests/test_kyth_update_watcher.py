import importlib.util
from importlib.machinery import SourceFileLoader
import subprocess  # nosec B404 # nosemgrep
import unittest
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
