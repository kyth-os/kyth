"""On-disk probe cache (Phase F) — pure stdlib, no Qt."""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-welcome"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.system import probe as probe_mod  # noqa: E402
from kyth_shared.system import process as process_mod  # noqa: E402


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


class ProbeCachedIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self._tmp.name) / "probe-cache.json"
        process_mod._PROBE_CACHE.clear()

    def tearDown(self):
        process_mod._PROBE_CACHE.clear()
        self._tmp.cleanup()

    def test_memory_hit_skips_fetch(self):
        calls = {"n": 0}

        def fetch():
            calls["n"] += 1
            return "live"

        # Seed memory
        process_mod._PROBE_CACHE["bootc-status-text"] = (time.monotonic(), "cached")
        val = process_mod._probe_cached("bootc-status-text", 5.0, fetch)
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
            process_mod._PROBE_CACHE.clear()
            val = process_mod._probe_cached("bootc-status-text", 5.0, fetch)
        self.assertEqual(val, "from-disk")
        self.assertEqual(calls["n"], 0)

    def test_invalidate_clears_memory_and_disk(self):
        probe_mod.update_sections({"nvidia-detect": True}, path=self.path)
        process_mod._PROBE_CACHE["nvidia-detect"] = (time.monotonic(), True)
        with mock.patch.object(
            probe_mod, "cache_read_paths", return_value=[self.path]
        ):
            process_mod._invalidate_probe_caches()
        self.assertNotIn("nvidia-detect", process_mod._PROBE_CACHE)
        doc = json.loads(self.path.read_text())
        self.assertNotIn("nvidia-detect", doc.get("sections", {}))

    def test_disk_section_usable_helpers(self):
        self.assertFalse(process_mod._disk_section_usable("flatpak-apps", None))
        self.assertTrue(process_mod._disk_section_usable("nvidia-detect", False))
        self.assertTrue(process_mod._disk_section_usable("flatpak-apps", []))
        self.assertFalse(process_mod._disk_section_usable("bootc-status-text", ""))


class CollectSnapshotTests(unittest.TestCase):
    def test_collect_snapshot_keys(self):
        with mock.patch(
            "kyth_shared.system.bootc._fetch_bootc_status_data",
            return_value={"ok": True},
        ), mock.patch(
            "kyth_shared.system.bootc._fetch_bootc_status_text",
            return_value="text",
        ), mock.patch(
            "kyth_shared.system.process._run_command",
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
