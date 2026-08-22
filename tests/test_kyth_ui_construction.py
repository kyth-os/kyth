"""Headless smoke tests for the refactored System Hub UI surface."""
from __future__ import annotations

import os
import importlib.util
import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = r"""
import ast
import inspect
from unittest.mock import patch

from kyth_welcome.qt import QApplication, QPushButton
from kyth_welcome.services.runtime import shutdown_threads
from kyth_welcome.windows import MainWindow
from kyth_welcome.wizard import WizardWindow
from kyth_welcome.vpn_app import VpnWindow
from kyth_welcome.page_vpn import VpnPage

app = QApplication([])
wizard = WizardWindow()
# Welcome is built eagerly; remaining steps (including GamingPage) are lazy.
assert "welcome" in wizard._steps
assert "gaming" not in wizard._steps
assert wizard.windowTitle() == "Welcome to KythOS"
for key in ("machine", "apps", "work", "finish"):
    wizard._ensure_step(key)
assert set(wizard._steps) >= {"welcome", "machine", "apps", "work", "finish"}
assert "gaming" not in wizard._steps
wizard.close()

hub = MainWindow()
pages = {
    key: hub._ensure_page(index)
    for key, index in hub._page_index_by_key.items()
}
constructed = {key: type(page).__name__ for key, page in pages.items()}
assert len(constructed) == 20
assert constructed["Welcome"] == "WelcomePage"
assert constructed["Hardware"] == "HardwarePage"

# Deferred signal callbacks are not exercised by construction. Verify that
# every self.method(...) call surviving the refactor resolves on the concrete
# page instance after lazy mixins have loaded.
missing_methods = {}
for key, page in pages.items():
    referenced = set()
    for base in type(page).__mro__:
        try:
            tree = ast.parse(inspect.getsource(base))
        except (OSError, TypeError, IndentationError):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"
            ):
                referenced.add(node.func.attr)
    absent = sorted(name for name in referenced if not hasattr(page, name))
    if absent:
        missing_methods[key] = absent
assert not missing_methods, missing_methods

move_page = pages["Move Files"]
terminal_buttons = [
    button
    for button in move_page.findChildren(QPushButton)
    if button.text() == "Open Terminal"
]
assert len(terminal_buttons) == 1
with patch("kyth_welcome.page_windows_migration.popen") as launch:
    terminal_buttons[0].click()
launch.assert_called_once_with(["konsole"])
hub.close()

vpn_window = VpnWindow()
assert isinstance(vpn_window.centralWidget(), VpnPage)
assert vpn_window.windowTitle() == "VPN Connect"
vpn_window.close()
shutdown_threads()
"""


class UiConstructionTests(unittest.TestCase):
    def test_first_run_wizard_and_every_hub_page_construct(self):
        if not any(importlib.util.find_spec(binding) for binding in ("PySide6", "PyQt6")):
            self.skipTest("PySide6/PyQt6 is not installed on this validation runner")
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["PYTHONPATH"] = os.pathsep.join(
            [
                str(ROOT / "build_files" / "kyth-welcome"),
                str(ROOT / "build_files" / "kyth_shared"),
            ]
        )
        subprocess.run(
            [sys.executable, "-c", SMOKE_SCRIPT],
            cwd=ROOT,
            env=env,
            check=True,
            timeout=30,
        )


if __name__ == "__main__":
    unittest.main()
