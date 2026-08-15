"""Import-time smoke for standalone entry-point scripts.

The pre-push offscreen smoke instantiates every System Hub *page*, but the
extensionless executables next to them are never imported by anything in the
suite. kyth-update-notifier shipped with two import-time defects that way — a
`QMenu`/`QSystemTrayIcon` pair missing from the kyth_shared.qt shim, and a
dropped `from pathlib import Path` — and only surfaced as a crash-loop in the
journal on real hardware.

Each script is imported in its own subprocess. Importing a full Qt application
into the shared test process leaks module state (and a QApplication) into every
test that runs afterwards, which is both order-dependent and a real source of
false failures.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WELCOME = ROOT / "build_files" / "kyth-welcome"
SHARED = ROOT / "build_files" / "kyth_shared"

# Import only — never run main(). runpy would execute the script body under
# __main__, starting real event loops.
_IMPORT_ONLY = """
import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

name, path = sys.argv[1], sys.argv[2]
loader = SourceFileLoader(name, path)
try:
    loader.exec_module(module_from_spec(spec_from_loader(name, loader)))
except SystemExit:
    pass
"""


def qt_binding_available() -> bool:
    return any(
        importlib.util.find_spec(binding) is not None
        for binding in ("PySide6", "PyQt6")
    )


# The Validation image installs no Qt binding, and every entry point here pulls
# one in. Static undefined-name coverage for these same files does not depend on
# Qt: ruff.toml extend-includes them, so F82 catches the NameError class in CI
# regardless. This import check adds the runtime half wherever Qt exists — the
# pre-push Hub smoke and developer machines.
requires_qt = unittest.skipUnless(
    qt_binding_available(), "no Qt binding available (neither PySide6 nor PyQt6)"
)


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


def import_in_subprocess(script: pathlib.Path) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(WELCOME), str(SHARED), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    environment["QT_QPA_PLATFORM"] = "offscreen"
    return subprocess.run(  # noqa: S603 — fixed interpreter, repo-local paths
        [sys.executable, "-c", _IMPORT_ONLY, script.stem.replace("-", "_"), str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        env=environment,
        cwd=str(ROOT),
        check=False,
    )


class EntryPointImportTests(unittest.TestCase):
    def test_at_least_one_entry_point_is_discovered(self):
        """Guard the guard: a discovery regression must not silently pass."""
        self.assertTrue(python_entry_points())

    @requires_qt
    def test_every_python_entry_point_imports(self):
        for script in python_entry_points():
            with self.subTest(script=script.name):
                result = import_in_subprocess(script)
                self.assertEqual(
                    0,
                    result.returncode,
                    f"{script.name} failed at import:\n{result.stderr}",
                )


@requires_qt
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
