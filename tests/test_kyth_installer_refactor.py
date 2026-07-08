import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files/kyth-installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from kyth_installer import plan, server  # noqa: E402


class InstallerRefactorTests(unittest.TestCase):
    def test_normalized_install_mode_defaults_to_wipe(self):
        self.assertEqual(plan._normalized_install_mode({}), "wipe")
        self.assertEqual(plan._normalized_install_mode({"install_mode": "  FREE_SPACE "}), "free_space")

    def test_apply_install_plan_updates_only_present_targets(self):
        state = {"install_mode": "wipe", "disk": "/dev/sda", "target_partition": "/dev/sda1"}
        install_plan = plan.InstallPlan("alongside", disk="/dev/nvme0n1")

        plan._apply_install_plan(state, install_plan)

        self.assertEqual(state["install_mode"], "alongside")
        self.assertEqual(state["disk"], "/dev/nvme0n1")
        self.assertEqual(state["target_partition"], "/dev/sda1")

    def test_cookie_parser_ignores_malformed_pairs(self):
        cookies = server._parse_cookie_header("a=1; no-value; b = two ")

        self.assertEqual(cookies, {"a": "1", "b": "two"})

    def test_start_route_requires_same_origin(self):
        route = plan.ROUTES["start"]

        self.assertEqual(route.method, "POST")
        self.assertEqual(route.path, "/api/start")
        self.assertTrue(route.requires_same_origin)

    def test_route_lookup_matches_method_and_path(self):
        route = server._route_for("GET", "/api/disks")

        self.assertIs(route, plan.ROUTES["disks"])
        self.assertIsNone(server._route_for("POST", "/api/disks"))


if __name__ == "__main__":
    unittest.main()
