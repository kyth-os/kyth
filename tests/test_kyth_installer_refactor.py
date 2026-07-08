import importlib.machinery
import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_installer():
    loader = importlib.machinery.SourceFileLoader(
        "kyth_installer_refactor_test",
        str(ROOT / "build_files/kyth-installer"),
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class InstallerRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.installer = load_installer()

    def test_normalized_install_mode_defaults_to_wipe(self):
        self.assertEqual(self.installer._normalized_install_mode({}), "wipe")
        self.assertEqual(self.installer._normalized_install_mode({"install_mode": "  FREE_SPACE "}), "free_space")

    def test_apply_install_plan_updates_only_present_targets(self):
        state = {"install_mode": "wipe", "disk": "/dev/sda", "target_partition": "/dev/sda1"}
        plan = self.installer.InstallPlan("alongside", disk="/dev/nvme0n1")

        self.installer._apply_install_plan(state, plan)

        self.assertEqual(state["install_mode"], "alongside")
        self.assertEqual(state["disk"], "/dev/nvme0n1")
        self.assertEqual(state["target_partition"], "/dev/sda1")

    def test_cookie_parser_ignores_malformed_pairs(self):
        cookies = self.installer._parse_cookie_header("a=1; no-value; b = two ")

        self.assertEqual(cookies, {"a": "1", "b": "two"})

    def test_start_route_requires_same_origin(self):
        route = self.installer.ROUTES["start"]

        self.assertEqual(route.method, "POST")
        self.assertEqual(route.path, "/api/start")
        self.assertTrue(route.requires_same_origin)

    def test_route_lookup_matches_method_and_path(self):
        route = self.installer._route_for("GET", "/api/disks")

        self.assertIs(route, self.installer.ROUTES["disks"])
        self.assertIsNone(self.installer._route_for("POST", "/api/disks"))


if __name__ == "__main__":
    unittest.main()
