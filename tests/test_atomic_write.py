"""Tests for kyth_shared.atomic durability primitive."""
import json
import pathlib
import tempfile
import threading
import unittest

import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src" / "kyth_shared"))

from kyth_shared.atomic import atomic_write_json, read_json_or_default  # noqa: E402


class AtomicWriteTests(unittest.TestCase):
    def test_torn_write_returns_default_and_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            atomic_write_json(path, {"a": 1})
            self.assertEqual(read_json_or_default(path, None), {"a": 1})
            # simulate torn write (truncate mid-JSON)
            path.write_text('{"a":', encoding="utf-8")
            self.assertEqual(read_json_or_default(path, {"default": True}), {"default": True})
            # next atomic write recovers
            atomic_write_json(path, {"b": 2})
            self.assertEqual(read_json_or_default(path, None), {"b": 2})

    def test_invariants_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            atomic_write_json(path, {"a": 1})
            def bad_invariants():
                return ["failures<0"]
            with self.assertRaises(ValueError):
                atomic_write_json(path, {"a": 2}, invariants=bad_invariants)
            # file unchanged after refusal
            self.assertEqual(read_json_or_default(path, None), {"a": 1})

    def test_concurrent_writers_produce_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            errors = []

            def writer(n):
                try:
                    atomic_write_json(path, {"n": n, "data": "x" * 100})
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [])
            data = read_json_or_default(path, None)
            self.assertIsInstance(data, dict)
            self.assertIn("n", data)
            # file is valid JSON
            json.loads(path.read_text(encoding="utf-8"))

    def test_parent_fsync_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "subdir" / "state.json"
            atomic_write_json(path, {"x": 1})
            self.assertTrue(path.exists())
            self.assertEqual(read_json_or_default(path, None), {"x": 1})


if __name__ == "__main__":
    unittest.main()
