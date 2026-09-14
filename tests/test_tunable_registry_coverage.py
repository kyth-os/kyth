"""Tunable coverage gate: every Python tunable must resolve to native code.

The native `kyth-tunable` dispatcher owns sysctl and module profiles at
runtime (see src/kyth-shared-rs/src/tunable_bin.rs and
system/tunable_registry.rs). This test pins that contract from the Python
side so a new `*_tune.py` / `*_preset.py` module cannot land without a
registry entry, a first-class Rust module, or an explicit exemption:

- `tunables.toml` `module = "..."` entries (dispatcher source of truth),
- the Rust fallback registry (offline/default path),
- first-class `system/*.rs` modules (e.g. `memory_tune.rs`),
- NATIVE_MODULES: presets whose TOML contract lives in a Rust module with
  a different name (each mapping verified by the preset's TOML filename
  appearing in that module).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY_DIR = ROOT / "src" / "kyth_shared" / "kyth_shared"
RS_SYSTEM = ROOT / "src" / "kyth-shared-rs" / "src" / "system"
TOML_PATH = ROOT / "build_files" / "config" / "tunables.toml"
REGISTRY_RS = RS_SYSTEM / "tunable_registry.rs"

# Preset -> Rust module owning its TOML contract (verified: each preset's
# TOML filename appears in the mapped module).
NATIVE_MODULES = {
    "backup_preset": "backup_config",
    "bluetooth_preset": "bluetooth",
    "cloud_preset": "network_services",
    "driver_preset": "driver_config",
    "fonts_preset": "preference_presets",
    "locale_preset": "preference_presets",
    "office_preset": "office",
    "plymouth_preset": "service_preferences",
    "polkit_preset": "service_preferences",
    "print_preset": "print_config",
    "privacy_preset": "privacy",
    "scx_preset": "service_preferences",
    "search_preset": "search_config",
    "selinux_preset": "selinux_preset",
    "signing_preset": "signing",
}

# Non-tunable modules matching the filename heuristic that are covered by
# other means (facades over ported helpers, deprecated shims, dispatchers).
EXEMPT = {
    # Re-export facade over atomic_io (ported as atomic_io.rs).
    "gaming_scan_atomic",
    # Deprecated shim delegating to memory_tune (ported).
    "zram",
}


def tunable_candidates() -> list[str]:
    names = []
    for path in sorted(PY_DIR.glob("*.py")):
        name = path.stem
        if name.startswith("_") or name in ("tunable",):
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        if path.name.endswith(("_tune.py", "_preset.py")) or "sysctl" in body.lower():
            names.append(name)
    return names


def toml_modules() -> set[str]:
    return set(
        re.findall(r'^module = "([^"]+)"', TOML_PATH.read_text(encoding="utf-8"), re.M)
    )


def fallback_modules() -> set[str]:
    body = REGISTRY_RS.read_text(encoding="utf-8")
    return set(re.findall(r'\(\s*"[^"]+",\s*"([a-z0-9_]+)"\s*\)', body))


def rust_system_modules() -> set[str]:
    return {path.stem for path in RS_SYSTEM.glob("*.rs")}


class TunableRegistryCoverageTests(unittest.TestCase):
    def test_every_python_tunable_resolves_to_native_code(self) -> None:
        covered = toml_modules() | fallback_modules() | rust_system_modules()
        uncovered = [
            name
            for name in tunable_candidates()
            if name not in covered
            and name not in NATIVE_MODULES
            and name not in EXEMPT
        ]
        self.assertEqual(
            uncovered,
            [],
            "tunable-shaped Python modules without native coverage: "
            "add a tunables.toml entry, a Rust module, or document an exemption",
        )

    def test_native_module_mappings_own_the_preset_toml(self) -> None:
        for python_module, rust_module in NATIVE_MODULES.items():
            with self.subTest(preset=python_module):
                body = (PY_DIR / f"{python_module}.py").read_text(encoding="utf-8")
                tomls = set(re.findall(r'"([a-z_]+\.toml)"', body))
                self.assertTrue(tomls, f"{python_module} names no TOML contract")
                rust = (RS_SYSTEM / f"{rust_module}.rs").read_text(encoding="utf-8")
                for toml in tomls:
                    self.assertIn(
                        toml,
                        rust,
                        f"{rust_module}.rs does not own {toml} "
                        f"(mapping for {python_module} is stale)",
                    )

    def test_every_registry_entry_resolves_to_an_implementation(self) -> None:
        python_modules = {path.stem for path in PY_DIR.glob("*.py")}
        rust_modules = rust_system_modules()
        dangling = [
            name
            for name in sorted(toml_modules() | fallback_modules())
            if name not in python_modules and name not in rust_modules
        ]
        self.assertEqual(
            dangling,
            [],
            "registry entries without a Python or Rust implementation",
        )


if __name__ == "__main__":
    unittest.main()
