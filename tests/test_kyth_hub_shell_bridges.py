"""backend/*.py bridges (src/kyth-hub-web/src-tauri/backend/) — the
subprocess boundary main.rs's Tauri commands shell out to. Invoked exactly
as main.rs invokes them (a bare `python3 <script> [args]` with PYTHONPATH
set to kyth_shared), so a regression here is a regression the Rust side
would actually hit.

Each bridge is read-only against kyth_shared state; tests isolate that
state via XDG_STATE_HOME/XDG_RUNTIME_DIR/HOME overrides so this never
touches the real machine's Guardian history or probe cache.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "src" / "kyth-hub-web" / "src-tauri" / "backend"
KYTH_SHARED_PYTHONPATH = str(ROOT / "src" / "kyth_shared")


def _run_bridge(script: str, args: list[str] | None = None, *, env_extra: dict[str, str] | None = None) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = KYTH_SHARED_PYTHONPATH
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        [sys.executable, str(BACKEND_DIR / script), *(args or [])],
        capture_output=True, text=True, env=env, timeout=15, check=False,
    )
    assert result.returncode == 0, f"{script} exited {result.returncode}: {result.stderr}"
    return json.loads(result.stdout)


class ProbeBridgeTests(unittest.TestCase):
    def test_missing_cache_returns_null_data_not_an_error(self):
        with tempfile.TemporaryDirectory() as home:
            payload = _run_bridge(
                "probe_bridge.py", ["bootc-branch"],
                env_extra={"HOME": home, "XDG_RUNTIME_DIR": home, "XDG_CACHE_HOME": home},
            )
        self.assertEqual(payload, {"key": "bootc-branch", "data": None, "error": None})

    def test_unknown_key_returns_null_data_not_a_crash(self):
        payload = _run_bridge("probe_bridge.py", ["not-a-real-probe-key"])
        self.assertIsNone(payload["data"])
        self.assertIsNone(payload["error"])

    def test_reads_a_real_cache_entry_within_ttl(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            cache_dir = Path(runtime_dir) / "kyth"
            cache_dir.mkdir(parents=True)
            doc = {
                "version": 2, "generated_at": time.time(),
                "sections": {"bootc-branch": {"ts": time.time(), "data": "testing"}},
            }
            (cache_dir / "probe-cache.json").write_text(json.dumps(doc), encoding="utf-8")
            payload = _run_bridge(
                "probe_bridge.py", ["bootc-branch"],
                env_extra={"XDG_RUNTIME_DIR": runtime_dir},
            )
        self.assertEqual(payload, {"key": "bootc-branch", "data": "testing", "error": None})


class GuardianBridgeTests(unittest.TestCase):
    def test_no_state_file_yet_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as state_home:
            payload = _run_bridge("guardian_bridge.py", env_extra={"XDG_STATE_HOME": state_home})
        self.assertEqual(payload, {"pending_count": 0, "history": []})

    def test_pending_recommendation_surfaces_with_its_recipe_title(self):
        with tempfile.TemporaryDirectory() as state_home:
            state_dir = Path(state_home) / "kyth"
            state_dir.mkdir(parents=True)
            state = {
                "schema_version": 1,
                "history": [{
                    "timestamp": time.time(), "recipe_id": "audio.restart",
                    "source": "deterministic", "confidence": 1.0,
                    "explanation": "audio symptom", "action": "recommended",
                    "verified": None, "detail": "",
                }],
                "occurrences": {},
            }
            (state_dir / "guardian.json").write_text(json.dumps(state), encoding="utf-8")
            payload = _run_bridge("guardian_bridge.py", env_extra={"XDG_STATE_HOME": state_home})
        self.assertEqual(payload["pending_count"], 1)
        self.assertEqual(len(payload["history"]), 1)
        self.assertEqual(payload["history"][0]["title"], "Restart audio services")
        self.assertEqual(payload["history"][0]["action"], "recommended")

    def test_history_is_most_recent_first_and_capped(self):
        with tempfile.TemporaryDirectory() as state_home:
            state_dir = Path(state_home) / "kyth"
            state_dir.mkdir(parents=True)
            now = time.time()
            history = [
                {"timestamp": now - i, "recipe_id": "audio.restart", "action": "executed", "verified": True, "detail": f"run {i}"}
                for i in range(12)
            ]
            state = {"schema_version": 1, "history": history, "occurrences": {}}
            (state_dir / "guardian.json").write_text(json.dumps(state), encoding="utf-8")
            payload = _run_bridge("guardian_bridge.py", env_extra={"XDG_STATE_HOME": state_home})
        self.assertEqual(len(payload["history"]), 8)  # capped, see guardian_bridge.py
        self.assertEqual(payload["history"][0]["detail"], "run 0")  # most recent (smallest i => largest timestamp) first


class HardwareBridgeTests(unittest.TestCase):
    def test_no_lspci_on_path_returns_null_not_an_error(self):
        with tempfile.TemporaryDirectory() as empty_path_dir:
            payload = _run_bridge("hardware_bridge.py", env_extra={"PATH": empty_path_dir})
        self.assertEqual(payload, {"gpu_line": None})

    def test_first_matching_lspci_line_is_returned(self):
        with tempfile.TemporaryDirectory() as fake_bin:
            fake_lspci = Path(fake_bin) / "lspci"
            fake_lspci.write_text(
                "#!/bin/sh\n"
                'echo "00:02.0 Unclassified device [0000]: Example Corp Widget [1234:0000]"\n'
                'echo "03:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. Navi 31 [1002:744c] (rev c8)"\n',
                encoding="utf-8",
            )
            fake_lspci.chmod(0o755)
            payload = _run_bridge("hardware_bridge.py", env_extra={"PATH": fake_bin})
        self.assertIsNotNone(payload["gpu_line"])
        self.assertIn("VGA compatible controller", payload["gpu_line"])
        self.assertNotIn("Unclassified device", payload["gpu_line"])


if __name__ == "__main__":
    unittest.main()
