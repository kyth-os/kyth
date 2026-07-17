"""Lazy page mixin composition (Phase G)."""
from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))

from kyth_welcome.lazy_page import compose_on_first_init  # noqa: E402


class _Base:
    def __init__(self, value=0):
        self.value = value
        self.base_init = True


class _MixinA:
    def mixin_a(self):
        return "a"


class _MixinB:
    def mixin_b(self):
        return "b"


_load_calls = {"n": 0}


def _load():
    _load_calls["n"] += 1
    return (_MixinA, _MixinB)


@compose_on_first_init(_load)
class _Shell(_Base):
    def shell_method(self):
        return "shell"


class LazyPageTests(unittest.TestCase):
    def setUp(self):
        _load_calls["n"] = 0
        # Reset composition state by re-decorating a fresh class each time is hard;
        # use a unique shell per test via factory.

    def test_mixins_load_once_on_first_construct(self):
        calls = {"n": 0}

        def load():
            calls["n"] += 1
            return (_MixinA, _MixinB)

        @compose_on_first_init(load)
        class Shell(_Base):
            pass

        self.assertEqual(calls["n"], 0)
        a = Shell(1)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(a.value, 1)
        self.assertEqual(a.mixin_a(), "a")
        self.assertEqual(a.mixin_b(), "b")
        b = Shell(2)
        self.assertEqual(calls["n"], 1)  # still once
        self.assertEqual(b.value, 2)
        self.assertIs(type(a), type(b))

    def test_gaming_software_loaders_defined_in_source(self):
        # Avoid importing page modules (need full Qt bindings). Assert source shape.
        root = ROOT / "build_files" / "kyth-welcome" / "kyth_welcome"
        gaming = (root / "page_gaming.py").read_text(encoding="utf-8")
        software = (root / "page_software.py").read_text(encoding="utf-8")
        self.assertIn("def _load_gaming_mixins", gaming)
        self.assertIn("@compose_on_first_init(_load_gaming_mixins)", gaming)
        self.assertNotIn("from .page_gaming_library import", gaming.split("def _load_gaming_mixins")[0])
        self.assertIn("def _load_software_mixins", software)
        self.assertIn("@compose_on_first_init(_load_software_mixins)", software)
        self.assertNotIn("from .page_software_starter import", software.split("def _load_software_mixins")[0])
        self.assertIn("self._ensure_tab", software)


if __name__ == "__main__":
    unittest.main()
