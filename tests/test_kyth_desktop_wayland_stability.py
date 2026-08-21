"""OS-level Plasma / Wayland / desktop stack stability (not System Hub)."""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared import plasma_drift as drift_mod  # noqa: E402
from kyth_shared import pipewire_latency as pw_mod  # noqa: E402
from kyth_shared.system import desktop_stack as stack_mod  # noqa: E402
from kyth_shared.system import plasma_hdr as hdr_mod  # noqa: E402


class PlasmaHdrTests(unittest.TestCase):
    def test_unknown_preset_rejected(self):
        ok, msg = hdr_mod.apply_preset("nope")
        self.assertFalse(ok)
        self.assertIn("unknown", msg)

    def test_dry_run(self):
        ok, msg = hdr_mod.apply_preset("vrr", dry_run=True)
        self.assertTrue(ok)
        self.assertIn("dry-run", msg)

    def test_vrr_writes_wayland_vrrpolicy_and_rolls_back_on_failure(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            kwinrc = home / "kwinrc"
            kwinrc.write_text("[Wayland]\nVrrPolicy=1\n", encoding="utf-8")
            with mock.patch.dict("os.environ", {"XDG_CONFIG_HOME": str(home)}), mock.patch.object(
                hdr_mod, "_kwriteconfig_bin", return_value="/bin/kwriteconfig6"
            ), mock.patch.object(hdr_mod, "_reconfigure_kwin"), mock.patch.object(
                hdr_mod,
                "_run",
                side_effect=RuntimeError("boom"),
            ):
                ok, msg = hdr_mod.apply_preset("vrr_off")
            self.assertFalse(ok)
            self.assertIn("boom", msg)
            self.assertEqual(kwinrc.read_text(encoding="utf-8"), "[Wayland]\nVrrPolicy=1\n")

    def test_apply_uses_section_keys_via_kwriteconfig(self):
        calls: list[list[str]] = []

        def fake_run(args, **_kwargs):
            calls.append(list(args))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            with mock.patch.dict("os.environ", {"XDG_CONFIG_HOME": str(home), "XDG_SESSION_TYPE": "x11"}), mock.patch.object(
                hdr_mod, "_kwriteconfig_bin", return_value="kwriteconfig6"
            ), mock.patch.object(hdr_mod, "_run", side_effect=fake_run), mock.patch.object(
                hdr_mod, "_reconfigure_kwin"
            ), mock.patch.object(hdr_mod.shutil, "which", return_value=None):
                ok, msg = hdr_mod.apply_preset("vrr")
            self.assertTrue(ok)
            self.assertIn("Wayland.VrrPolicy=1", msg)
            self.assertTrue(any("--group" in c and "Wayland" in c and "VrrPolicy" in c for c in calls))

    def test_preset_status_is_section_aware(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "kwinrc").write_text(
                "[Compositing]\nVrrPolicy=1\n[Wayland]\nVrrPolicy=0\n",
                encoding="utf-8",
            )
            with mock.patch.dict("os.environ", {"XDG_CONFIG_HOME": str(home)}):
                # vrr wants Wayland VrrPolicy=1 — Compositing value must not count.
                self.assertIn("not active", hdr_mod.preset_status("vrr"))
                (home / "kwinrc").write_text("[Wayland]\nVrrPolicy=1\n", encoding="utf-8")
                self.assertEqual(hdr_mod.preset_status("vrr"), "active")


class PlasmaDriftTests(unittest.TestCase):
    def test_flatten_nested_toml_sections(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "plasma.toml"
            p.write_text(
                '[kwinrc.Compositing]\nLatencyPolicy = "extreme"\n'
                '[plasmarc]\nTheme = "kyth-dark"\n',
                encoding="utf-8",
            )
            loaded = drift_mod.load_plasma(p)
            self.assertEqual(loaded["kwinrc.Compositing"]["LatencyPolicy"], "extreme")
            self.assertEqual(loaded["plasmarc"]["Theme"], "kyth-dark")

    def test_parse_section_defaults_to_general(self):
        conf, groups = drift_mod._parse_section("kwinrc")
        self.assertEqual(conf, "kwinrc")
        self.assertEqual(groups, ["General"])
        conf, groups = drift_mod._parse_section("kwinrc.Compositing")
        self.assertEqual(groups, ["Compositing"])

    def test_apply_uses_nested_groups_and_kwriteconfig6(self):
        calls: list[list[str]] = []

        def fake_run(args, **_kwargs):
            calls.append(list(args))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(drift_mod, "_kwriteconfig_bin", return_value="kwriteconfig6"), mock.patch.object(
            drift_mod, "run", side_effect=fake_run
        ), mock.patch.object(drift_mod, "_reconfigure_kwin"), mock.patch.object(
            drift_mod, "_atomic_write_text"
        ):
            applied = drift_mod.apply_plasma({"kwinrc.Compositing": {"LatencyPolicy": "extreme"}})
        self.assertEqual(applied, ["kwinrc.Compositing:LatencyPolicy=extreme"])
        self.assertEqual(
            calls[0],
            [
                "kwriteconfig6",
                "--file",
                "kwinrc",
                "--group",
                "Compositing",
                "--key",
                "LatencyPolicy",
                "extreme",
            ],
        )


class PipewireLatencyApplyTests(unittest.TestCase):
    def test_apply_writes_real_quantum_dropin_and_env_map(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            dropin = td_path / "pipewire.conf.d" / "99-kyth-latency.conf"
            env_map = td_path / "pipewire-latency.env"
            notes = pw_mod.apply_pipewire_latency(
                {"default": 128, "game.exe": 64},
                quantum_dropin=dropin,
                env_map=env_map,
            )
            self.assertTrue(dropin.exists())
            body = dropin.read_text(encoding="utf-8")
            self.assertIn("default.clock.quantum = 128", body)
            self.assertNotIn("-- ", body)  # must not be comment-only
            env_body = env_map.read_text(encoding="utf-8")
            self.assertIn("game.exe=PIPEWIRE_LATENCY=64/48000", env_body)
            self.assertTrue(any("quantum=128" in n for n in notes))


class DesktopStackTests(unittest.TestCase):
    def test_greeter_context_skips_user_units(self):
        checks = stack_mod.desktop_stack_checks(
            has_session_bus=lambda: False,
            path_exists=lambda p: p.endswith("xdg-desktop-portal"),
            which=lambda _n: None,
        )
        names = {c.name for c in checks}
        self.assertIn("Portal packages", names)
        self.assertIn("User desktop session", names)
        self.assertTrue(all(c.passed for c in checks if c.name == "User desktop session"))
        self.assertNotIn("PipeWire", names)

    def test_wayland_session_reports_missing_portal_unit(self):
        checks = stack_mod.desktop_stack_checks(
            has_session_bus=lambda: True,
            session_type=lambda: "wayland",
            wayland_display=lambda: "wayland-0",
            user_unit_active=lambda unit: unit in {"pipewire.service", "wireplumber.service"},
            path_exists=lambda _p: True,
            which=lambda _n: "/usr/bin/xdg-desktop-portal",
        )
        by_name = {c.name: c for c in checks}
        self.assertTrue(by_name["Wayland display"].passed)
        self.assertFalse(by_name["xdg-desktop-portal"].passed)
        self.assertTrue(by_name["xdg-desktop-portal"].advisory)
        self.assertTrue(by_name["PipeWire"].passed)

    def test_packages_script_lists_portal_rpms(self):
        body = (
            ROOT / "build_files/scripts/packages/18-desktop-helper-and-creator-tooling.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("xdg-desktop-portal-kde", body)
        self.assertIn("xdg-desktop-portal", body)

    def test_docs_describe_wayland_bare_metal_default(self):
        body = (ROOT / "docs/plasma-wayland-polish.md").read_text(encoding="utf-8")
        self.assertIn("Bare metal", body)
        self.assertIn("Wayland", body)
        self.assertNotIn("intentionally starts Plasma X11", body)


if __name__ == "__main__":
    unittest.main()
