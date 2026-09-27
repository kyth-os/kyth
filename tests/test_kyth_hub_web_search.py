"""The React/Tauri Hub's search box and manifest-backed ranker."""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HUB_WEB_ROOT = ROOT / "src" / "kyth-hub-web"
HUB_WEB = HUB_WEB_ROOT / "src"
TOPBAR = (HUB_WEB / "components" / "Topbar.tsx").read_text(encoding="utf-8")
SEARCH_TS = (HUB_WEB / "search.ts").read_text(encoding="utf-8")
HUB_ROUTES = json.loads(
    (HUB_WEB / "data" / "hubRoutes.json").read_text(encoding="utf-8")
)

QUERIES = [
    "guardian", "update", "app store", "game controller", "perf",
    "Performance", "install", "drive", "no such page", "",
]

def _code_only(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith(("//", "*"))
    )

TOPBAR_CODE = _code_only(TOPBAR)

def _sections_from_manifest() -> list[tuple[str, str, str]]:
    return [
        (section["key"], section["title"], section["description"])
        for destination in HUB_ROUTES["destinations"]
        for section in destination["sections"]
    ]

def _esbuild() -> pathlib.Path | None:
    binary = HUB_WEB_ROOT / "node_modules" / ".bin" / "esbuild"
    return binary if binary.exists() and shutil.which("node") else None

class TopbarSearchWiringTests(unittest.TestCase):
    def test_search_input_is_controlled(self):
        block = TOPBAR_CODE.split("<input")[1].split("/>")[0]
        self.assertIn("value={query}", block)
        self.assertIn("onChange", block)

    def test_topbar_ranks_and_navigates(self):
        self.assertIn("rankSearchResults", TOPBAR_CODE)
        self.assertIn("navigate(", TOPBAR_CODE)

    def test_search_routes_through_the_deep_link_resolver(self):
        self.assertIn("routeForPage", TOPBAR_CODE)
        self.assertNotIn("?section=", TOPBAR_CODE)

    def test_search_index_is_derived_from_shared_destinations(self):
        code = _code_only(SEARCH_TS)
        self.assertIn("DESTINATIONS", code)
        for key, _title, _description in _sections_from_manifest():
            self.assertNotIn(f'"{key}"', code)

    def test_bell_dot_is_not_permanently_lit(self):
        self.assertIn("pendingCount", TOPBAR_CODE)
        self.assertIn("{!!pendingCount && (", TOPBAR_CODE.split("IconBell")[-1])

class SearchRankingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        binary = _esbuild()
        if binary is None:
            raise unittest.SkipTest("node/esbuild unavailable — frontend deps not installed")
        entry = HUB_WEB_ROOT / "kyth-search-probe.mjs"
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

    def test_rankings_use_manifest_keys_and_scores(self):
        manifest_keys = {key for key, _title, _description in _sections_from_manifest()}
        for query in QUERIES:
            with self.subTest(query=query):
                self.assertLessEqual(len(self.ts_rankings[query]), 5)
                for key, score in self.ts_rankings[query]:
                    self.assertIn(key, manifest_keys)
                    self.assertGreater(score, 0)

    def test_comparison_is_not_vacuous(self):
        self.assertGreater(sum(len(v) for v in self.ts_rankings.values()), 5)

if __name__ == "__main__":
    unittest.main()
