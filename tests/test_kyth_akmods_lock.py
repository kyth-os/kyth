"""Single-flight lock for NVIDIA akmods builds."""
from __future__ import annotations

import pathlib
import sys
import tempfile
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.akmods_lock import (  # noqa: E402
    acquire_akmods_lock,
    akmods_build_in_progress,
    release_akmods_lock,
)


class AkmodsLockTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self._tmp.name) / "akmods.lock"

    def tearDown(self):
        self._tmp.cleanup()

    def test_second_holder_sees_in_progress(self):
        fd = acquire_akmods_lock(self.path, timeout=0.5)
        try:
            self.assertTrue(akmods_build_in_progress(self.path))
        finally:
            release_akmods_lock(fd)
        self.assertFalse(akmods_build_in_progress(self.path))

    def test_timeout_raises_instead_of_sharing_the_lock(self):
        fd = acquire_akmods_lock(self.path, timeout=0.5)
        try:
            with self.assertRaises(RuntimeError):
                acquire_akmods_lock(self.path, timeout=0.2)
        finally:
            release_akmods_lock(fd)

    def test_waiter_acquires_after_release(self):
        held = acquire_akmods_lock(self.path, timeout=0.5)
        got: list[int] = []

        def _wait():
            try:
                waiter = acquire_akmods_lock(self.path, timeout=2.0)
                got.append(waiter)
                release_akmods_lock(waiter)
            except RuntimeError:
                pass

        thread = threading.Thread(target=_wait)
        thread.start()
        time.sleep(0.1)
        release_akmods_lock(held)
        thread.join(timeout=3)
        self.assertTrue(got)


if __name__ == "__main__":
    unittest.main()
