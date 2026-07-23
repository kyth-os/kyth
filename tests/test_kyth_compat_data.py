"""Game compatibility data loading/parsing (pure, no Qt).

page_compatibility.py's game list, filters, and "data last refreshed N days
ago" banner are all downstream of these functions — none had direct test
coverage before.
"""
from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

try:
    from kyth_welcome.services.gaming import compat_data
    from kyth_welcome.services.gaming.compat_data import (
        CompatGame,
        parse_compat_payload,
        replace_compat_games,
    )
except ImportError:
    raise unittest.SkipTest("PyQt6/PySide6 required by kyth_welcome.core_base → qt imports") from None


class ParseCompatPayloadTests(unittest.TestCase):
    def test_parses_valid_entries(self):
        updated, games = parse_compat_payload({
            "updated": "2026-01-15",
            "games": [
                {
                    "name": "Example Game",
                    "anticheat": "EAC",
                    "status": "proton",
                    "note": "Works with GE-Proton.",
                    "checked": "2026-01-01",
                    "source": "ProtonDB",
                    "source_url": "https://example.invalid/report",
                },
            ],
        })
        self.assertEqual(updated, "2026-01-15")
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0], CompatGame(
            name="Example Game", anticheat="EAC", status="proton",
            note="Works with GE-Proton.", checked="2026-01-01",
            source="ProtonDB", source_url="https://example.invalid/report",
        ))

    def test_filters_entries_with_unrecognized_status(self):
        _, games = parse_compat_payload({
            "updated": "2026-01-15",
            "games": [{"name": "Bad Status Game", "status": "totally-broken"}],
        })
        self.assertEqual(games, [])

    def test_filters_entries_missing_name(self):
        _, games = parse_compat_payload({
            "updated": "2026-01-15",
            "games": [{"status": "native"}],
        })
        self.assertEqual(games, [])

    def test_filters_non_dict_entries(self):
        _, games = parse_compat_payload({
            "updated": "2026-01-15",
            "games": ["not-a-dict", 42, None],
        })
        self.assertEqual(games, [])

    def test_missing_optional_fields_default_to_expected_values(self):
        _, games = parse_compat_payload({
            "updated": "2026-01-15",
            "games": [{"name": "Minimal Game", "status": "native"}],
        })
        self.assertEqual(games[0].anticheat, "None")
        self.assertEqual(games[0].note, "")

    def test_non_dict_payload_returns_empty(self):
        self.assertEqual(parse_compat_payload(["not", "a", "dict"]), ("", []))
        self.assertEqual(parse_compat_payload(None), ("", []))

    def test_all_four_known_statuses_are_accepted(self):
        for status in ("native", "proton", "tweaks", "blocked"):
            _, games = parse_compat_payload({
                "updated": "x", "games": [{"name": "G", "status": status}],
            })
            self.assertEqual(len(games), 1, msg=status)


class ReplaceCompatGamesTests(unittest.TestCase):
    def test_mutates_shared_list_in_place(self):
        # Callers (page_compatibility.py) hold a reference to the same list
        # object handed back by load_compat_games() — replace_compat_games
        # must mutate it in place, not rebind the module attribute to a new
        # list the caller never sees.
        original_list = compat_data._COMPAT_GAMES
        original_snapshot = list(original_list)
        original_updated = compat_data._COMPAT_DATA_UPDATED
        new_game = CompatGame(
            name="New Game", anticheat="None", status="native",
            note="", checked="", source="", source_url="",
        )
        try:
            replace_compat_games("2026-02-01", [new_game])
            self.assertIs(compat_data._COMPAT_GAMES, original_list)
            self.assertEqual(original_list, [new_game])
            self.assertEqual(compat_data._COMPAT_DATA_UPDATED, "2026-02-01")
        finally:
            # Restore so this test doesn't leak state into others.
            replace_compat_games(original_updated, original_snapshot)


if __name__ == "__main__":
    unittest.main()
