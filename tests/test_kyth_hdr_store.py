"""hdr_store durability: saves are atomic, never truncated in place."""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared import hdr_store  # noqa: E402


class HdrStoreTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "hdr-store.toml"
            hdr_store.save_hdr_store({"preserve": False}, path)
            self.assertEqual(hdr_store.load_hdr_store(path), {"preserve": False})
            hdr_store.save_hdr_store({"preserve": True}, path)
            self.assertEqual(hdr_store.load_hdr_store(path), {"preserve": True})

    def test_crash_mid_write_keeps_previous_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "hdr-store.toml"
            hdr_store.save_hdr_store({"preserve": False}, path)
            before = path.read_bytes()

            real_fdopen = hdr_store.__dict__.get("os").fdopen

            class Exploding:
                def __init__(self, handle):
                    self._handle = handle

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    self._handle.close()
                    return False

                def write(self, data):
                    # Partial write, then the process "dies".
                    self._handle.write(data[:5])
                    raise OSError("simulated power loss")

                def flush(self):
                    pass

                def fileno(self):
                    return self._handle.fileno()

            with mock.patch(
                "kyth_shared.atomic_io.os.fdopen",
                side_effect=lambda fd, *a, **k: Exploding(real_fdopen(fd, *a, **k)),
            ):
                with self.assertRaises(OSError):
                    hdr_store.save_hdr_store({"preserve": True}, path)

            # The live file is untouched: old content, never truncated, and
            # the user's choice (preserve=false) still loads.
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(hdr_store.load_hdr_store(path), {"preserve": False})
            # No temp litter left next to the store.
            self.assertEqual(sorted(p.name for p in pathlib.Path(tmp).iterdir()), ["hdr-store.toml"])


if __name__ == "__main__":
    unittest.main()
