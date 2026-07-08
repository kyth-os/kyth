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
    PROBLEM_ROUTES,
    SEARCH_ALIASES,
    SEARCH_ITEMS,
    get_nav_groups,
)


class PageRegistryTests(unittest.TestCase):
    def test_nav_groups_expose_expected_core_pages(self):
        groups = get_nav_groups(lambda _destination: None)
        keys = [key for _section, items in groups for _icons, _glyph, _label, key, _factory in items]

        for expected in ("Welcome", "App Store", "Update", "Hardware", "Feedback"):
            self.assertIn(expected, keys)

    def test_search_metadata_covers_core_pages(self):
        for expected in ("Welcome", "App Store", "Update", "Hardware", "Feedback"):
            self.assertIn(expected, SEARCH_ITEMS)

    def test_aliases_and_problem_routes_remain_centralized(self):
        self.assertIn("Control Panel", SEARCH_ALIASES["Welcome"])
        self.assertEqual(PROBLEM_ROUTES["no audio"], "Hardware")


if __name__ == "__main__":
    unittest.main()
