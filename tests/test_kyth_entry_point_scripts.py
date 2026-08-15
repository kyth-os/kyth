"""Import-time smoke for standalone entry-point scripts.

The pre-push offscreen smoke instantiates every System Hub *page*, but the
extensionless executables next to them are never imported by anything in the
suite. kyth-update-notifier shipped with two import-time defects that way — a
`QMenu`/`QSystemTrayIcon` pair missing from the kyth_shared.qt shim, and a
dropped `from pathlib import Path` — and only surfaced as a crash-loop in the
journal on real hardware.
"""
from __future__ import annotations

import os
import pathlib
import sys
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

ROOT = pathlib.Path(__file__).resolve().parents[1]
WELCOME = ROOT / "build_files" / "kyth-welcome"

for path in (ROOT / "build_files" / "kyth_shared", WELCOME):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def python_entry_points() -> list[pathlib.Path]:
    """Extensionless executables in kyth-welcome with a python shebang."""
    found = []
    for candidate in sorted(WELCOME.iterdir()):
        if not candidate.is_file() or candidate.suffix:
            continue
        try:
            first = candidate.read_text(encoding="utf-8").splitlines()[0]
        except (OSError, IndexError, UnicodeDecodeError):
            continue
        if first.startswith("#!") and "python" in first:
            found.append(candidate)
    return found


class EntryPointImportTests(unittest.TestCase):
    def test_at_least_one_entry_point_is_discovered(self):
        """Guard the guard: a discovery regression must not silently pass."""
        self.assertTrue(python_entry_points())

    def test_every_python_entry_point_imports(self):
        for script in python_entry_points():
            with self.subTest(script=script.name):
                name = f"entrypoint_{script.name.replace('-', '_')}"
                loader = SourceFileLoader(name, str(script))
                try:
                    loader.exec_module(module_from_spec(spec_from_loader(name, loader)))
                except SystemExit:
                    # A module-level main() guard exiting is a successful import.
                    pass
                except Exception as exc:  # noqa: BLE001 — any import-time error is the bug
                    self.fail(f"{script.name} failed at import: {type(exc).__name__}: {exc}")


class QtShimExportTests(unittest.TestCase):
    def test_every_declared_symbol_actually_exists(self):
        """__all__ is the contract callers import against; keep it honest."""
        from kyth_shared import qt

        missing = [name for name in qt.__all__ if not hasattr(qt, name)]
        self.assertEqual([], missing)

    def test_tray_symbols_are_exported(self):
        from kyth_shared.qt import QMenu, QSystemTrayIcon

        self.assertIsNotNone(QMenu)
        self.assertIsNotNone(QSystemTrayIcon)


if __name__ == "__main__":
    unittest.main()
