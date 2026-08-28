"""The React Hub's search box must actually search, and rank like the Qt Hub.

The Topbar shipped an `<input placeholder="Search settings…">` with no
`value` and no `onChange` — it accepted typing and did nothing, while the
Qt Hub's box has ranked search over the same pages via
page_registry.rank_search_results. A dead input is valid TSX, so nothing in
the build catches it.

The ranking here is a port, not a reimplementation, so the parity test runs
the shipped TypeScript under node and compares it to the Python ranker over
the same entries. Only the algorithm is compared: hubSections.ts carries no
`search_terms`, and `problem_routes` has no source on the TS side, so both
are held empty on the Python side rather than pretended into existence.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys
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

from kyth_welcome.page_registry import PageDescriptor, rank_search_results  # noqa: E402

HUB_WEB_ROOT = ROOT / "src" / "kyth-hub-web"
HUB_WEB = HUB_WEB_ROOT / "src"
TOPBAR = (HUB_WEB / "components" / "Topbar.tsx").read_text(encoding="utf-8")
SEARCH_TS = (HUB_WEB / "search.ts").read_text(encoding="utf-8")
SECTIONS_TS = (HUB_WEB / "data" / "hubSections.ts").read_text(encoding="utf-8")

QUERIES = [
    "guardian",
    "update",
    "app store",
    "game controller",
    "perf",
    "Performance",
    "install",
    "drive",
    "no such page",
    "",
]


def _code_only(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith(("//", "*"))
    )


TOPBAR_CODE = _code_only(TOPBAR)


def _sections_from_ts() -> list[tuple[str, str, str]]:
    """(key, title, description) for every section, in file order."""
    pattern = re.compile(
        r'\{\s*key:\s*"([^"]+)",\s*title:\s*"([^"]+)",\s*description:\s*"([^"]+)"'
    )
    return pattern.findall(SECTIONS_TS)


def _esbuild() -> pathlib.Path | None:
    binary = HUB_WEB_ROOT / "node_modules" / ".bin" / "esbuild"
    if binary.exists() and shutil.which("node"):
        return binary
    return None


class TopbarSearchWiringTests(unittest.TestCase):
    def test_search_input_is_controlled(self):
        block = TOPBAR_CODE.split("<input")[1].split("/>")[0]
        self.assertIn("value={query}", block, "search input must be bound to state")
        self.assertIn("onChange", block, "search input must handle typing")

    def test_topbar_ranks_and_navigates(self):
        self.assertIn("rankSearchResults", TOPBAR_CODE)
        self.assertIn("navigate(", TOPBAR_CODE)

    def test_search_routes_through_the_deep_link_resolver(self):
        # A second route table is exactly how deep links lost 21 of 26 keys;
        # search must resolve a section key the same way --page does.
        self.assertIn("routeForPage", TOPBAR_CODE)
        self.assertNotIn("?section=", TOPBAR_CODE)

    def test_search_index_is_derived_from_the_shared_destinations(self):
        code = _code_only(SEARCH_TS)
        self.assertIn("DESTINATIONS", code)
        for key, _title, _desc in _sections_from_ts():
            self.assertNotIn(f'"{key}"', code, f"{key} hardcoded in the search index")

    def test_bell_dot_is_not_permanently_lit(self):
        # It rendered an unread dot unconditionally with no notification
        # source anywhere in either Hub.
        self.assertIn("pendingCount", TOPBAR_CODE)
        # [-1]: the first "IconBell" is the import, the last is the render.
        dot = TOPBAR_CODE.split("IconBell")[-1]
        self.assertIn("{!!pendingCount && (", dot)


class SearchRankingParityTests(unittest.TestCase):
    """The TS ranker must agree with page_registry.rank_search_results."""

    @classmethod
    def setUpClass(cls):
        binary = _esbuild()
        if binary is None:
            raise unittest.SkipTest("node/esbuild unavailable — frontend deps not installed")
        entry = HUB_WEB_ROOT / "kyth-search-parity-probe.mjs"
        entry.write_text(
            "import { rankSearchResults } from './src/search.ts';\n"
            f"const queries = {json.dumps(QUERIES)};\n"
            "const out = {};\n"
            "for (const q of queries) out[q] = rankSearchResults(q)"
            ".map(r => [r.entry.key, r.score]);\n"
            "console.log(JSON.stringify(out));\n",
            encoding="utf-8",
        )
        try:
            bundle = subprocess.run(
                [str(binary), "--bundle", "--format=esm", "--platform=node",
                 "--loader:.tsx=tsx", str(entry)],
                capture_output=True, text=True, cwd=HUB_WEB_ROOT, check=True,
            ).stdout
        finally:
            entry.unlink(missing_ok=True)
        result = subprocess.run(
            [shutil.which("node"), "--input-type=module"],
            input=bundle, capture_output=True, text=True, cwd=HUB_WEB_ROOT, check=True,
        )
        cls.ts_rankings = json.loads(result.stdout)

    def _python_rankings(self, query: str) -> list[list]:
        descriptors = [
            PageDescriptor(
                key=key,
                title=title,
                section=None,
                icon_names=(),
                factory=lambda: None,
                search_description=description,
                search_terms=(),
            )
            for key, title, description in _sections_from_ts()
        ]
        return [[key, score] for key, score in rank_search_results(query, descriptors, {})]

    def test_rankings_match_the_qt_hub_for_every_query(self):
        for query in QUERIES:
            with self.subTest(query=query):
                self.assertEqual(
                    self._python_rankings(query),
                    self.ts_rankings[query],
                    f"TS ranking diverged from page_registry.rank_search_results for {query!r}",
                )

    def test_the_comparison_is_not_vacuous(self):
        # At least one query must actually return hits, or the test above
        # would pass by comparing empty lists forever.
        hits = sum(len(v) for v in self.ts_rankings.values())
        self.assertGreater(hits, 5, "parity fixture produced almost no results")


if __name__ == "__main__":
    unittest.main()
