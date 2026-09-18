"""Family-stack correctness: telemetry opt-in, print honesty, BT guard, exe hints."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared import pipewire_gaming
from kyth_shared import print_preset
from kyth_shared import telemetry_opt


class TestTelemetryOptInDefault(unittest.TestCase):
    def test_missing_config_is_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = telemetry_opt.load_telemetry_opt(Path(tmp) / "absent.toml")
            self.assertFalse(cfg["enabled"])
            self.assertEqual(cfg["collectors"], [])

    def test_partial_config_stays_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "telemetry-opt.toml"
            p.write_text('collectors = ["cpu"]\n', encoding="utf-8")
            cfg = telemetry_opt.load_telemetry_opt(p)
            self.assertFalse(cfg["enabled"])
            self.assertEqual(telemetry_opt.telemetry_collectors_status(p), [])

    def test_explicit_opt_in_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "telemetry-opt.toml"
            telemetry_opt.save_telemetry_opt(
                {"enabled": True, "collectors": []}, p
            )
            self.assertTrue(telemetry_opt.load_telemetry_opt(p)["enabled"])


class TestPrintAirscanHonesty(unittest.TestCase):
    def test_missing_config_disables_airscan(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = print_preset.load_print(Path(tmp) / "absent.toml")
            self.assertFalse(cfg["airscan"])

    def test_partial_config_disables_airscan(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "print.toml"
            p.write_text("auto_add = true\n", encoding="utf-8")
            self.assertFalse(print_preset.load_print(p)["airscan"])


class TestBluetoothQuantumGuard(unittest.TestCase):
    def _gaming_paths(self, tmp):
        base = Path(tmp)
        return (
            {"profile": "gaming", "quantum": 128},
            base / "99-kyth-gaming.lua",
            base / "99-kyth-gaming.conf",
        )

    def test_bt_active_skips_quantum_dropin(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg, dest, qdest = self._gaming_paths(tmp)
            qdest.write_text("stale\n", encoding="utf-8")
            out = pipewire_gaming.generate_pipewire_gaming(
                cfg, dest, qdest, bt_active=True
            )
            self.assertEqual(out, dest)  # ALSA rules still applied
            self.assertTrue(dest.exists())
            self.assertFalse(qdest.exists())  # stale 128 cleared, none written

    def test_no_bt_writes_quantum_dropin(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg, dest, qdest = self._gaming_paths(tmp)
            out = pipewire_gaming.generate_pipewire_gaming(
                cfg, dest, qdest, bt_active=False
            )
            self.assertEqual(out, dest)
            self.assertIn("quantum       = 128", qdest.read_text(encoding="utf-8"))

    def test_probe_fails_closed_without_tools(self):
        with (
            patch("shutil.which", return_value=None),
            patch(
                "kyth_shared.pipewire_gaming.run_optional",
                side_effect=AssertionError("must not probe"),
            ),
        ):
            self.assertFalse(pipewire_gaming.bluetooth_audio_active())

    def test_probe_detects_bluez_sink(self):
        def fake_run(argv, **kwargs):
            class R:
                stdout = (
                    "1\tbluez_output.XX_YY  module-bluez5-device.c  s16le 2ch 48000Hz\n"
                    if argv[0] == "pactl"
                    else ""
                )

            return R()

        with (
            patch("shutil.which", return_value="/usr/bin/pactl"),
            patch(
                "kyth_shared.pipewire_gaming.run_optional", side_effect=fake_run
            ),
        ):
            self.assertTrue(pipewire_gaming.bluetooth_audio_active())


if __name__ == "__main__":
    unittest.main()
