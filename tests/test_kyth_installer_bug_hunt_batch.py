from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer.context import InstallRequest, InstallerContext  # noqa: E402
from kyth_installer import imagesrc, validation  # noqa: E402
from kyth_installer.disk import _probe  # noqa: E402
from kyth_installer.disk import _util as disk_utils  # noqa: E402
from kyth_installer import system as installer_system  # noqa: E402
from kyth_installer.mount_registry import MountRegistry  # noqa: E402
from kyth_installer.partition_ops_journal import Journal  # noqa: E402
from kyth_installer import recovery  # noqa: E402


class InstallerBugHuntBatchTests(unittest.TestCase):
    def test_safe_int_rejects_non_finite_json_numbers(self):
        for value in (json.loads("1e999"), json.loads("-1e999"), float("nan")):
            self.assertEqual(disk_utils._safe_int(value, -1), -1)

    def test_password_rejects_nul_instead_of_hashing_a_truncated_value(self):
        with self.assertRaisesRegex(RuntimeError, "NUL"):
            installer_system._hash_password("pa\x00ss-tail")

    def test_immutable_request_preserves_guided_storage_fields(self):
        request = InstallRequest.from_state({
            "install_mode": "free_space",
            "resize_partition": "/dev/sda2",
            "resize_gib": 64,
            "free_region_start": 4096,
            "free_region_end": 8192,
        })
        self.assertEqual(request.resize_partition, "/dev/sda2")
        self.assertEqual(request.resize_gib, 64)
        self.assertEqual(request.free_region_start, 4096)
        self.assertEqual(request.free_region_end, 8192)

    def test_plan_probe_requires_a_successful_partition_scan(self):
        from kyth_installer import plan

        with mock.patch.object(plan, "list_disks", return_value=()), \
             mock.patch.object(plan, "list_partitions", return_value=[]) as parts, \
             mock.patch.object(plan, "find_efi_partition", return_value=None), \
             mock.patch.object(plan, "_is_gpt_disk", return_value=False):
            plan._probe_storage("/dev/sda")
        parts.assert_called_once_with("/dev/sda", strict=True)

    def test_journal_validation_requires_a_successful_partition_scan(self):
        journal = Journal("/dev/sda", disk_service=SimpleNamespace(dry_run=True))
        journal.add_op("new_table", {"table_type": "gpt"})
        with mock.patch("kyth_installer.partition_ops_journal.list_partitions", side_effect=RuntimeError("lsblk failed")) as parts:
            with self.assertRaisesRegex(RuntimeError, "lsblk failed"):
                journal.validate()
        parts.assert_called_once_with("/dev/sda", strict=True)

    def test_live_usb_probe_failure_does_not_reference_an_unset_source(self):
        with mock.patch.object(_probe._disk, "_findmnt_source", side_effect=OSError("findmnt unavailable")):
            self.assertIsNone(_probe._get_live_usb_disk())

    def test_live_usb_parent_is_added_to_protected_disk_set(self):
        with mock.patch.object(_probe._disk, "_lsblk_tree", return_value={}), \
             mock.patch.object(_probe._disk, "_running_system_disk", return_value=""), \
             mock.patch.object(_probe._disk, "_mount_sources", return_value=set()), \
             mock.patch.object(_probe._disk, "_get_live_usb_disk", return_value="/dev/sdb1"), \
             mock.patch.object(_probe._disk, "_parent_disk", return_value="/dev/sdb") as parent, \
             mock.patch.object(_probe, "_IS_LIVE_SESSION", True):
            protected = _probe._protected_install_disks()
        self.assertIn("/dev/sdb", protected)
        parent.assert_any_call("/dev/sdb1", tree={})

    def test_registry_preflight_uses_explicit_port(self):
        route = SimpleNamespace(returncode=0, stdout="default via 192.0.2.1")
        connection = mock.MagicMock()
        with mock.patch.object(imagesrc, "run_command", return_value=route), \
             mock.patch.object(imagesrc.socket, "getaddrinfo", return_value=[]) as resolve, \
             mock.patch.object(imagesrc.socket, "create_connection", return_value=connection) as connect:
            self.assertIsNone(imagesrc._network_preflight("docker://registry.example:5443/team/kyth:testing"))
        resolve.assert_called_once_with("registry.example", 5443, type=imagesrc.socket.SOCK_STREAM)
        connect.assert_called_once_with(("registry.example", 5443), timeout=5)

    def test_registry_parser_handles_bad_ports_and_network_dns_errors(self):
        self.assertEqual(imagesrc._registry_endpoint("docker://registry.example:bad/team/image"), ("", 443))
        route = SimpleNamespace(returncode=0, stdout="default via 192.0.2.1")
        with mock.patch.object(imagesrc, "run_command", return_value=route), \
             mock.patch.object(imagesrc.socket, "getaddrinfo", side_effect=OSError("resolver failed")):
            message = imagesrc._network_preflight("docker://registry.example/team/image")
        self.assertIn("DNS check", message)
        self.assertIn("resolver failed", message)

    def test_embedded_image_verifier_rejects_invalid_metadata_paths_and_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "image"
            root.mkdir()
            linked_root = Path(tmp) / "linked-image"
            linked_root.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "missing or unsafe"):
                imagesrc._verify_oci_source(f"oci:{linked_root}:latest")

            (root / "oci-layout").write_text(json.dumps({"imageLayoutVersion": "1.0.0"}))
            (root / "index.json").write_text(json.dumps({"manifests": []}))
            original_read_text = Path.read_text

            def fail_index_read(path, *args, **kwargs):
                if path.name == "index.json":
                    raise OSError("read failed")
                return original_read_text(path, *args, **kwargs)

            with mock.patch.object(Path, "read_text", fail_index_read):
                with self.assertRaisesRegex(RuntimeError, "could not read embedded OCI image"):
                    imagesrc._verify_oci_source(f"oci:{root}:latest")

            (root / "index.json").write_text("[]")
            with self.assertRaisesRegex(RuntimeError, "index must be a JSON object"):
                imagesrc._verify_oci_source(f"oci:{root}:latest")

            (root / "index.json").write_text(json.dumps({"manifests": [{"annotations": []}]}))
            with self.assertRaisesRegex(RuntimeError, "invalid annotations"):
                imagesrc._verify_oci_source(f"oci:{root}:latest")

            (root / "index.json").unlink()
            external_index = Path(tmp) / "external-index.json"
            external_index.write_text(json.dumps({"manifests": []}))
            (root / "index.json").symlink_to(external_index)
            with self.assertRaisesRegex(RuntimeError, "metadata is missing or unsafe"):
                imagesrc._verify_oci_source(f"oci:{root}:latest")

    def test_signature_bundle_path_override_is_honored(self):
        with mock.patch.dict("os.environ", {"KYTH_SOURCE_SIGNATURE": "/tmp/sig.json"}):
            self.assertEqual(imagesrc._signature_bundle_path(), Path("/tmp/sig.json"))

    def test_metadata_rejects_non_object_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "must be a JSON object"):
                imagesrc._read_source_metadata(path)

    def test_oci_index_rejects_malformed_manifest_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "image"
            root.mkdir()
            (root / "oci-layout").write_text(json.dumps({"imageLayoutVersion": "1.0.0"}))
            (root / "index.json").write_text(json.dumps({"manifests": {"bad": "shape"}}))
            with self.assertRaisesRegex(RuntimeError, "invalid manifest list"):
                imagesrc._verify_oci_source(
                    f"oci:{root}:latest", expected_digest="sha256:" + "a" * 64,
                )

    def test_cachyos_alias_is_normalized_and_unknown_kernel_rejected(self):
        with mock.patch.object(imagesrc, "TARGET_IMAGE", "registry/kyth:testing"):
            self.assertEqual(imagesrc._install_images("cachyos"), imagesrc._install_images("cachy"))
            with self.assertRaisesRegex(RuntimeError, "Unsupported kernel flavor"):
                imagesrc._install_images("unknown")

    def test_install_request_normalizes_cachyos_alias_and_rejects_unknown_kernel(self):
        base_state = {"disk": "/dev/sda", "install_mode": "wipe"}
        dependencies = (
            mock.patch.object(validation, "_storage_state", return_value=(base_state, {"current": False})),
            mock.patch.object(validation, "_hash_password_for_request", return_value="hashed"),
            mock.patch.object(validation.system, "list_timezones", return_value=["UTC"]),
            mock.patch.object(validation.system, "list_locales", return_value=["en_US.UTF-8"]),
            mock.patch.object(validation.system, "list_keymaps", return_value=["us"]),
        )
        with dependencies[0], dependencies[1], dependencies[2], dependencies[3], dependencies[4]:
            request = validation.validate_install_request({
                "confirm_backup": True, "confirm_erase": True, "kernel": "cachyos",
                "username": "user", "password": "pass", "hostname": "kyth",
            }, InstallerContext())
        self.assertEqual(request.kernel, "cachy")

        with dependencies[0], dependencies[1], dependencies[2], dependencies[3], dependencies[4]:
            with self.assertRaisesRegex(validation.InstallRequestError, "Invalid kernel flavor"):
                validation.validate_install_request({
                    "confirm_backup": True, "confirm_erase": True, "kernel": "unknown",
                    "username": "user", "password": "pass", "hostname": "kyth",
                }, InstallerContext())

    def test_mount_registry_keeps_mount_after_failed_unmount(self):
        registry = MountRegistry()
        registry.register("/mnt/target")
        with mock.patch("kyth_installer.system._safe_umount", return_value=SimpleNamespace(returncode=1)):
            registry.cleanup(run=mock.Mock())
        self.assertEqual(registry.snapshot(), ["/mnt/target"])

    def test_mount_registry_hold_keeps_mount_after_nonzero_unmount(self):
        registry = MountRegistry()
        log = mock.Mock()
        with mock.patch("kyth_installer.system._safe_umount", return_value=SimpleNamespace(returncode=1)):
            with registry.hold("/mnt/target", run=mock.Mock(), log=log):
                pass
        self.assertEqual(registry.snapshot(), ["/mnt/target"])
        self.assertIn("status 1", log.call_args.args[0])

    def test_recovery_cleanup_keeps_mount_after_failed_unmount(self):
        context = InstallerContext()
        context.register_mount("/mnt/target")
        with mock.patch("kyth_installer.system.unmount_filesystem", return_value=SimpleNamespace(returncode=1)):
            recovery.cleanup_registered_mounts(context, run=mock.Mock())
        self.assertEqual(context.cleanup_mounts, ["/mnt/target"])


if __name__ == "__main__":
    unittest.main()
