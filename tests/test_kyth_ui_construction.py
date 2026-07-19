"""Headless smoke tests for the refactored System Hub UI surface."""
from __future__ import annotations

import os
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = r"""
from kyth_welcome.qt import QApplication
from kyth_welcome.windows import MainWindow
from kyth_welcome.wizard import WizardWindow

app = QApplication([])
wizard = WizardWindow()
assert len(wizard._steps) == 6
assert wizard.windowTitle() == "Welcome to KythOS"
wizard.close()

hub = MainWindow()
constructed = {
    key: type(hub._ensure_page(index)).__name__
    for key, index in hub._page_index_by_key.items()
}
assert len(constructed) == 19
assert constructed["Welcome"] == "WelcomePage"
assert constructed["Hardware"] == "HardwarePage"
hub.close()
"""


class UiConstructionTests(unittest.TestCase):
    def test_first_run_wizard_and_every_hub_page_construct(self):
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["PYTHONPATH"] = os.pathsep.join(
            [
                str(ROOT / "build_files" / "kyth-welcome"),
                str(ROOT / "build_files" / "kyth_shared"),
            ]
        )
        subprocess.run(
            ["python", "-c", SMOKE_SCRIPT],
            cwd=ROOT,
            env=env,
            check=True,
            timeout=30,
        )


if __name__ == "__main__":
    unittest.main()
