"""KRunner search entries — generated .desktop files for every Hub page.

Runs Qt-free (see _install_qt_stubs, mirrors test_kyth_page_registry.py):
krunner_desktop only reads page_registry's plain descriptor data, so a
fake kyth_welcome.qt module is enough — no PySide6/offscreen platform
needed for these checks.
"""
from __future__ import annotations

import shutil
import sys
import pathlib
import tempfile
import types
import unittest


def _install_qt_stubs() -> None:
    class _Dummy:
        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, *args, **kwargs):
            return self

        def __getattr__(self, _name):
            return self

    qt = types.ModuleType("kyth_welcome.qt")
    for name in ("QLabel", "QPushButton", "QTextEdit", "QThread", "QWidget"):
        setattr(qt, name, _Dummy)
    qt.Signal = _Dummy
    sys.modules["kyth_welcome.qt"] = qt


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))
_install_qt_stubs()

from kyth_welcome.krunner_desktop import build_entries, write_desktop_entries  # noqa: E402
from kyth_welcome.page_registry import SEARCH_ITEMS  # noqa: E402


class KrunnerDesktopTests(unittest.TestCase):
    def test_covers_every_search_item_that_is_also_a_real_page(self):
        entries = build_entries()
        # Every generated slug maps back to a SEARCH_ITEMS key — nothing
        # invented, nothing dropped silently.
        self.assertGreaterEqual(len(entries), 20)
        for slug in entries:
            self.assertTrue(slug.startswith("kyth-hub-"))

    def test_entry_shape_is_a_valid_no_display_launcher(self):
        entries = build_entries()
        content = entries["kyth-hub-guardian"]
        self.assertIn("[Desktop Entry]\n", content)
        self.assertIn("Type=Application\n", content)
        self.assertIn("NoDisplay=true\n", content)
        self.assertIn('Exec=/usr/bin/kyth-welcome-launch --page "Guardian"\n', content)
        # Keywords must include the page's own search terms so krunner can
        # actually find it by the phrases SEARCH_ITEMS documents.
        guardian_terms = SEARCH_ITEMS["Guardian"].terms
        self.assertTrue(guardian_terms)
        for term in guardian_terms:
            self.assertIn(term, content)

    def test_page_keys_with_spaces_stay_quoted_and_slug_is_filesystem_safe(self):
        entries = build_entries()
        content = entries["kyth-hub-this-pc"]
        self.assertIn('--page "This PC"\n', content)
        for slug in entries:
            self.assertNotIn(" ", slug)
            self.assertNotIn("/", slug)

    def test_write_desktop_entries_writes_one_file_per_entry(self):
        tmp = tempfile.mkdtemp(prefix="kyth-krunner-test-")
        try:
            written = write_desktop_entries(tmp)
            entries = build_entries()
            self.assertEqual(len(written), len(entries))
            for path in written:
                self.assertTrue(path.is_file())
                self.assertEqual(path.read_text(encoding="utf-8"), entries[path.stem])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_rerunning_write_is_idempotent(self):
        tmp = tempfile.mkdtemp(prefix="kyth-krunner-test-")
        try:
            first = {p.name for p in write_desktop_entries(tmp)}
            second = {p.name for p in write_desktop_entries(tmp)}
            self.assertEqual(first, second)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
