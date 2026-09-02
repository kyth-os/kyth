"""Regression checks for retired Python/Qt Hub entry points."""
from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WELCOME = ROOT / "src" / "kyth-welcome"


def python_entry_points() -> list[pathlib.Path]:
    """Extensionless Python executables must not remain beside the launcher."""
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
    def test_no_python_launcher_or_notifier_remains(self):
        self.assertEqual([], python_entry_points())
        self.assertFalse((WELCOME / "kyth-update-notifier").exists())


if __name__ == "__main__":
    unittest.main()
