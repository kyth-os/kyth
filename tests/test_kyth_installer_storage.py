import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files/kyth-installer"
WEBUI_DIR = INSTALLER_ROOT / "kyth_installer/webui"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from kyth_installer import disk, install, plan, server  # noqa: E402


class InstallerWebuiTests(unittest.TestCase):
    def test_disk_continue_button_id_matches_updater(self):
        html = (WEBUI_DIR / "index.html").read_text()
        js = (WEBUI_DIR / "app.js").read_text()

        self.assertIn('id="disk-next"', html)
        self.assertIn("document.getElementById('disk-next').disabled", js)
        self.assertIn("const btn = document.getElementById('disk-next');", js)
        self.assertNotIn("getElementById('next-disk')", js)

    def test_review_page_treats_target_partition_as_plain_name_string(self):
        # S.target_partition is set from p.name (a string), never a partition
        # object — `.name`/`.fstype` accesses on it are always undefined and
        # silently blank the review page's "which partition gets erased" text.
        js = (WEBUI_DIR / "app.js").read_text()

        self.assertNotIn("S.target_partition.name", js)
        self.assertNotIn("S.target_partition.fstype", js)


class InstallerStorageTests(unittest.TestCase):
    def setUp(self):
        self.disk = disk

    def test_list_disks_excludes_protected_live_media(self):
        payload = {
            "blockdevices": [
                {"name": "/dev/nvme0n1", "size": 128 * 1024**3, "model": "Internal", "type": "disk", "tran": "nvme", "rota": False, "rm": False},
                {"name": "/dev/sdb", "size": 32 * 1024**3, "model": "Live USB", "type": "disk", "tran": "usb", "rota": False, "rm": True},
                {"name": "/dev/loop0", "size": 4 * 1024**3, "model": "Squashfs", "type": "disk", "tran": None, "rota": False, "rm": False},
            ]
        }

        with patch.object(self.disk, "_protected_install_disks", return_value={"/dev/sdb"}), \
             patch.object(self.disk.subprocess, "check_output", return_value=json.dumps(payload)):
            disks = self.disk.list_disks()

        self.assertEqual([d["name"] for d in disks], ["/dev/nvme0n1"])

    def test_list_disks_flags_running_system_disk_as_current(self):
        payload = {
            "blockdevices": [
                {"name": "/dev/nvme0n1", "size": 128 * 1024**3, "model": "Internal", "type": "disk", "tran": "nvme", "rota": False, "rm": False},
                {"name": "/dev/sdb", "size": 512 * 1024**3, "model": "Secondary", "type": "disk", "tran": "sata", "rota": False, "rm": False},
            ]
        }

        with patch.object(self.disk, "_protected_install_disks", return_value=set()), \
             patch.object(self.disk, "_running_system_disk", return_value="/dev/nvme0n1"), \
             patch.object(self.disk, "_parent_disk", return_value="/dev/nvme0n1"), \
             patch.object(self.disk.subprocess, "check_output", return_value=json.dumps(payload)):
            disks = {d["name"]: d for d in self.disk.list_disks()}

        self.assertTrue(disks["/dev/nvme0n1"]["current"])
        self.assertFalse(disks["/dev/sdb"]["current"])

    def test_parent_disk_walks_through_lvm_and_luks_layers(self):
        # Root on an LVM logical volume backed by a LUKS-encrypted partition:
        # LV -> crypt mapper -> partition -> disk is three PKNAME hops, not one.
        chain = {
            ("lsblk", "-n", "-o", "TYPE", "/dev/mapper/kyth-root"): "lvm\n",
            ("lsblk", "-n", "-o", "PKNAME", "/dev/mapper/kyth-root"): "dm-0\n",
            ("lsblk", "-n", "-o", "TYPE", "/dev/dm-0"): "crypt\n",
            ("lsblk", "-n", "-o", "PKNAME", "/dev/dm-0"): "nvme0n1p3\n",
            ("lsblk", "-n", "-o", "TYPE", "/dev/nvme0n1p3"): "part\n",
            ("lsblk", "-n", "-o", "PKNAME", "/dev/nvme0n1p3"): "nvme0n1\n",
            ("lsblk", "-n", "-o", "TYPE", "/dev/nvme0n1"): "disk\n",
        }

        def fake_check_output(cmd, **_kwargs):
            key = tuple(cmd)
            if key not in chain:
                raise AssertionError(f"unexpected lsblk invocation: {cmd}")
            return chain[key]

        normalize = lambda p: p if p.startswith("/dev/") else f"/dev/{p}"
        with patch.object(self.disk, "_normal_device_path", side_effect=normalize), \
             patch.object(self.disk.subprocess, "check_output", side_effect=fake_check_output):
            result = self.disk._parent_disk("/dev/mapper/kyth-root")

        self.assertEqual(result, "/dev/nvme0n1")

    def test_list_partitions_marks_only_unmounted_btrfs_as_alongside_candidate(self):
        payload = {
            "blockdevices": [{
                "name": "/dev/nvme0n1",
                "type": "disk",
                "children": [
                    {"name": "/dev/nvme0n1p1", "size": 1024**3, "type": "part", "fstype": "vfat", "parttype": self.disk.EFI_PART_GUID, "label": "EFI", "mountpoints": ["/boot/efi"]},
                    {"name": "/dev/nvme0n1p2", "size": 80 * 1024**3, "type": "part", "fstype": "btrfs", "parttype": "", "label": "shared", "mountpoints": []},
                    {"name": "/dev/nvme0n1p3", "size": 40 * 1024**3, "type": "part", "fstype": "ext4", "parttype": "", "label": "other", "mountpoints": []},
                    {"name": "/dev/nvme0n1p4", "size": 40 * 1024**3, "type": "part", "fstype": "btrfs", "parttype": "", "label": "active", "mountpoints": ["/home"]},
                ],
            }]
        }

        with patch.object(self.disk.subprocess, "check_output", return_value=json.dumps(payload)):
            parts = {p["name"]: p for p in self.disk.list_partitions("/dev/nvme0n1")}

        self.assertFalse(parts["/dev/nvme0n1p1"]["alongside_candidate"])
        self.assertTrue(parts["/dev/nvme0n1p2"]["alongside_candidate"])
        self.assertFalse(parts["/dev/nvme0n1p3"]["alongside_candidate"])
        self.assertFalse(parts["/dev/nvme0n1p4"]["alongside_candidate"])

    def test_find_efi_partition_reads_efi_key_without_keyerror(self):
        partitions = [
            {"name": "/dev/nvme0n1p1", "efi": False},
            {"name": "/dev/nvme0n1p2", "efi": True},
        ]
        with patch.object(self.disk, "list_partitions", return_value=partitions):
            result = self.disk.find_efi_partition("/dev/nvme0n1")

        self.assertEqual(result, "/dev/nvme0n1p2")

    def test_find_efi_partition_falls_back_to_findmnt_when_no_partition_flagged(self):
        with patch.object(self.disk, "list_partitions", return_value=[{"name": "/dev/nvme0n1p1", "efi": False}]), \
             patch.object(self.disk.subprocess, "check_output", return_value="/dev/nvme0n1p1\n"):
            result = self.disk.find_efi_partition("/dev/nvme0n1")

        self.assertEqual(result, "/dev/nvme0n1p1")

    def test_list_free_space_finds_trailing_gap_after_partitions(self):
        reserve = 1024**2
        p1_start = reserve
        p1_size = 1 * 1024**3 - reserve
        p2_start = p1_start + p1_size  # contiguous with p1, no gap between them
        p2_size = 39 * 1024**3
        disk_size = 120 * 1024**3

        partitions = [
            {"name": "/dev/nvme0n1p1", "size_bytes": p1_size},
            {"name": "/dev/nvme0n1p2", "size_bytes": p2_size},
        ]
        starts = {"/dev/nvme0n1p1": p1_start, "/dev/nvme0n1p2": p2_start}

        with patch.object(self.disk, "list_partitions", return_value=partitions), \
             patch.object(self.disk, "_partition_size_bytes", return_value=disk_size), \
             patch.object(self.disk, "_block_size_bytes", return_value=512), \
             patch.object(self.disk, "_partition_start_bytes", side_effect=lambda name: starts[name]):
            regions = self.disk.list_free_space("/dev/nvme0n1")

        self.assertEqual(len(regions), 1)
        region = regions[0]
        self.assertEqual(region["start_bytes"], p2_start + p2_size)
        self.assertEqual(region["end_bytes"], disk_size - reserve)
        self.assertGreater(region["end_bytes"] - region["start_bytes"], self.disk.MIN_KYTHOS_BYTES)

    def test_list_free_space_omits_gaps_smaller_than_minimum(self):
        partitions = [{"name": "/dev/nvme0n1p1", "size_bytes": 300 * 1024**2}]
        with patch.object(self.disk, "list_partitions", return_value=partitions), \
             patch.object(self.disk, "_partition_size_bytes", return_value=310 * 1024**2), \
             patch.object(self.disk, "_block_size_bytes", return_value=512), \
             patch.object(self.disk, "_partition_start_bytes", return_value=1024**2):
            regions = self.disk.list_free_space("/dev/nvme0n1")

        self.assertEqual(regions, [])

    def test_latest_partition_on_disk_natural_sort(self):
        before = {"/dev/sda1", "/dev/sda2"}
        partitions = [
            {"name": "/dev/sda1"},
            {"name": "/dev/sda2"},
            {"name": "/dev/sda10"},
        ]
        with patch.object(self.disk, "list_partitions", return_value=partitions):
            result = self.disk._latest_partition_on_disk("/dev/sda", before)
        self.assertEqual(result, "/dev/sda10")

    def test_find_efi_partition_scans_other_disks_as_fallback(self):
        def fake_list_partitions(d):
            if d == "/dev/nvme0n1":
                return [{"name": "/dev/nvme0n1p1", "efi": True}]
            return [{"name": "/dev/nvme1n1p1", "efi": False}]

        with patch.object(self.disk, "list_partitions", side_effect=fake_list_partitions), \
             patch.object(self.disk, "list_disks", return_value=[{"name": "/dev/nvme0n1"}, {"name": "/dev/nvme1n1"}]):
            result = self.disk.find_efi_partition("/dev/nvme1n1")
            self.assertEqual(result, "/dev/nvme0n1p1")


class InstallerPlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = plan

    def test_validate_alongside_requires_partition_on_selected_disk(self):
        with patch.object(self.plan, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.plan, "list_partitions", return_value=[]), \
             patch.object(self.plan, "_parent_disk", return_value="/dev/sda"):
            with self.assertRaisesRegex(RuntimeError, "does not belong"):
                self.plan._validate_install_target({
                    "install_mode": "alongside",
                    "disk": "/dev/nvme0n1",
                    "target_partition": "/dev/sda2",
                })

    def test_validate_alongside_requires_btrfs_partition(self):
        partition = {
            "name": "/dev/nvme0n1p2",
            "fstype": "ext4",
            "efi": False,
            "current": False,
        }
        with patch.object(self.plan, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.plan, "list_partitions", return_value=[partition]), \
             patch.object(self.plan, "_parent_disk", return_value="/dev/nvme0n1"):
            with self.assertRaisesRegex(RuntimeError, "Btrfs"):
                self.plan._validate_install_target({
                    "install_mode": "alongside",
                    "disk": "/dev/nvme0n1",
                    "target_partition": "/dev/nvme0n1p2",
                })

    def test_validate_wipe_rejects_disk_missing_from_safe_scan(self):
        with patch.object(self.plan, "list_disks", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "not a safe install target"):
                self.plan._validate_install_target({"install_mode": "wipe", "disk": "/dev/sda"})

    def test_validate_wipe_rejects_disk_below_minimum_size(self):
        with patch.object(self.plan, "list_disks", return_value=[
            {"name": "/dev/sda", "size_bytes": 16 * 1024**3},
        ]):
            with self.assertRaisesRegex(RuntimeError, "too small"):
                self.plan._validate_install_target({"install_mode": "wipe", "disk": "/dev/sda"})

    def test_validate_wipe_accepts_disk_at_minimum_size(self):
        with patch.object(self.plan, "list_disks", return_value=[
            {"name": "/dev/sda", "size_bytes": 32 * 1024**3},
        ]):
            disk_name, target = self.plan._validate_install_target({"install_mode": "wipe", "disk": "/dev/sda"})

        self.assertEqual((disk_name, target), ("/dev/sda", None))

    def test_validate_resize_ntfs_requires_last_partition(self):
        partition = {
            "name": "/dev/nvme0n1p3",
            "fstype": "ntfs",
            "efi": False,
            "current": False,
            "size_bytes": 256 * 1024**3,
        }
        with patch.object(self.plan, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.plan, "list_partitions", return_value=[partition]), \
             patch.object(self.plan, "_parent_disk", return_value="/dev/nvme0n1"), \
             patch.object(self.plan, "_partitions_after", return_value=[{"name": "/dev/nvme0n1p4"}]):
            with self.assertRaisesRegex(RuntimeError, "not the last partition"):
                self.plan._validate_resize_ntfs_target({
                    "disk": "/dev/nvme0n1",
                    "resize_partition": "/dev/nvme0n1p3",
                    "resize_gib": 64,
                })

    def test_validate_resize_ntfs_accepts_clean_last_ntfs_partition(self):
        partition = {
            "name": "/dev/nvme0n1p3",
            "fstype": "ntfs",
            "efi": False,
            "current": False,
            "size_bytes": 256 * 1024**3,
        }
        with patch.object(self.plan, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.plan, "list_partitions", return_value=[partition]), \
             patch.object(self.plan, "_parent_disk", return_value="/dev/nvme0n1"), \
             patch.object(self.plan, "_partitions_after", return_value=[]), \
             patch.object(self.plan, "find_efi_partition", return_value="/dev/nvme0n1p1"):
            disk_name, target, shrink = self.plan._validate_resize_ntfs_target({
                "disk": "/dev/nvme0n1",
                "resize_partition": "/dev/nvme0n1p3",
                "resize_gib": 64,
            })

        self.assertEqual(disk_name, "/dev/nvme0n1")
        self.assertEqual(target, "/dev/nvme0n1p3")
        self.assertEqual(shrink, 64 * 1024**3)

    def test_prepare_ntfs_resize_creates_btrfs_target_after_dry_run(self):
        partition = "/dev/nvme0n1p3"
        commands = []

        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            return self.plan.subprocess.CompletedProcess(cmd, 0, stdout="ok")

        # _latest_partition_on_disk (defined in disk.py) calls disk's own
        # list_partitions, not plan's imported reference, so both names must
        # be patched to the same mock to share the before/after side_effect.
        list_partitions_mock = MagicMock(side_effect=[
            [{"name": "/dev/nvme0n1p1"}, {"name": partition}],
            [{"name": "/dev/nvme0n1p1"}, {"name": partition}, {"name": "/dev/nvme0n1p4"}],
        ])

        with patch.object(self.plan.shutil, "which", return_value="/usr/bin/tool"), \
             patch.object(self.plan, "unmount_target_disk") as mock_unmount, \
             patch.object(self.plan, "_validate_resize_ntfs_target", return_value=("/dev/nvme0n1", partition, 64 * 1024**3)), \
             patch.object(self.plan, "_partition_size_bytes", return_value=256 * 1024**3), \
             patch.object(self.plan, "_partition_number", return_value=3), \
             patch.object(self.plan, "_partition_start_bytes", return_value=128 * 1024**3), \
             patch.object(self.plan, "_block_size_bytes", return_value=512), \
             patch.object(self.plan, "list_partitions", list_partitions_mock), \
             patch.object(disk, "list_partitions", list_partitions_mock), \
             patch.object(self.plan, "_settle_block_devices"), \
             patch.object(self.plan.subprocess, "run", side_effect=fake_run):
            created = self.plan._prepare_ntfs_resize_target(
                {"disk": "/dev/nvme0n1", "resize_partition": partition, "resize_gib": 64},
                lambda _msg: None,
            )

        mock_unmount.assert_called_once_with("/dev/nvme0n1", unittest.mock.ANY)
        self.assertEqual(created, ("/dev/nvme0n1", "/dev/nvme0n1p4"))
        flattened = [" ".join(cmd) for cmd in commands]
        self.assertTrue(any("ntfsresize --no-action" in cmd for cmd in flattened))
        self.assertTrue(any("parted -s /dev/nvme0n1 unit B resizepart 3" in cmd for cmd in flattened))
        self.assertTrue(any("mkfs.btrfs -f -L KythOS /dev/nvme0n1p4" in cmd for cmd in flattened))

    def test_validate_free_space_rejects_region_below_minimum_size(self):
        with patch.object(self.plan, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.plan, "find_efi_partition", return_value="/dev/nvme0n1p1"):
            with self.assertRaisesRegex(RuntimeError, "at least"):
                self.plan._validate_free_space_target({
                    "disk": "/dev/nvme0n1",
                    "free_region_start": 1024**2,
                    "free_region_end": 16 * 1024**3,
                })

    def test_validate_free_space_rejects_stale_region_no_longer_free(self):
        with patch.object(self.plan, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.plan, "find_efi_partition", return_value="/dev/nvme0n1p1"), \
             patch.object(self.plan, "list_free_space", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "no longer available"):
                self.plan._validate_free_space_target({
                    "disk": "/dev/nvme0n1",
                    "free_region_start": 40 * 1024**3,
                    "free_region_end": 80 * 1024**3,
                })

    def test_validate_free_space_requires_efi_partition(self):
        with patch.object(self.plan, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.plan, "find_efi_partition", return_value=""):
            with self.assertRaisesRegex(RuntimeError, "EFI system partition"):
                self.plan._validate_free_space_target({
                    "disk": "/dev/nvme0n1",
                    "free_region_start": 40 * 1024**3,
                    "free_region_end": 80 * 1024**3,
                })

    def test_validate_free_space_accepts_region_covered_by_current_scan(self):
        with patch.object(self.plan, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.plan, "find_efi_partition", return_value="/dev/nvme0n1p1"), \
             patch.object(self.plan, "list_free_space", return_value=[
                 {"start_bytes": 40 * 1024**3, "end_bytes": 100 * 1024**3},
             ]):
            disk_name, start, end = self.plan._validate_free_space_target({
                "disk": "/dev/nvme0n1",
                "free_region_start": 40 * 1024**3,
                "free_region_end": 80 * 1024**3,
            })

        self.assertEqual((disk_name, start, end), ("/dev/nvme0n1", 40 * 1024**3, 80 * 1024**3))

    def test_prepare_free_space_target_creates_btrfs_partition(self):
        commands = []

        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            return self.plan.subprocess.CompletedProcess(cmd, 0, stdout="ok")

        with patch.object(self.plan.shutil, "which", return_value="/usr/bin/tool"), \
             patch.object(self.plan, "unmount_target_disk") as mock_unmount, \
             patch.object(self.plan, "_validate_free_space_target", return_value=("/dev/nvme0n1", 40 * 1024**3, 80 * 1024**3)), \
             patch.object(self.plan, "list_partitions", return_value=[{"name": "/dev/nvme0n1p1"}]), \
             patch.object(self.plan, "_latest_partition_on_disk", return_value="/dev/nvme0n1p2"), \
             patch.object(self.plan, "_settle_block_devices"), \
             patch.object(self.plan.subprocess, "run", side_effect=fake_run):
            created = self.plan._prepare_free_space_target(
                {"disk": "/dev/nvme0n1", "free_region_start": 40 * 1024**3, "free_region_end": 80 * 1024**3},
                lambda _msg: None,
            )

        mock_unmount.assert_called_once_with("/dev/nvme0n1", unittest.mock.ANY)
        self.assertEqual(created, ("/dev/nvme0n1", "/dev/nvme0n1p2"))
        flattened = [" ".join(cmd) for cmd in commands]
        self.assertTrue(any(
            f"parted -s /dev/nvme0n1 unit B mkpart KythOS btrfs {40 * 1024**3}B {80 * 1024**3}B" in cmd
            for cmd in flattened
        ))
        self.assertTrue(any("mkfs.btrfs -f -L KythOS /dev/nvme0n1p2" in cmd for cmd in flattened))

    def test_prepare_free_space_target_requires_partitioning_tools(self):
        with patch.object(self.plan.shutil, "which", return_value=None), \
             patch.object(self.plan, "unmount_target_disk"), \
             patch.object(self.plan, "_validate_free_space_target", return_value=("/dev/nvme0n1", 40 * 1024**3, 80 * 1024**3)):
            with self.assertRaisesRegex(RuntimeError, "Required partitioning tools"):
                self.plan._prepare_free_space_target(
                    {"disk": "/dev/nvme0n1", "free_region_start": 40 * 1024**3, "free_region_end": 80 * 1024**3},
                    lambda _msg: None,
                )


class InstallerServerConfirmationTests(unittest.TestCase):
    """/api/start must re-check the review-page acknowledgement checkboxes
    server-side, not just trust the frontend to keep "Install Now" disabled."""

    def _make_handler(self, body: dict) -> server.Handler:
        handler = server.Handler.__new__(server.Handler)
        payload = json.dumps(body).encode()
        handler.headers = {"Content-Length": str(len(payload))}
        handler.rfile = io.BytesIO(payload)
        handler.wfile = io.BytesIO()
        handler.path = "/api/start"
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.send_error = MagicMock()
        return handler

    @patch.object(server.Handler, "_require_same_origin_context", return_value=True)
    @patch.object(server.Handler, "_require_auth", return_value=True)
    def test_start_rejects_missing_confirmation_checkboxes(self, *_mocks):
        disks = [{"name": "/dev/sda", "current": False, "size_bytes": 64 * 1024**3}]
        handler = self._make_handler({
            "disk": "/dev/sda",
            "install_mode": "wipe",
            "confirm_backup": True,
            "confirm_erase": False,
        })
        with patch.object(server, "list_disks", return_value=disks), \
             patch.object(install, "_run_install") as run_install:
            handler.do_POST()

        handler.send_error.assert_not_called()
        written = handler.wfile.getvalue().decode().lower()
        self.assertIn('"started": false', written)
        run_install.assert_not_called()

    @patch.object(server.Handler, "_require_same_origin_context", return_value=True)
    @patch.object(server.Handler, "_require_auth", return_value=True)
    def test_start_accepts_when_confirmations_present(self, *_mocks):
        disks = [{"name": "/dev/sda", "current": False, "size_bytes": 64 * 1024**3}]
        handler = self._make_handler({
            "disk": "/dev/sda",
            "install_mode": "wipe",
            "username": "user",
            "password": "x",
            "confirm_backup": True,
            "confirm_erase": True,
        })
        with patch.object(server, "list_disks", return_value=disks), \
             patch.object(server, "list_timezones", return_value=["UTC"]), \
             patch.object(install, "_run_install"):
            handler.do_POST()

        handler.send_error.assert_not_called()
        written = handler.wfile.getvalue().decode().lower()
        self.assertIn('"started": true', written)


if __name__ == "__main__":
    unittest.main()
