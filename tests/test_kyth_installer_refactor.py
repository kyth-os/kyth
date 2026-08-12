import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files/kyth-installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from kyth_installer import plan, server  # noqa: E402
from kyth_installer.storage_snapshot import StorageSnapshot  # noqa: E402


class InstallerRefactorTests(unittest.TestCase):
    def test_plan_validation_accepts_precomputed_storage_snapshot(self):
        disk = "/dev/nvme0n1"
        target = f"{disk}p2"
        snapshot = StorageSnapshot(
            disks=({"name": disk, "size_bytes": 128 * 1024**3},),
            partitions=({
                "name": target,
                "size_bytes": 64 * 1024**3,
                "efi": False,
                "current": False,
                "in_use": False,
            },),
            free_regions=(),
            efi_partition=f"{disk}p1",
            is_gpt=False,
        )

        with patch.object(plan, "_parent_disk", return_value=disk), \
             patch.object(plan, "list_disks", side_effect=AssertionError("live probe")), \
             patch.object(plan, "list_partitions", side_effect=AssertionError("live probe")):
            result = plan._validate_install_target(
                {"install_mode": "alongside", "disk": disk, "target_partition": target},
                snapshot=snapshot,
            )

        self.assertEqual(result, (disk, target))

    def test_snapshot_free_region_matching_is_pure(self):
        snapshot = StorageSnapshot(
            disks=(), partitions=(),
            free_regions=({"start_bytes": 1024, "end_bytes": 4096},),
            efi_partition=None, is_gpt=True,
        )

        self.assertTrue(snapshot.contains_free_region(1024, 4096))
        self.assertFalse(snapshot.contains_free_region(1024, 8192))

    def test_normalized_install_mode_defaults_to_wipe(self):
        self.assertEqual(plan._normalized_install_mode({}), "wipe")
        self.assertEqual(plan._normalized_install_mode({"install_mode": "  FREE_SPACE "}), "free_space")

    def test_request_with_install_plan_is_immutable_and_updates_only_present_targets(self):
        state = {"install_mode": "wipe", "disk": "/dev/sda", "target_partition": "/dev/sda1"}
        install_plan = plan.InstallPlan("alongside", disk="/dev/nvme0n1")

        request = plan.request_with_install_plan(state, install_plan)

        self.assertEqual(request.install_mode, "alongside")
        self.assertEqual(request.disk, "/dev/nvme0n1")
        self.assertEqual(request.target_partition, "/dev/sda1")
        self.assertEqual(state["install_mode"], "wipe")
        self.assertEqual(state["disk"], "/dev/sda")

    def test_prepare_plan_does_not_rewrite_request_state(self):
        state = {"install_mode": "wipe", "disk": "/dev/sda", "target_partition": ""}
        original = state.copy()

        with patch.object(plan, "_validate_install_target", return_value=("/dev/sda", None)):
            result = plan._prepare_install_plan(state, lambda _message: None)

        self.assertEqual(result, plan.InstallPlan("wipe", disk="/dev/sda", target_partition=None))
        self.assertEqual(state, original)

    def test_cookie_parser_ignores_malformed_pairs(self):
        cookies = server._parse_cookie_header("a=1; no-value; b = two ")

        self.assertEqual(cookies, {"a": "1", "b": "two"})

    def test_start_route_requires_same_origin(self):
        route = server.ROUTES["start"]

        self.assertEqual(route.method, "POST")
        self.assertEqual(route.path, "/api/start")
        self.assertTrue(route.requires_same_origin)

    def test_route_lookup_matches_method_and_path(self):
        route = server._route_for("GET", "/api/disks")

        self.assertIs(route, server.ROUTES["disks"])
        self.assertIsNone(server._route_for("POST", "/api/disks"))


if __name__ == "__main__":
    unittest.main()
