"""Redaction parity: Python scrubber must byte-match the native port.

tests/fixtures/scrub_corpus.json carries inputs with baked expected outputs
and must-not-contain tokens. The Rust side
(src/kyth-shared-rs/src/diagnostics_scrub.rs) asserts the same fixture, so
a redaction rule changed in one implementation without the other fails on
both sides. Host/user-dependent fallbacks are covered per-side, not here:
this corpus contains no hostname or username tokens.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "kyth_shared"))

from kyth_shared.diagnostics_scrub import scrub_logs  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "scrub_corpus.json"


def load_corpus() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


class ScrubParityTests(unittest.TestCase):
    def test_corpus_matches_native_port_expectations(self) -> None:
        for case in load_corpus():
            with self.subTest(case=case["name"]):
                self.assertEqual(scrub_logs(case["input"]), case["expected"])

    def test_corpus_leaks_nothing(self) -> None:
        for case in load_corpus():
            with self.subTest(case=case["name"]):
                scrubbed = scrub_logs(case["input"])
                for token in case["must_not_contain"]:
                    self.assertNotIn(token, scrubbed)

    def test_username_fallback_redacts_env_user(self) -> None:
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"USER": "parity-user", "USERNAME": ""}):
            scrubbed = scrub_logs("ran as parity-user today")
        self.assertNotIn("parity-user", scrubbed)

if __name__ == "__main__":
    unittest.main()
