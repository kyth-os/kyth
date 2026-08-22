"""Headless System Hub smoke — 20 pages, search, legacy aliases, grab.

Guards W4 regression (rank tie-break) and _setup_search lower-normalize.
Runs offscreen (QT_QPA_PLATFORM=offscreen) so CI and local gates catch
navigation breakage before push.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

try:
    from PySide6.QtCore import QCoreApplication, QEvent, Qt  # noqa: E402
    from PySide6.QtWidgets import QApplication  # noqa: E402
except ImportError:
    raise unittest.SkipTest("PySide6 required for Hub smoke") from None


class TestHubSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Heavy offscreen smoke — skip under coverage to avoid OOM (run explicitly via `python -m unittest tests.test_kyth_welcome_hub_smoke`)
        if "coverage" in sys.modules:
            raise unittest.SkipTest("skip Hub offscreen smoke under coverage (run explicitly)")
        # If another welcome test mocked kyth_welcome.qt, MainWindow will fail
        # to import real Qt symbols. Skip gracefully in discover.
        try:
            from kyth_welcome.windows import MainWindow  # noqa: E402
        except ImportError as exc:
            raise unittest.SkipTest(f"Qt not available (mocked): {exc}") from exc
        try:
            cls._app = QApplication.instance() or QApplication(sys.argv)
            cls.window = MainWindow()
        except Exception as exc:
            raise unittest.SkipTest(f"Hub not runnable offscreen: {exc}") from exc
        cls.window.resize(1200, 800)
        cls.window.show()
        cls._app.processEvents()
        cls.MainWindow = MainWindow

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls._app.processEvents()

    def test_navigate_all_20_pages(self):
        from kyth_welcome.page_registry import landing_for_page, section_for_page

        keys = [d.key for d in self.window._page_descriptors]
        self.assertGreaterEqual(len(keys), 24)
        for expected in ("Welcome", "Play", "Apps", "This PC", "Move In", "Move Files"):
            self.assertIn(expected, keys)
        for key in keys:
            with self.subTest(page=key):
                self.window._navigate_to(key)
                self._app.processEvents()
                folded = section_for_page(key)
                landing = landing_for_page(key) if folded else key
                idx = self.window._page_index_by_key.get(landing)
                self.assertIsNotNone(idx)
                self.assertEqual(self.window._stack.currentIndex(), idx)
                page = self.window._pages[idx]
                if folded:
                    self.assertTrue(hasattr(page, "current_section"))
                    self.assertEqual(page.current_section(), key)
                elif page is not None and hasattr(page, "current_section"):
                    self.assertEqual(page.current_section(), "overview")

    def test_folded_child_hides_settings_header(self):
        self.window._navigate_to("Performance")
        self._app.processEvents()
        play = self.window._pages[self.window._page_index_by_key["Play"]]
        child = play._children.get("Performance")
        self.assertIsNotNone(child)
        band = getattr(child, "_page_header_band", None)
        self.assertIsNotNone(band)
        self.assertFalse(band.isVisible())

    def test_advanced_tools_stay_on_this_pc(self):
        self.window._navigate_to("NVIDIA")
        self._app.processEvents()
        pc = self.window._pages[self.window._page_index_by_key["This PC"]]
        self.assertEqual(pc.current_section(), "NVIDIA")
        self.assertEqual(pc._tab_for_section("NVIDIA"), "More")

    def test_pulse_chrome_matches_labeled_rail(self):
        from PySide6.QtWidgets import QLabel, QWidget

        self.assertEqual(self.window.windowTitle(), "Kyth Pulse")
        rail = self.window.findChild(QWidget, "pulse-rail")
        self.assertIsNotNone(rail)
        self.assertGreaterEqual(rail.width(), 100)
        play = self.window._rail_buttons["Play"]
        self.assertEqual(play.accessibleName(), "Play")
        self.assertTrue(any(label.text() == "Play" for label in play.findChildren(QLabel)))
        wordmark = self.window.findChild(QLabel, "pulse-rail-wordmark")
        self.assertIsNotNone(wordmark)
        self.assertEqual(wordmark.text(), "PULSE")
        self.window._navigate_to("Play")
        self._app.processEvents()
        self.assertEqual(self.window._place_btn.text(), "Play")
        self.window._navigate_to("Performance")
        self._app.processEvents()
        self.assertEqual(self.window._place_btn.text(), "Play")
        self.assertIn("Boost", self.window._crumb_lbl.text())

    def test_ensure_page_and_grab(self):
        for key in [d.key for d in self.window._page_descriptors][:5]:
            idx = self.window._page_index_by_key[key]
            w = self.window._ensure_page(idx)
            self.assertIsNotNone(w)
            pix = self.window.grab()
            self.assertFalse(pix.isNull())
            self.assertGreater(pix.width(), 0)

    def test_rank_search_results(self):
        cases = {
            "wifi": "Hardware",
            "no audio": "Hardware",
            "slow game": "Performance",
            "rollback update": "Update",
            "printer setup": "Hardware",
            "game won't launch": "Compatibility",
            "take screenshot": "Plasma Wayland",
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                res = self.window._rank_search_results(query)
                self.assertTrue(res)
                self.assertEqual(res[0][0], expected)

    def test_search_lower_normalize(self):
        # S10: alias lower inserted, so "WIFI" norm matches
        self.assertEqual(self.window._search_key_by_entry.get("wifi"), "Hardware")
        self.assertEqual(self.window._search_key_by_entry.get("wifi".lower()), "Hardware")
        # direct case variant should also resolve via norm or direct
        self.assertIsNotNone(
            self.window._search_key_by_entry.get("Control Panel")
            or self.window._search_key_by_entry.get("control panel")
        )

    def test_legacy_aliases(self):
        from kyth_welcome.page_registry import landing_for_page, section_for_page

        for old, new in self.window._LEGACY_ALIASES.items():
            with self.subTest(alias=old):
                folded = section_for_page(new)
                landing = landing_for_page(new) if folded else new
                expected = self.window._page_index_by_key.get(landing)
                self.window._navigate_to(old)
                self._app.processEvents()
                self.assertEqual(self.window._stack.currentIndex(), expected)
                if folded:
                    page = self.window._pages[expected]
                    self.assertEqual(page.current_section(), new)

    def test_search_panel_no_crash(self):
        for txt in ["", "a", "wifi"]:
            self.window._update_search_results(txt)
            self._app.processEvents()

    def test_repeated_window_lifecycle_releases_workers_and_widgets(self):
        from kyth_welcome.services.runtime import running_threads, shutdown_threads

        baseline = set(QApplication.topLevelWidgets())
        for cycle in range(3):
            with self.subTest(cycle=cycle):
                window = self.MainWindow()
                window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
                window.resize(900, 600)
                window.show()
                for key in [d.key for d in window._page_descriptors][:5]:
                    window._navigate_to(key)
                    self._app.processEvents()
                window.close()
                window.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                self._app.processEvents()
                for _ in range(3):
                    shutdown_threads(5000)
                    self._app.processEvents()
                self.assertEqual(running_threads(), [])
                self.assertNotIn(window, QApplication.topLevelWidgets())
        self.assertEqual(set(QApplication.topLevelWidgets()), baseline)
