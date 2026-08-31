"""Static contract checks for the production Rust/Slint Hub surface."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "src/kyth-hub-web/src-tauri/src/native_main.rs"
SLINT = ROOT / "src/kyth-hub-web/src-tauri/ui/hub.slint"


class NativeHubContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = NATIVE.read_text(encoding="utf-8")
        cls.slint = SLINT.read_text(encoding="utf-8")

    def test_every_slint_callback_has_a_rust_handler(self):
        callbacks = re.findall(r"callback\s+([a-z-]+)\s*\(", self.slint)
        for callback in callbacks:
            rust_name = "on_" + callback.replace("-", "_")
            self.assertRegex(self.native, rf"\.{rust_name}\s*\(", callback)

    def test_every_page_action_is_in_the_native_source(self):
        actions = sorted(set(re.findall(r'page-action\("([a-z0-9_-]+)"\)', self.slint)))
        for action in actions:
            self.assertIn(f'"{action}"', self.native, action)

    def test_system_changing_actions_have_a_confirmation_boundary(self):
        for action in (
            "upgrade",
            "rollback",
            "apply-staged",
            "firmware-update",
            "install-ludusavi",
            "setup-tailscale",
            "switch-channel-stable",
            "switch-kernel-cachy",
        ):
            self.assertIn(f'"{action}"', self.native)
        self.assertIn("confirmation_granted", self.native)
        self.assertIn("fixed_assignments", self.native)

    def test_recipe_runner_publishes_structured_lifecycle_state(self):
        for field in ("action-state", "action-id", "action-job-id"):
            self.assertIn(field, self.slint)
        for state in ("running", "complete", "failed"):
            self.assertIn(f'"{state}"', self.native)
        self.assertIn("NativeActionResult", self.native)


if __name__ == "__main__":
    unittest.main()
