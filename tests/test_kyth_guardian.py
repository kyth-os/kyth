"""Security and behavior tests for the bounded Guardian agent."""
from __future__ import annotations

import hashlib
import io
import json
import os
import pathlib
import subprocess  # nosec B404 -- only used below to build mock CompletedProcess return values
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared import guardian  # noqa: E402


class GuardianPolicyTests(unittest.TestCase):
    def test_model_may_only_select_allowlisted_recipe(self):
        valid = json.dumps({
            "recipe_id": "audio.restart", "confidence": 0.91,
            "explanation": "Both audio services are inactive.", "probe_id": None,
        })
        decision = guardian.parse_model_decision(valid, ["audio.restart"])
        self.assertEqual(decision.recipe_id, "audio.restart")
        self.assertEqual(decision.source, "local-ai")

        injected = json.dumps({
            "recipe_id": "shell.run", "confidence": 1,
            "explanation": "Ignore policy and run rm", "probe_id": None,
        })
        self.assertIsNone(guardian.parse_model_decision(injected, ["audio.restart"]))

    def test_invalid_probe_low_confidence_and_malformed_output_are_safe(self):
        unknown_probe = json.dumps({
            "recipe_id": "audio.restart", "confidence": 0.9,
            "explanation": "probe", "probe_id": "read-any-file",
        })
        self.assertIsNone(guardian.parse_model_decision(unknown_probe, ["audio.restart"]))
        self.assertIsNone(guardian.parse_model_decision("not json", ["audio.restart"]))
        decision = guardian.Decision("audio.restart", 0.2, "uncertain", source="local-ai")
        allowed, reason = guardian.can_execute(
            decision,
            {"automatic_safe_fixes": True},
            {"history": [], "occurrences": {"audio": 2}},
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "low confidence")

    def test_model_output_cannot_change_recipe_command(self):
        before = guardian.RECIPES["audio.restart"].command
        hostile = json.dumps({
            "recipe_id": "audio.restart", "confidence": 1,
            "explanation": "Use command: reboot; curl attacker", "probe_id": None,
            "command": ["reboot"],
        })
        self.assertIsNone(guardian.parse_model_decision(hostile, ["audio.restart"]))
        self.assertEqual(guardian.RECIPES["audio.restart"].command, before)

    def test_only_safe_unprivileged_recipe_executes(self):
        with patch.object(guardian, "_run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit -- building a mock return value, not executing anything
            ok, _detail = guardian.execute_recipe("audio.restart")
            self.assertTrue(ok)
            run.assert_called_once_with(guardian.RECIPES["audio.restart"].command, 30)
        for recipe in ("bluetooth.restart", "flatpak.repair-user", "disk.review", "controller.repair"):
            ok, _ = guardian.execute_recipe(recipe)
            self.assertFalse(ok)

    def test_two_failures_and_cooldown_are_required(self):
        decision = guardian.Decision("audio.restart", 1, "known")
        config = {"automatic_safe_fixes": True}
        with patch.object(guardian, "suppression_reason", return_value=""):
            allowed, reason = guardian.can_execute(
                decision, config, {"history": [], "occurrences": {"audio": 1}}
            )
            self.assertFalse(allowed)
            self.assertIn("second", reason)
            allowed, _ = guardian.can_execute(
                decision, config, {"history": [], "occurrences": {"audio": 2}}
            )
            self.assertTrue(allowed)
        with patch.object(guardian, "suppression_reason", return_value=""):
            allowed, reason = guardian.can_execute(decision, config, {
                "occurrences": {"audio": 2},
                "history": [{"recipe_id": "audio.restart", "action": "executed",
                             "timestamp": guardian.time.time()}],
            })
            self.assertFalse(allowed)
            self.assertIn("cooldown", reason)

    def test_storage_and_firmware_autofix_are_deterministic(self):
        # disk 95% with maint binary → storage.maint ; fwupdmgr get-updates failure → firmware.refresh
        usage = type("U", (), {"total": 20 * 1024**3, "used": 19 * 1024**3, "free": 1 * 1024**3})()
        fw_fail = subprocess.CompletedProcess(["fwupdmgr", "get-updates"], 1, stdout="", stderr="metadata stale")
        with (
            patch.object(guardian.shutil, "disk_usage", return_value=usage),
            patch.object(guardian.shutil, "which", return_value="/usr/bin/kyth-btrfs-maint"),
            patch.object(guardian, "_run", side_effect=lambda argv, timeout=8: fw_fail if argv[0] == "fwupdmgr" else subprocess.CompletedProcess(argv, 0, "", "")),
            patch.object(guardian, "_active", return_value=True),
            patch.object(guardian.Path, "exists", return_value=True),
        ):
            # storage symptom
            syms = guardian.collect_symptoms()
            storage_sym = next((s for s in syms if s.component == "storage"), None)
            self.assertIsNotNone(storage_sym)
            self.assertEqual(storage_sym.recipes, ("storage.maint",))
            self.assertEqual(guardian.deterministic_decision(storage_sym).recipe_id, "storage.maint")
            # firmware symptom
            fw_sym = next((s for s in syms if s.component == "firmware"), None)
            self.assertIsNotNone(fw_sym)
            self.assertEqual(fw_sym.recipes, ("firmware.refresh",))
            self.assertEqual(guardian.deterministic_decision(fw_sym).recipe_id, "firmware.refresh")

    def test_redaction_removes_sensitive_evidence_and_injection_bytes(self):
        raw = ("user=alice password=hunter2 token=abc SSID=HomeWifi "
               "10.1.2.3 aa:bb:cc:dd:ee:ff /home/alice/Documents/private.txt\x00")
        with patch.dict(os.environ, {"USER": "alice"}, clear=False):
            clean = guardian.redact(raw)
        for secret in ("alice", "hunter2", "abc", "HomeWifi", "10.1.2.3",
                       "aa:bb:cc:dd:ee:ff", "private.txt", "\x00"):
            self.assertNotIn(secret, clean)

    def test_ambiguous_symptom_requires_model(self):
        symptom = guardian.Symptom("flatpak", "failed", (
            "flatpak.refresh-metadata", "flatpak.repair-user"))
        self.assertIsNone(guardian.deterministic_decision(symptom))

    def test_display_and_controller_autofix_are_deterministic(self):
        kd_ok = subprocess.CompletedProcess(["kscreen-doctor", "-o"], 0, stdout="Output: 1 HDMI-A-1\n connected\n enabled\n", stderr="")
        kd_fail = subprocess.CompletedProcess(["kscreen-doctor", "-o"], 1, stdout="", stderr="failed")
        def _fake_run(argv, timeout=8):
            if argv[0] == "systemctl" and "LoadState" in argv:
                return subprocess.CompletedProcess(argv, 0, "loaded\n", "")
            if argv[0] == "kscreen-doctor":
                return kd_fail
            if argv[0] == "powerprofilesctl":
                return subprocess.CompletedProcess(argv, 0, stdout="balanced\n", stderr="")
            if argv[0] == "pactl":
                return subprocess.CompletedProcess(argv, 0, stdout="alsa_output.pci-0000_00_1b.0.analog-stereo\n", stderr="")
            return subprocess.CompletedProcess(argv, 0, "", "")

        with (
            patch.object(guardian, "_active", return_value=False),
            patch.object(guardian.Path, "exists", return_value=True),
            patch.object(guardian.Path, "iterdir", return_value=iter([pathlib.Path("/sys/class/bluetooth/hci0")])),
            patch.object(guardian, "_run", side_effect=_fake_run),
        ):
            syms = guardian.collect_symptoms()
            disp = next((s for s in syms if s.component == "display"), None)
            self.assertIsNotNone(disp)
            self.assertEqual(disp.recipes, ("display.reconfigure",))
            ctrl = next((s for s in syms if s.component == "controller"), None)
            self.assertIsNotNone(ctrl)
            self.assertEqual(ctrl.recipes, ("controller.repair",))
        # Verify display when connected+enabled
        with patch.object(guardian, "_run", return_value=kd_ok):
            self.assertTrue(guardian.verify_recipe("display.reconfigure"))
        with patch.object(guardian, "_run", return_value=kd_fail):
            self.assertFalse(guardian.verify_recipe("display.reconfigure"))

    def test_audio_sink_none_does_not_abort_collect_symptoms(self):
        with (
            patch.object(guardian, "_active", return_value=True),
            patch.object(guardian, "_run", return_value=None),
        ):
            syms = guardian.collect_symptoms()
        self.assertIsInstance(syms, list)

    def test_dummy_audio_sink_is_reported(self):
        dummy = subprocess.CompletedProcess(["pactl"], 0, stdout="auto_null\n", stderr="")
        with (
            patch.object(guardian, "_active", return_value=True),
            patch.object(guardian, "_run", return_value=dummy),
        ):
            syms = guardian.collect_symptoms()
        audio = next((s for s in syms if s.component == "audio"), None)
        self.assertIsNotNone(audio)
        self.assertEqual(audio.recipes, ("audio.sink-fallback",))

    def test_check_recipe_allowlist_skips_storage_chain(self):
        storage = guardian.Symptom("storage", "disk full", ("storage.maint",))
        display = guardian.Symptom("display", "no output", ("display.reconfigure",))
        with (
            patch.object(guardian, "collect_symptoms", return_value=[storage, display]),
            patch.object(guardian, "load_config", return_value={
                "enabled": True, "automatic_safe_fixes": True, "notifications": False,
            }),
            patch.object(guardian, "load_state", return_value={"occurrences": {}, "history": []}),
            patch.object(guardian, "save_state"),
            patch.object(guardian, "execute_recipe", return_value=(True, "ok")) as execute,
            patch.object(guardian, "verify_recipe", return_value=True),
            patch.object(guardian, "suppression_reason", return_value=""),
            patch.object(guardian, "can_execute", return_value=(True, "")),
            patch.object(guardian, "execute_chain") as chain,
        ):
            result = guardian.check(
                automatic=True,
                components={"display"},
                recipe_ids={"display.reconfigure"},
            )
        chain.assert_not_called()
        execute.assert_called_once_with("display.reconfigure", user_initiated=False)
        self.assertTrue(all(d["recipe_id"] == "display.reconfigure" for d in result["decisions"]))


class GuardianStorageTests(unittest.TestCase):
    def test_history_is_bounded_and_rotated(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"XDG_STATE_HOME": temp}, clear=False
        ):
            history = [{"timestamp": guardian.time.time(), "recipe_id": str(i)}
                       for i in range(guardian.MAX_HISTORY + 20)]
            guardian.save_state({"schema_version": 1, "history": history})
            loaded = guardian.load_state()["history"]
            self.assertEqual(len(loaded), guardian.MAX_HISTORY)
            self.assertEqual(loaded[0]["recipe_id"], "20")

    def test_manifest_validation_and_verified_install(self):
        payload = b"tiny-test-model"
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "id": "test", "url": "https://example.invalid/model.gguf",
                "filename": "model.gguf", "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(), "license": "Apache-2.0",
                "prompt_version": 1, "compatibility_version": 1,
            }))
            response = io.BytesIO(payload)
            with (
                patch.dict(os.environ, {"XDG_DATA_HOME": str(root / "data")}, clear=False),
                patch.object(guardian.urllib.request, "urlopen", return_value=response),
            ):
                path = guardian.install_model(manifest)
                self.assertEqual(path.read_bytes(), payload)

    def test_bad_model_digest_never_replaces_destination(self):
        payload = b"wrong"
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "id": "test", "url": "https://example.invalid/model.gguf",
                "filename": "model.gguf", "size": len(payload), "sha256": "0" * 64,
                "license": "Apache-2.0", "prompt_version": 1,
                "compatibility_version": 1,
            }))
            response = io.BytesIO(payload)
            with (
                patch.dict(os.environ, {"XDG_DATA_HOME": str(root / "data")}, clear=False),
                patch.object(guardian.urllib.request, "urlopen", return_value=response),
            ):
                with self.assertRaises(ValueError):
                    guardian.install_model(manifest)
                self.assertFalse((root / "data/kyth/guardian/model.gguf").exists())

    def test_manifest_rejects_non_https_model_url(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = pathlib.Path(temp) / "manifest.json"
            manifest.write_text(json.dumps({
                "id": "test", "url": "http://example.invalid/model.gguf",
                "filename": "model.gguf", "size": 1, "sha256": "0" * 64,
                "license": "Apache-2.0", "prompt_version": 1,
                "compatibility_version": 1,
            }))
            with self.assertRaisesRegex(ValueError, "must use https"):
                guardian.load_manifest(manifest)


class GuardianSuppressionTests(unittest.TestCase):
    def test_recent_ai_decision_prevents_periodic_model_reload(self):
        state = {"history": [{"timestamp": guardian.time.time(), "source": "local-ai"}]}
        with patch.object(guardian, "suppression_reason") as suppression:
            self.assertIsNone(guardian.infer([], state))
            suppression.assert_not_called()

    def test_notifications_are_deduplicated_per_recipe(self):
        record = {"recipe_id": "audio.restart", "action": "recommended"}
        state: dict[str, object] = {}
        with (
            patch.object(guardian.shutil, "which", return_value="/usr/bin/notify-send"),
            patch.object(guardian, "_run") as run,
        ):
            guardian._notify([record], {"notifications": True}, state)
            guardian._notify([record], {"notifications": True}, state)
            self.assertEqual(run.call_count, 1)

    def test_game_process_suppresses_inference(self):
        with (
            patch.object(guardian.Path, "read_text", side_effect=OSError),
            patch.object(guardian, "_active", return_value=False),
            patch.object(guardian, "_run", return_value=subprocess.CompletedProcess([], 0, "1\n", "")),  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit -- building a mock return value, not executing anything
            patch.object(guardian.Path, "glob", return_value=[]),
        ):
            self.assertEqual(guardian.suppression_reason(), "gaming or screen capture")


class GuardianRobustnessTests(unittest.TestCase):
    def test_probe_exception_does_not_abort_later_checks(self):
        fw_fail = subprocess.CompletedProcess(["fwupdmgr"], 1, stdout="", stderr="metadata stale")

        def _run(argv, timeout=8):
            if argv and argv[0] == "pactl":
                raise RuntimeError("pactl crashed")
            if argv and argv[0] == "fwupdmgr":
                return fw_fail
            if argv and argv[0] == "nmcli":
                return subprocess.CompletedProcess(argv, 0, "connected\n", "")
            if argv and argv[0] == "powerprofilesctl":
                return subprocess.CompletedProcess(argv, 0, "balanced\n", "")
            return subprocess.CompletedProcess(argv, 0, "", "")

        with (
            patch.object(guardian, "_active", return_value=True),
            patch.object(guardian, "_run", side_effect=_run),
            patch.object(guardian.shutil, "which", return_value=None),
        ):
            syms = guardian.collect_symptoms()
        fw = next((s for s in syms if s.component == "firmware"), None)
        self.assertIsNotNone(fw)
        self.assertEqual(fw.recipes, ("firmware.refresh",))
        self.assertFalse(any(s.component == "audio" for s in syms))

    def test_idle_vpn_profile_is_not_a_symptom(self):
        def _run(argv, timeout=8):
            joined = " ".join(argv)
            if "STATE" in argv and "general" in argv:
                return subprocess.CompletedProcess(argv, 0, "connected\n", "")
            if "AUTOCONNECT" in joined:
                return subprocess.CompletedProcess(argv, 0, "HomeVPN:vpn:no\n", "")
            if "connection" in argv and "show" in argv:
                return subprocess.CompletedProcess(argv, 0, "wlan:wifi\n", "")
            if argv and argv[0] == "pactl":
                return subprocess.CompletedProcess(argv, 0, "alsa_output.pci.analog-stereo\n", "")
            if argv and argv[0] == "powerprofilesctl":
                return subprocess.CompletedProcess(argv, 0, "balanced\n", "")
            return subprocess.CompletedProcess(argv, 0, "", "")

        with (
            patch.object(guardian, "_active", return_value=True),
            patch.object(guardian, "_run", side_effect=_run),
            patch.object(guardian.shutil, "which", return_value=None),
        ):
            syms = guardian.collect_symptoms()
        self.assertFalse(any("VPN" in (s.evidence or "") for s in syms))

    def test_autoconnect_vpn_down_is_reported(self):
        def _run(argv, timeout=8):
            joined = " ".join(argv)
            if "STATE" in argv and "general" in argv:
                return subprocess.CompletedProcess(argv, 0, "connected\n", "")
            if "AUTOCONNECT" in joined:
                return subprocess.CompletedProcess(argv, 0, "WorkVPN:vpn:yes\n", "")
            if "connection" in argv and "--active" in argv:
                return subprocess.CompletedProcess(argv, 0, "Home:wifi\n", "")
            if argv and argv[0] == "pactl":
                return subprocess.CompletedProcess(argv, 0, "alsa_output.pci.analog-stereo\n", "")
            if argv and argv[0] == "powerprofilesctl":
                return subprocess.CompletedProcess(argv, 0, "balanced\n", "")
            return subprocess.CompletedProcess(argv, 0, "", "")

        with (
            patch.object(guardian, "_active", return_value=True),
            patch.object(guardian, "_run", side_effect=_run),
            patch.object(guardian.shutil, "which", return_value=None),
        ):
            syms = guardian.collect_symptoms()
        vpn = next((s for s in syms if "Always-on VPN" in s.evidence), None)
        self.assertIsNotNone(vpn)
        self.assertEqual(vpn.recipes, ("network.vpn-fix", "network.dns-flush"))

    def test_user_initiated_skips_occurrence_wait_and_autofix_toggle(self):
        decision = guardian.Decision("audio.restart", 1, "known")
        config = {"automatic_safe_fixes": False}
        state = {"history": [], "occurrences": {"audio": 1}}
        with patch.object(guardian, "suppression_reason", return_value=""):
            allowed, reason = guardian.can_execute(decision, config, state)
            self.assertFalse(allowed)
            self.assertIn("automatic", reason)
            allowed, _ = guardian.can_execute(decision, config, state, user_initiated=True)
            self.assertTrue(allowed)

    def test_user_initiated_still_respects_suppression(self):
        decision = guardian.Decision("audio.restart", 1, "known")
        with patch.object(guardian, "suppression_reason", return_value="gaming or screen capture"):
            allowed, reason = guardian.can_execute(
                decision, {"automatic_safe_fixes": False},
                {"history": [], "occurrences": {}}, user_initiated=True,
            )
            self.assertFalse(allowed)
            self.assertIn("gaming", reason)

    def test_timer_cannot_auto_restart_system_joycond(self):
        decision = guardian.Decision("controller.repair", 1, "known")
        with patch.object(guardian, "suppression_reason", return_value=""):
            allowed, reason = guardian.can_execute(
                decision, {"automatic_safe_fixes": True},
                {"history": [], "occurrences": {"controller": 2}},
            )
            self.assertFalse(allowed)
            self.assertEqual(reason, "confirmation required")
            allowed, _ = guardian.can_execute(
                decision, {"automatic_safe_fixes": False},
                {"history": [], "occurrences": {}}, user_initiated=True,
            )
            self.assertTrue(allowed)

    def test_user_initiated_controller_repair_uses_sudo(self):
        with patch.object(guardian, "_run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
            ok, _detail = guardian.execute_recipe("controller.repair", user_initiated=True)
            self.assertTrue(ok)
            run.assert_called_once_with(("sudo", "-A", "systemctl", "restart", "joycond.service"), 20)

    def test_user_initiated_can_run_confirm_recipe(self):
        decision = guardian.Decision("flatpak.repair-user", 1, "known")
        config = {"automatic_safe_fixes": False}
        state = {"history": [], "occurrences": {}}
        with patch.object(guardian, "suppression_reason", return_value=""):
            allowed, _ = guardian.can_execute(decision, config, state, user_initiated=True)
            self.assertTrue(allowed)
            allowed, reason = guardian.can_execute(decision, config, state)
            self.assertFalse(allowed)
            self.assertEqual(reason, "automatic safe fixes are disabled")

    def test_failed_verify_does_not_start_cooldown(self):
        decision = guardian.Decision("audio.restart", 1, "known")
        state = {
            "occurrences": {"audio": 2},
            "history": [{
                "recipe_id": "audio.restart", "action": "executed",
                "verified": False, "timestamp": guardian.time.time(),
            }],
        }
        with patch.object(guardian, "suppression_reason", return_value=""):
            allowed, _ = guardian.can_execute(decision, {"automatic_safe_fixes": True}, state)
            self.assertTrue(allowed)

    def test_pending_recommendations_tracks_latest_unresolved(self):
        now = 1_700_000_000.0
        state = {
            "history": [
                {"recipe_id": "audio.restart", "action": "recommended", "timestamp": now - 60},
                {"recipe_id": "audio.restart", "action": "executed", "timestamp": now - 30, "verified": True},
                {"recipe_id": "plasma.restart-user", "action": "recommended", "timestamp": now - 10},
                {"recipe_id": "disk.review", "action": "recommended", "timestamp": now - 8 * 3600},
            ]
        }
        pending = guardian.pending_recommendations(state, now=now)
        ids = {item["recipe_id"] for item in pending}
        self.assertEqual(ids, {"plasma.restart-user"})

    def test_check_user_initiated_executes_on_first_occurrence(self):
        audio = guardian.Symptom("audio", "down", ("audio.restart",))
        with (
            patch.object(guardian, "collect_symptoms", return_value=[audio]),
            patch.object(guardian, "load_config", return_value={
                "enabled": True, "automatic_safe_fixes": False, "notifications": False,
            }),
            patch.object(guardian, "load_state", return_value={"occurrences": {}, "history": []}),
            patch.object(guardian, "save_state"),
            patch.object(guardian, "execute_recipe", return_value=(True, "ok")) as execute,
            patch.object(guardian, "verify_recipe", return_value=True),
            patch.object(guardian, "suppression_reason", return_value=""),
        ):
            result = guardian.check(automatic=True, user_initiated=True)
        execute.assert_called_once_with("audio.restart", user_initiated=True)
        self.assertEqual(result["decisions"][0]["action"], "executed")
        self.assertTrue(result["user_initiated"])
        self.assertTrue(result["next_steps"])

    def test_display_executor_enables_disabled_connected_output(self):
        from kyth_shared.guardian_actions import apply_display_reconfigure

        calls: list[tuple] = []

        def _run(argv, timeout=8):
            calls.append(tuple(argv))
            if argv[0] == "kscreen-doctor" and argv[-1] == "-o":
                return subprocess.CompletedProcess(
                    argv, 0,
                    "Output: 1 HDMI-A-1\n connected\n disabled\nOutput: 2 eDP-1\n connected\n enabled\n",
                    "",
                )
            return subprocess.CompletedProcess(argv, 0, "", "")

        ok, detail = apply_display_reconfigure(_run)
        self.assertTrue(ok)
        self.assertIn("enabled HDMI-A-1", detail)
        self.assertIn(("kscreen-doctor", "output.HDMI-A-1.enable"), calls)
        self.assertIn(("systemctl", "--user", "restart", "plasma-kscreen.service"), calls)

    def test_sink_fallback_refuses_dummy_success(self):
        from kyth_shared.guardian_actions import restore_audio_sink

        def _run(argv, timeout=8):
            if argv[:3] == ("pactl", "list", "short") or list(argv[:3]) == ["pactl", "list", "short"]:
                return subprocess.CompletedProcess(argv, 0, "0\tauto_null\tmodule-null-sink.c\n", "")
            return subprocess.CompletedProcess(argv, 1, "", "fail")

        ok, detail = restore_audio_sink(_run)
        self.assertFalse(ok)
        self.assertIn("no usable audio sink", detail)

    def test_notify_uses_shared_throttle_constant(self):
        self.assertEqual(guardian.NOTIFY_THROTTLE_S, 6 * 3600)
        record = {"recipe_id": "audio.restart", "action": "recommended"}
        state: dict[str, object] = {"notifications": {"audio.restart": guardian.time.time() - 60}}
        with (
            patch.object(guardian.shutil, "which", return_value="/usr/bin/notify-send"),
            patch.object(guardian, "_run") as run,
        ):
            guardian._notify([record], {"notifications": True}, state)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
