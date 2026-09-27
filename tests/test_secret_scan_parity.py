"""Parity between the Python and Rust committed-secret detectors.

``build_files/scripts/check-committed-secrets.py`` owns Git enumeration and
reporting; ``src/kyth-shared-rs/src/secret_scan.rs`` reuses the same rules
for supplied text. Both copies intentionally contain the high-confidence
signatures they enforce. This test extracts the pattern sets from both
sources and asserts equivalence so neither copy can drift: same kind
labels, same regexes (modulo language literal syntax), same case
sensitivity, and same binary-suffix exclusions.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY_DETECTOR = ROOT / "build_files/scripts/check-committed-secrets.py"
RS_DETECTOR = ROOT / "src/kyth-shared-rs/src/secret_scan.rs"


def _extract_python_patterns(source: str) -> dict[str, tuple[str, bool]]:
    """Return {label: (regex, ignorecase)} from the Python detector."""
    entries: dict[str, tuple[str, bool]] = {}
    for match in re.finditer(
        r'"([^"]+)"\s*:\s*re\.compile\(\s*r"((?:[^"\\]|\\.)*)"\s*(,\s*re\.IGNORECASE)?\s*\)',
        source,
    ):
        label, pattern, flag = match.group(1), match.group(2), match.group(3)
        entries[label] = (pattern, bool(flag))
    return entries


def _extract_rust_patterns(source: str) -> dict[str, tuple[str, bool]]:
    """Return {label: (regex, ignorecase)} from the Rust detector."""
    entries: dict[str, tuple[str, bool]] = {}
    for match in re.finditer(r'\(\s*"([^"]+)"\s*,\s*Regex', source):
        label = match.group(1)
        rest = source[match.end():]
        raw = re.match(r'[A-Za-z:]*new\(\s*r"((?:[^"\\]|\\.)*)"', rest)
        if raw is None:  # pragma: no cover - malformed detector source
            raise AssertionError(f"could not parse regex for {label!r}")
        pattern = raw.group(1)
        after = rest[raw.end():]
        # Bound flag detection to this tuple entry so a later
        # `.case_insensitive(true)` cannot leak into an earlier pattern.
        next_entry = re.search(r'\(\s*"[^"]+"\s*,', after)
        tail = after[:next_entry.start()] if next_entry else after[:400]
        ignorecase = ".case_insensitive(true)" in tail
        entries[label] = (pattern, ignorecase)
    return entries


def _normalize(pattern: str) -> str:
    """Unescape language-level doubling so Python and Rust literals compare."""
    return pattern.replace("\\\\", "\\")


def _extract_python_suffixes(source: str) -> set[str]:
    match = re.search(r"binary_suffixes\s*=\s*\{([^}]*)\}", source)
    assert match, "binary_suffixes set not found in Python detector"
    return set(re.findall(r'"(\.[a-z0-9]+)"', match.group(1)))


def _extract_rust_suffixes(source: str) -> set[str]:
    match = re.search(r'Some\("((?:[a-z]+" \| ")+[a-z]+)"\)', source)
    assert match, "binary suffix list not found in Rust detector"
    return {f".{part}" for part in re.findall(r"[a-z]+", match.group(1))}


class SecretScanParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.py_source = PY_DETECTOR.read_text(encoding="utf-8")
        cls.rs_source = RS_DETECTOR.read_text(encoding="utf-8")
        cls.py_patterns = _extract_python_patterns(cls.py_source)
        cls.rs_patterns = _extract_rust_patterns(cls.rs_source)

    def test_pattern_labels_match(self):
        self.assertTrue(self.py_patterns, "no patterns extracted from Python detector")
        self.assertTrue(self.rs_patterns, "no patterns extracted from Rust detector")
        self.assertEqual(
            set(self.py_patterns), set(self.rs_patterns),
            "detector pattern labels diverged",
        )

    def test_pattern_bodies_match(self):
        for label in self.py_patterns:
            py_regex, py_ci = self.py_patterns[label]
            rs_regex, rs_ci = self.rs_patterns[label]
            self.assertEqual(
                _normalize(rs_regex), _normalize(py_regex),
                f"regex for {label!r} diverged between detectors",
            )
            self.assertEqual(
                rs_ci, py_ci,
                f"case-insensitivity for {label!r} diverged between detectors",
            )

    def test_binary_suffix_exclusions_match(self):
        self.assertEqual(
            _extract_rust_suffixes(self.rs_source),
            _extract_python_suffixes(self.py_source),
            "binary suffix exclusions diverged between detectors",
        )

    def test_extracted_python_patterns_catch_fixtures(self):
        compiled = {
            label: re.compile(body, re.IGNORECASE if ci else 0)
            for label, (body, ci) in self.py_patterns.items()
        }
        # Built by concatenation so this file itself never contains the
        # byte sequence the committed-secrets gate scans for.
        key_block = "-----BEGIN " + "PRIVATE KEY-----"
        self.assertTrue(compiled["private key block"].search(key_block))
        self.assertTrue(
            compiled["GitHub token"].search("token=«redacted:ghp_" + "A" * 36 + "»")
            or compiled["GitHub token"].search("x " + "ghp_" + "A" * 36 + " y")
        )
        self.assertFalse(
            compiled["private key block"].search("This is a normal build note.")
        )


if __name__ == "__main__":
    unittest.main()
