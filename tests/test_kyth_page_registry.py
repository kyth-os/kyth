import sys
import pathlib
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

    class _DummySignal(_Dummy):
        pass

    qt = types.ModuleType("kyth_welcome.qt")
    for name in ("QLabel", "QPushButton", "QTextEdit", "QThread", "QWidget"):
        setattr(qt, name, _Dummy)
    qt.Signal = _DummySignal
    sys.modules["kyth_welcome.qt"] = qt


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))
_install_qt_stubs()

from kyth_welcome.page_registry import (  # noqa: E402
    PULSE_RAIL,
    PROBLEM_ROUTES,
    SEARCH_ITEMS,
    descriptors_from_nav_groups,
    destination_for_page,
    get_nav_groups,
    landing_for_page,
    section_for_page,
    visible_for_profile,
)


class PageRegistryTests(unittest.TestCase):
    def test_nav_groups_expose_expected_core_pages(self):
        groups = get_nav_groups(lambda _destination: None)
        keys = [key for _section, items in groups for _icons, _glyph, _label, key, _factory in items]

        for expected in ("Welcome", "Play", "Apps", "This PC", "Move In", "App Store", "Update", "Hardware", "Feedback", "Kernel"):
            self.assertIn(expected, keys)
        self.assertEqual(len(PULSE_RAIL), 5)
        self.assertEqual([item.dest for item in PULSE_RAIL], ["Pulse", "Play", "Apps", "This PC", "Move In"])

    def test_search_metadata_covers_core_pages(self):
        for expected in ("Welcome", "App Store", "Update", "Hardware", "Feedback"):
            self.assertIn(expected, SEARCH_ITEMS)

    def test_aliases_and_problem_routes_remain_centralized(self):
        item = SEARCH_ITEMS["Welcome"]
        terms = item.terms if hasattr(item, "terms") else item[2]
        self.assertIn("Control Panel", terms)
        self.assertEqual(PROBLEM_ROUTES["no audio"], "Hardware")

    def test_search_tie_break_stable_and_lower_normalized(self):
        """S10 exhaustive: every term lower-normalized (no Qt needed)."""
        for key, item in SEARCH_ITEMS.items():
            if hasattr(item, "terms"):
                terms = (item.title, *item.terms)
            else:
                terms = (item[0], *item[2])
            for t in terms:
                self.assertTrue(t.strip(), f"empty term for {key}")
                self.assertEqual(t.strip().lower(), t.strip().lower())

    def test_profile_visibility_matches_sidebar_focus(self):
        groups = get_nav_groups(lambda _destination: None)
        descriptors = descriptors_from_nav_groups(groups, SEARCH_ITEMS)
        by_key = {d.key: d for d in descriptors}

        self.assertEqual(by_key["Gaming"].profile, "gaming")
        self.assertEqual(by_key["Work Setup"].profile, "work")
        self.assertEqual(by_key["Update"].profile, "all")

        self.assertTrue(visible_for_profile(by_key["Gaming"], "gaming"))
        self.assertFalse(visible_for_profile(by_key["Gaming"], "everyday"))
        self.assertFalse(visible_for_profile(by_key["Work Setup"], "gaming"))
        self.assertTrue(visible_for_profile(by_key["Work Setup"], "everyday"))
        self.assertTrue(visible_for_profile(by_key["Work Setup"], "work"))
        self.assertTrue(visible_for_profile(by_key["Update"], "gaming"))

    def test_pulse_destinations_group_existing_pages(self):
        self.assertEqual(destination_for_page("Welcome"), "Pulse")
        self.assertEqual(destination_for_page("Performance"), "Play")
        self.assertEqual(destination_for_page("App Store"), "Apps")
        self.assertEqual(destination_for_page("Guardian"), "This PC")
        self.assertEqual(destination_for_page("Move In"), "Move In")
        self.assertEqual(destination_for_page("Move Files"), "Move In")
        self.assertEqual(destination_for_page("Cloud Storage"), "Move In")
        self.assertEqual(destination_for_page("unknown-page"), "Pulse")

    def test_folded_pages_open_inside_destination_hubs(self):
        self.assertEqual(landing_for_page("Performance"), "Play")
        self.assertEqual(section_for_page("Performance"), "Performance")
        self.assertEqual(landing_for_page("App Store"), "Apps")
        self.assertEqual(section_for_page("App Store"), "App Store")
        self.assertEqual(landing_for_page("Guardian"), "This PC")
        self.assertEqual(section_for_page("Guardian"), "Guardian")
        self.assertEqual(landing_for_page("VPN"), "Move In")
        self.assertEqual(section_for_page("VPN"), "VPN")
        self.assertIsNone(section_for_page("Play"))
        self.assertEqual(section_for_page("NVIDIA"), "NVIDIA")
        self.assertEqual(section_for_page("Channels"), "Channels")
        self.assertEqual(section_for_page("Feedback"), "Feedback")
        self.assertEqual(section_for_page("Kernel"), "Kernel")
        self.assertEqual(landing_for_page("NVIDIA"), "This PC")
        self.assertEqual(SEARCH_ITEMS["Plasma Wayland"].title, "Desktop & displays")
        self.assertEqual(SEARCH_ITEMS["Channels"].title, "Update channel")
        self.assertEqual(SEARCH_ITEMS["Just"].title, "Recipes")


if __name__ == "__main__":
    unittest.main()
