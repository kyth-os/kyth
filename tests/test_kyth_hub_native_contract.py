"""Static contract checks for the production Rust/Tauri Hub surface."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
TAURI = ROOT / "src/kyth-hub-web/src-tauri"
MAIN = (TAURI / "src/main.rs").read_text(encoding="utf-8")
LIVE_DATA = (ROOT / "src/kyth-hub-web/src/services/liveData.ts").read_text(encoding="utf-8")


class NativeHubContractTests(unittest.TestCase):
    def test_hub_has_one_tauri_binary_and_no_slint_sources(self):
        cargo = (TAURI / "Cargo.toml").read_text(encoding="utf-8")
        self.assertIn('name = "kyth-hub-shell"', cargo)
        self.assertNotIn("slint", cargo.lower())
        self.assertFalse((TAURI / "src/native_main.rs").exists())
        self.assertFalse((TAURI / "ui/hub.slint").exists())

    def test_every_frontend_invoke_is_registered(self):
        handler = re.search(r"generate_handler!\[([\s\S]*?)\]", MAIN)
        self.assertIsNotNone(handler)
        commands = set(re.findall(r'invoke(?:<[^>]+>)?\("([^"]+)"', LIVE_DATA))
        self.assertTrue(commands)
        for command in commands:
            self.assertRegex(handler.group(1), rf"\b{command}\b", command)

    def test_recipe_lifecycle_is_registered_and_structured(self):
        self.assertIn("commands::updates::just_run", MAIN)
        self.assertIn("commands::updates::just_run_status", MAIN)
        self.assertIn("struct InstallStatus", MAIN)
        for state in ("running", "complete", "failed", "unknown"):
            self.assertIn(f'"{state}"', MAIN)


if __name__ == "__main__":
    unittest.main()
