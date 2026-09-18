"""On-disk probe cache (Phase F) — pure stdlib, no Qt."""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.system import probe as probe_mod  # noqa: E402
from kyth_shared.system import process as process_mod  # noqa: E402
from kyth_shared.system import controllers as controller_mod  # noqa: E402


class ProbeCacheFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self._tmp.name) / "probe-cache.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_and_read_section(self):
        probe_mod.update_sections(
            {
                "nvidia-detect": False,
                "flatpak-apps": ["com.valvesoftware.Steam"],
                "bootc-status-data": {"status": {"booted": {}}},
            },
            path=self.path,
        )
        self.assertTrue(self.path.is_file())
        doc = json.loads(self.path.read_text())
        self.assertEqual(doc["version"], probe_mod.CACHE_VERSION)
        self.assertIn("sections", doc)

        self.assertIs(
            probe_mod.read_section(
                "nvidia-detect",
                max_age=60,
                paths=[self.path],
            ),
            False,
        )
        apps = probe_mod.read_section("flatpak-apps", max_age=60, paths=[self.path])
        self.assertEqual(apps, ["com.valvesoftware.Steam"])

    def test_stale_section_rejected(self):
        probe_mod.update_sections({"nvidia-detect": True}, path=self.path)
        # Force section timestamp into the past.
        doc = json.loads(self.path.read_text())
        doc["sections"]["nvidia-detect"]["ts"] = time.time() - 10_000
        self.path.write_text(json.dumps(doc))
        # Mutating the file in place can keep the same mtime; drop the
        # in-process file cache so read_section sees the backdated ts.
        probe_mod._FILE_CACHE.clear()
        self.assertIsNone(
            probe_mod.read_section("nvidia-detect", max_age=60, paths=[self.path])
        )

    def test_invalidate_drops_sections(self):
        probe_mod.update_sections(
            {"nvidia-detect": True, "flatpak-apps": ["a"]},
            path=self.path,
        )
        with mock.patch.object(
            probe_mod, "cache_read_paths", return_value=[self.path]
        ):
            probe_mod.invalidate_disk_sections(["nvidia-detect"])
        doc = json.loads(self.path.read_text())
        self.assertNotIn("nvidia-detect", doc["sections"])
        self.assertIn("flatpak-apps", doc["sections"])

    def test_atomic_write_roundtrip(self):
        big = {"status": {"booted": {"image": {"reference": "ghcr.io/x/y:tag"}}}}
        probe_mod.update_sections({"bootc-status-data": big}, path=self.path)
        got = probe_mod.read_section("bootc-status-data", max_age=60, paths=[self.path])
        self.assertEqual(got, big)


class ProbeCacheLockTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self._tmp.name) / "probe-cache.json"
        probe_mod._FILE_CACHE.clear()

    def tearDown(self):
        probe_mod._FILE_CACHE.clear()
        self._tmp.cleanup()

    def test_lock_timeout_retries_then_writes(self):
        import fcntl
        import os

        original = {"version": probe_mod.CACHE_VERSION, "sections": {"keep": {"ts": 1, "data": True}}}
        self.path.write_text(json.dumps(original), encoding="utf-8")
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        lock_path.touch()
        fd = os.open(str(lock_path), os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            with mock.patch.object(probe_mod, "CACHE_LOCK_TIMEOUT_SEC", 0.05):
                # Contended lock: retry once, then write anyway so the update
                # is not silently dropped (tmp+rename stays atomic for readers).
                probe_mod.write_cache_file(self.path, {"version": 9, "sections": {}})
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        self.assertEqual(json.loads(self.path.read_text()), {"version": 9, "sections": {}})

    def test_concurrent_update_sections_keep_both_keys(self):
        import threading

        errors = []

        def writer(key, value):
            try:
                for _ in range(5):
                    probe_mod.update_sections({key: value}, path=self.path)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=(f"key-{n}", n)) for n in range(8)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        doc = json.loads(self.path.read_text())
        for n in range(8):
            self.assertIn(f"key-{n}", doc["sections"])

    def test_file_cache_key_tracks_subsecond_rewrites(self):
        probe_mod.update_sections({"nvidia-detect": True}, path=self.path)
        first = probe_mod.load_cache_file(self.path)
        self.assertIsNotNone(first)
        # Rewrite within the same mtime second with different content: the
        # (mtime_ns, size) key must miss and re-read instead of serving the
        # stale in-process entry.
        probe_mod.update_sections({"nvidia-detect": False, "extra-section": [1]}, path=self.path)
        second = probe_mod.load_cache_file(self.path)
        self.assertIs(second["sections"]["nvidia-detect"]["data"], False)
        self.assertIn("extra-section", second["sections"])

    def test_claim_fetch_single_flights_and_reclaims_stale(self):
        target = self.path
        try:
            self.assertTrue(probe_mod.claim_fetch(target))
            # A concurrent sweep sees the fresh marker and stands down.
            self.assertFalse(probe_mod.claim_fetch(target))
            probe_mod.clear_fetch(target)
            self.assertTrue(probe_mod.claim_fetch(target))
            probe_mod.clear_fetch(target)
            # A crashed owner's stale marker is reclaimed after its TTL.
            marker = target.with_suffix(target.suffix + ".fetching")
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("dead\n", encoding="utf-8")
            old = time.time() - (probe_mod.FETCH_MARKER_TTL_SEC + 5)
            os.utime(marker, (old, old))
            self.assertTrue(probe_mod.claim_fetch(target))
        finally:
            probe_mod.clear_fetch(target)

    def test_refresh_cache_serves_existing_when_fetch_in_progress(self):
        import os

        probe_mod.update_sections({"nvidia-detect": True}, path=self.path)
        marker = self.path.with_suffix(self.path.suffix + ".fetching")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("other\n", encoding="utf-8")
        try:
            with mock.patch.object(
                probe_mod, "collect_snapshot", side_effect=AssertionError("must not collect")
            ):
                target, sections = probe_mod.refresh_cache(path=self.path)
            self.assertEqual(target, self.path)
            self.assertIs(sections["nvidia-detect"], True)
        finally:
            try:
                os.unlink(marker)
            except OSError:
                pass

    def test_invalidate_logs_at_debug(self):
        import logging

        with self.assertLogs(probe_mod._logger, level="DEBUG") as captured:
            probe_mod.invalidate_probe_caches(["nvidia-detect"])
        self.assertTrue(any("invalidate_probe_caches" in line for line in captured.output))
        self.assertFalse(any("INFO" in line.split(":")[0] for line in captured.output))


class ProbeCachedIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self._tmp.name) / "probe-cache.json"
        process_mod.PROBE_CACHE.clear()

    def tearDown(self):
        process_mod.PROBE_CACHE.clear()
        self._tmp.cleanup()

    def test_memory_hit_skips_fetch(self):
        calls = {"n": 0}

        def fetch():
            calls["n"] += 1
            return "live"

        # Seed memory
        process_mod.PROBE_CACHE["bootc-status-text"] = (time.monotonic(), "cached")
        val = process_mod.probe_cached("bootc-status-text", 5.0, fetch)
        self.assertEqual(val, "cached")
        self.assertEqual(calls["n"], 0)

    def test_disk_warm_skips_live_fetch(self):
        probe_mod.update_sections(
            {"bootc-status-text": "from-disk"},
            path=self.path,
        )
        calls = {"n": 0}

        def fetch():
            calls["n"] += 1
            return "live"

        with mock.patch.object(
            probe_mod, "cache_read_paths", return_value=[self.path]
        ):
            # Clear memory so disk path is used
            process_mod.PROBE_CACHE.clear()
            val = process_mod.probe_cached("bootc-status-text", 5.0, fetch)
        self.assertEqual(val, "from-disk")
        self.assertEqual(calls["n"], 0)

    def test_invalidate_clears_memory_and_disk(self):
        probe_mod.update_sections({"nvidia-detect": True}, path=self.path)
        process_mod.PROBE_CACHE["nvidia-detect"] = (time.monotonic(), True)
        with mock.patch.object(
            probe_mod, "cache_read_paths", return_value=[self.path]
        ):
            process_mod.invalidate_probe_caches()
        self.assertNotIn("nvidia-detect", process_mod.PROBE_CACHE)
        doc = json.loads(self.path.read_text())
        self.assertNotIn("nvidia-detect", doc.get("sections", {}))

    def test_disk_section_usable_helpers(self):
        self.assertFalse(process_mod.disk_section_usable("flatpak-apps", None))
        self.assertTrue(process_mod.disk_section_usable("nvidia-detect", False))
        self.assertTrue(process_mod.disk_section_usable("flatpak-apps", []))
        self.assertFalse(process_mod.disk_section_usable("bootc-status-text", ""))


class CollectSnapshotTests(unittest.TestCase):
    def test_shared_controller_detector_parses_known_usb_device(self):
        def output(command, timeout=5):
            if command[0] == "lsusb":
                return "Bus 001 Device 005: ID 045e:02e6 Xbox Wireless Adapter\n"
            if command[0] == "lsmod":
                return "xone_hid 40960 0\n"
            return ""

        with mock.patch.object(controller_mod, "command_stdout", side_effect=output), \
             mock.patch.object(controller_mod.os, "listdir", return_value=[]), \
             mock.patch.object(controller_mod.shutil, "which", return_value=None):
            result = controller_mod.detect_controllers()

        self.assertTrue(result["xone_dongle"])
        self.assertTrue(result["xone_loaded"])

    def test_typed_collectors_preserve_unavailable_and_failure_states(self):
        collectors = (
            probe_mod.ProbeCollector("ok", ("available", "missing"), lambda: {
                "available": {"value": 1}, "missing": None,
            }),
            probe_mod.ProbeCollector("bad", ("failed",), lambda: (_ for _ in ()).throw(RuntimeError("boom"))),
        )

        results = probe_mod.collect_probe_results(collectors)

        self.assertEqual(results["available"].status, probe_mod.ProbeStatus.AVAILABLE)
        self.assertEqual(results["missing"].status, probe_mod.ProbeStatus.UNAVAILABLE)
        self.assertEqual(results["failed"].status, probe_mod.ProbeStatus.FAILED)
        self.assertIn("boom", results["failed"].error)

    def test_shared_probe_has_no_welcome_dependency(self):
        source = pathlib.Path(probe_mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("kyth_welcome", source)

    def test_collect_snapshot_keys(self):
        with mock.patch(
            "kyth_shared.system.bootc.fetch_bootc_status_data",
            return_value={"ok": True},
        ), mock.patch(
            "kyth_shared.system.bootc.fetch_bootc_status_text",
            return_value="text",
        ), mock.patch(
            "kyth_shared.system.process.run_command",
        ) as run:
            # flatpak list
            flatpak = mock.Mock(returncode=0, stdout="com.a.B\ncom.c.D\n")
            lspci = mock.Mock(returncode=0, stdout="VGA: AMD\n")

            def side_effect(cmd, timeout=5):
                if cmd and cmd[0] == "flatpak":
                    return flatpak
                if cmd and cmd[0] == "lspci":
                    return lspci
                return mock.Mock(returncode=1, stdout="")

            run.side_effect = side_effect
            sections = probe_mod.collect_snapshot()

        self.assertEqual(sections["bootc-status-data"], {"ok": True})
        self.assertEqual(sections["bootc-status-text"], "text")
        self.assertEqual(sections["flatpak-apps"], ["com.a.B", "com.c.D"])
        self.assertIs(sections["nvidia-detect"], False)


if __name__ == "__main__":
    unittest.main()
