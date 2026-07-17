import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_ROOT = ROOT / "build_files/kyth-installer"
WEBUI_DIR = INSTALLER_ROOT / "kyth_installer/webui"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from kyth_installer import disk, install, plan, server, system  # noqa: E402


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

    def test_back_from_error_routes_to_config_not_configure(self):
        js = (WEBUI_DIR / "app.js").read_text()
        self.assertIn("goto(S.password ? 'review' : 'config')", js)
        self.assertNotIn("goto(S.password ? 'review' : 'configure')", js)

    def test_backend_route_table_keeps_frontend_api_paths(self):
        expected = {
            ("GET", "/api/disks"),
            ("GET", "/api/free-space"),
            ("GET", "/api/partitions"),
            ("GET", "/api/timezones"),
            ("GET", "/api/log"),
            ("POST", "/api/start"),
        }
        actual = {(route.method, route.path) for route in plan.ROUTES.values()}

        self.assertTrue(expected.issubset(actual))

    def test_webui_and_backend_share_install_mode_names(self):
        js = (WEBUI_DIR / "app.js").read_text()

        for field in (
            "install_mode",
            "target_partition",
            "resize_partition",
            "free_region_start",
            "free_region_end",
        ):
            self.assertIn(field, js)

        for mode in ("wipe", "alongside", "free-space", "resize-ntfs"):
            self.assertEqual(plan._install_plan_from_state({"install_mode": mode}).mode, mode)


class InstallerCommandTests(unittest.TestCase):
    def test_streaming_command_handles_carriage_return_progress(self):
        logs = []
        progress = []
        command = [
            sys.executable,
            "-c",
            (
                "import sys,time; "
                "sys.stdout.write('Downloading layer 1\\r'); sys.stdout.flush(); "
                "time.sleep(0.05); print('Writing image')"
            ),
        ]

        with patch.object(install, "_as_root", side_effect=lambda cmd: cmd), \
             patch.object(install, "_get_rx_bytes", return_value=0):
            install._run_cmd(
                command, 5, 90, logs.append, progress.append,
                stall_timeout=2, absolute_timeout=None,
            )

        self.assertIn("Downloading layer 1", logs)
        self.assertIn("Writing image", logs)
        self.assertEqual(progress[-1], 90)

    def test_bootc_install_calls_disable_absolute_timeout(self):
        source = (INSTALLER_ROOT / "kyth_installer/install.py").read_text()

        self.assertEqual(source.count("stall_timeout=3600, absolute_timeout=None"), 2)
        self.assertNotIn("absolute_timeout=14400", source)


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

    def test_list_disks_excludes_read_only_devices(self):
        payload = {"blockdevices": [
            {"name": "/dev/sda", "size": 64 * 1024**3, "model": "Read only", "type": "disk", "ro": True},
            {"name": "/dev/sdb", "size": 64 * 1024**3, "model": "Writable", "type": "disk", "ro": False},
        ]}
        with patch.object(self.disk, "_protected_install_disks", return_value=set()), \
             patch.object(self.disk, "_running_system_disk", return_value=""), \
             patch.object(self.disk.subprocess, "check_output", return_value=json.dumps(payload)):
            disks = self.disk.list_disks()

        self.assertEqual([item["name"] for item in disks], ["/dev/sdb"])

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

    def test_list_partitions_marks_replaceable_unmounted_partitions(self):
        payload = {
            "blockdevices": [{
                "name": "/dev/nvme0n1",
                "type": "disk",
                "children": [
                    {"name": "/dev/nvme0n1p1", "size": 1024**3, "type": "part", "fstype": "vfat", "parttype": self.disk.EFI_PART_GUID, "label": "EFI", "mountpoints": ["/boot/efi"]},
                    {"name": "/dev/nvme0n1p2", "size": 80 * 1024**3, "type": "part", "fstype": "btrfs", "parttype": "", "label": "shared", "mountpoints": []},
                    {"name": "/dev/nvme0n1p3", "size": 40 * 1024**3, "type": "part", "fstype": "ext4", "parttype": "", "label": "other", "mountpoints": []},
                    {"name": "/dev/nvme0n1p4", "size": 40 * 1024**3, "type": "part", "fstype": "btrfs", "parttype": "", "label": "active", "mountpoints": ["/home"]},
                    {"name": "/dev/nvme0n1p5", "size": 80 * 1024**3, "type": "part", "fstype": "crypto_LUKS", "parttype": "", "label": "vault", "mountpoints": [], "children": [
                        {"name": "/dev/mapper/vault", "size": 80 * 1024**3, "type": "crypt", "fstype": "ext4", "mountpoints": []},
                    ]},
                ],
            }]
        }

        with patch.object(self.disk.subprocess, "check_output", return_value=json.dumps(payload)):
            parts = {p["name"]: p for p in self.disk.list_partitions("/dev/nvme0n1")}

        self.assertFalse(parts["/dev/nvme0n1p1"]["alongside_candidate"])
        self.assertTrue(parts["/dev/nvme0n1p2"]["alongside_candidate"])
        self.assertTrue(parts["/dev/nvme0n1p3"]["alongside_candidate"])
        self.assertFalse(parts["/dev/nvme0n1p4"]["alongside_candidate"])
        self.assertFalse(parts["/dev/nvme0n1p5"]["alongside_candidate"])
        self.assertTrue(parts["/dev/nvme0n1p5"]["in_use"])

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

    def test_list_free_space_fails_closed_when_partition_scan_fails(self):
        with patch.object(self.disk, "list_partitions", side_effect=RuntimeError("scan failed")), \
             patch.object(self.disk, "_partition_size_bytes", return_value=120 * 1024**3), \
             patch.object(self.disk, "_block_size_bytes", return_value=512):
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

    def test_validate_alongside_allows_any_filesystem_partition(self):
        partition = {
            "name": "/dev/nvme0n1p2",
            "fstype": "ext4",
            "efi": False,
            "current": False,
            "size_bytes": 128 * 1024**3,
        }
        with patch.object(self.plan, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.plan, "list_partitions", return_value=[partition]), \
             patch.object(self.plan, "_parent_disk", return_value="/dev/nvme0n1"), \
             patch.object(self.plan, "_is_gpt_disk", return_value=False), \
             patch.object(self.plan, "find_efi_partition", return_value="/dev/nvme0n1p1"):
            disk_name, target = self.plan._validate_install_target({
                "install_mode": "alongside",
                "disk": "/dev/nvme0n1",
                "target_partition": "/dev/nvme0n1p2",
            })
            self.assertEqual((disk_name, target), ("/dev/nvme0n1", "/dev/nvme0n1p2"))

    def test_validate_alongside_rejects_gpt_without_bios_boot_partition(self):
        partition = {
            "name": "/dev/nvme0n1p2",
            "fstype": "ext4",
            "efi": False,
            "current": False,
            "size_bytes": 128 * 1024**3,
        }
        with patch.object(self.plan, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.plan, "list_partitions", return_value=[partition]), \
             patch.object(self.plan, "_parent_disk", return_value="/dev/nvme0n1"), \
             patch.object(self.plan, "_is_gpt_disk", return_value=True), \
             patch.object(self.plan, "_has_bios_boot_partition", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "no BIOS boot partition"):
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

    def test_validate_resize_ntfs_allows_trailing_recovery_partition(self):
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
             patch.object(self.plan, "_is_gpt_disk", return_value=False), \
             patch.object(self.plan, "find_efi_partition", return_value="/dev/nvme0n1p1"):
            result = self.plan._validate_resize_ntfs_target({
                "disk": "/dev/nvme0n1",
                "resize_partition": "/dev/nvme0n1p3",
                "resize_gib": 64,
            })

        self.assertEqual(result, ("/dev/nvme0n1", "/dev/nvme0n1p3", 64 * 1024**3))

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
             patch.object(self.plan, "_is_gpt_disk", return_value=False), \
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
        run_kwargs = []

        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            run_kwargs.append(kwargs)
            return self.plan.subprocess.CompletedProcess(cmd, 0, stdout="ok")

        # _latest_partition_on_disk (defined in disk.py) calls disk's own
        # list_partitions, not plan's imported reference, so both names must
        # be patched to the same mock to share the before/after side_effect.
        # p1 already carries the bios_grub GUID so _ensure_bios_boot_partition
        # (call 1) skips creation; calls 2 and 3 are the before/after
        # snapshots around the KythOS mkpart.
        existing = [
            {"name": "/dev/nvme0n1p1", "parttype": self.plan.BIOS_BOOT_GUID},
            {"name": partition},
        ]
        list_partitions_mock = MagicMock(side_effect=[
            existing,
            existing,
            existing + [{"name": "/dev/nvme0n1p4"}],
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
             patch.object(self.plan, "_is_gpt_disk", return_value=True), \
             patch.object(self.plan, "run_command", side_effect=fake_run):
            created = self.plan._prepare_ntfs_resize_target(
                {"disk": "/dev/nvme0n1", "resize_partition": partition, "resize_gib": 64},
                lambda _msg: None,
            )

        mock_unmount.assert_called_once_with("/dev/nvme0n1", unittest.mock.ANY)
        self.assertEqual(created, ("/dev/nvme0n1", "/dev/nvme0n1p4"))
        flattened = [" ".join(cmd) for cmd in commands]
        self.assertTrue(any("ntfsresize --no-action" in cmd for cmd in flattened))
        # parted >= 3.3 exits 1 on a script-mode (-s) shrink because it cannot
        # ask its "can cause data loss" question; the shrink must run with
        # ---pretend-input-tty and "Yes" on stdin instead.
        shrink_calls = [
            (cmd, kwargs)
            for cmd, kwargs in zip(flattened, run_kwargs)
            if "resizepart 3" in cmd
        ]
        self.assertEqual(len(shrink_calls), 1)
        shrink_cmd, shrink_kwargs = shrink_calls[0]
        self.assertIn("parted ---pretend-input-tty /dev/nvme0n1 unit B resizepart 3", shrink_cmd)
        self.assertNotIn(" -s ", shrink_cmd)
        self.assertEqual(shrink_kwargs.get("input"), "Yes\n")
        ntfs_shrink = next(
            kwargs for cmd, kwargs in zip(flattened, run_kwargs)
            if "ntfsresize --size" in cmd and "--no-action" not in cmd
        )
        self.assertEqual(ntfs_shrink.get("input"), "y\n")
        self.assertTrue(any("mkpart KythOS btrfs" in cmd and "100%" not in cmd for cmd in flattened))
        self.assertTrue(any("mkfs.btrfs -f -L KythOS /dev/nvme0n1p4" in cmd for cmd in flattened))

    def test_ensure_bios_boot_partition_creates_and_flags_when_missing(self):
        # The OS image ships a bootupd BIOS component and bootc installs every
        # shipped component; without a bios_grub partition grub2-install falls
        # back to blocklists, which Btrfs rejects, failing the install.
        commands = []

        def fake_run(cmd, **kwargs):
            commands.append(" ".join(cmd))
            return self.plan.subprocess.CompletedProcess(cmd, 0, stdout="ok")

        gap_start = 128 * 1024**3
        with patch.object(self.plan, "list_partitions", return_value=[{"name": "/dev/sda1", "parttype": ""}]), \
             patch.object(self.plan, "_latest_partition_on_disk", return_value="/dev/sda2"), \
             patch.object(self.plan, "_partition_number", return_value=2), \
             patch.object(self.plan, "_block_size_bytes", return_value=512), \
             patch.object(self.plan, "_settle_block_devices"), \
             patch.object(self.plan, "_is_gpt_disk", return_value=True), \
             patch.object(self.plan, "run_command", side_effect=fake_run):
            btrfs_start = self.plan._ensure_bios_boot_partition("/dev/sda", gap_start, lambda _msg: None)

        self.assertEqual(btrfs_start, gap_start + self.plan.BIOS_BOOT_BYTES)
        bios_end = gap_start + self.plan.BIOS_BOOT_BYTES - 512
        self.assertTrue(any(f"mkpart biosboot {gap_start}B {bios_end}B" in cmd for cmd in commands))
        self.assertTrue(any("set 2 bios_grub on" in cmd for cmd in commands))

    def test_ensure_bios_boot_partition_skips_when_already_present(self):
        with patch.object(self.plan, "_is_gpt_disk", return_value=True), \
             patch.object(self.plan, "list_partitions", return_value=[
                 {"name": "/dev/sda1", "parttype": self.plan.BIOS_BOOT_GUID},
             ]), patch.object(self.plan, "run_command") as mock_run:
            btrfs_start = self.plan._ensure_bios_boot_partition("/dev/sda", 4096, lambda _msg: None)

        self.assertEqual(btrfs_start, 4096)
        mock_run.assert_not_called()

    def test_validate_free_space_rejects_region_below_minimum_size(self):
        with patch.object(self.plan, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.plan, "find_efi_partition", return_value="/dev/nvme0n1p1"):
            with self.assertRaisesRegex(RuntimeError, "at least"):
                self.plan._validate_free_space_target({
                    "disk": "/dev/nvme0n1",
                    "free_region_start": 1024**2,
                    "free_region_end": 16 * 1024**3,
                })

    def test_validate_free_space_reserves_room_for_new_bios_partition(self):
        start = 40 * 1024**3
        end = start + 32 * 1024**3
        with patch.object(self.plan, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.plan, "_is_gpt_disk", return_value=True), \
             patch.object(self.plan, "_has_bios_boot_partition", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "33 GiB"):
                self.plan._validate_free_space_target({
                    "disk": "/dev/nvme0n1",
                    "free_region_start": start,
                    "free_region_end": end,
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

    def test_validate_free_space_accepts_exact_region_from_current_scan(self):
        with patch.object(self.plan, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.plan, "find_efi_partition", return_value="/dev/nvme0n1p1"), \
             patch.object(self.plan, "list_free_space", return_value=[
                 {"start_bytes": 40 * 1024**3, "end_bytes": 80 * 1024**3},
             ]):
            disk_name, start, end = self.plan._validate_free_space_target({
                "disk": "/dev/nvme0n1",
                "free_region_start": 40 * 1024**3,
                "free_region_end": 80 * 1024**3,
            })

        self.assertEqual((disk_name, start, end), ("/dev/nvme0n1", 40 * 1024**3, 80 * 1024**3))

    def test_validate_free_space_rejects_ui_supplied_subregion(self):
        with patch.object(self.plan, "list_disks", return_value=[{"name": "/dev/nvme0n1"}]), \
             patch.object(self.plan, "find_efi_partition", return_value="/dev/nvme0n1p1"), \
             patch.object(self.plan, "list_free_space", return_value=[
                 {"start_bytes": 40 * 1024**3, "end_bytes": 100 * 1024**3},
             ]):
            with self.assertRaisesRegex(RuntimeError, "no longer available"):
                self.plan._validate_free_space_target({
                    "disk": "/dev/nvme0n1",
                    "free_region_start": 40 * 1024**3,
                    "free_region_end": 80 * 1024**3,
                })

    def test_prepare_free_space_target_creates_btrfs_partition(self):
        commands = []

        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            return self.plan.subprocess.CompletedProcess(cmd, 0, stdout="ok")

        with patch.object(self.plan.shutil, "which", return_value="/usr/bin/tool"), \
             patch.object(self.plan, "unmount_target_disk") as mock_unmount, \
             patch.object(self.plan, "_validate_free_space_target", return_value=("/dev/nvme0n1", 40 * 1024**3, 80 * 1024**3)), \
             patch.object(self.plan, "list_partitions", return_value=[
                 {"name": "/dev/nvme0n1p1", "parttype": self.plan.BIOS_BOOT_GUID},
             ]), \
             patch.object(self.plan, "_latest_partition_on_disk", return_value="/dev/nvme0n1p2"), \
             patch.object(self.plan, "_block_size_bytes", return_value=512), \
             patch.object(self.plan, "_settle_block_devices"), \
             patch.object(self.plan, "_is_gpt_disk", return_value=True), \
             patch.object(self.plan, "run_command", side_effect=fake_run):
            created = self.plan._prepare_free_space_target(
                {"disk": "/dev/nvme0n1", "free_region_start": 40 * 1024**3, "free_region_end": 80 * 1024**3},
                lambda _msg: None,
            )

        mock_unmount.assert_called_once_with("/dev/nvme0n1", unittest.mock.ANY)
        self.assertEqual(created, ("/dev/nvme0n1", "/dev/nvme0n1p2"))
        flattened = [" ".join(cmd) for cmd in commands]
        self.assertTrue(any(
            f"parted -s /dev/nvme0n1 unit B mkpart KythOS btrfs {40 * 1024**3}B {80 * 1024**3 - 512}B" in cmd
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
             patch.object(server, "_validate_storage_intent"), \
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
             patch.object(server, "_validate_storage_intent"), \
             patch.object(server, "list_timezones", return_value=["UTC"]), \
             patch.object(install, "_run_install"):
            handler.do_POST()

        handler.send_error.assert_not_called()
        written = handler.wfile.getvalue().decode().lower()
        self.assertIn('"started": true', written)
        self.assertEqual(install._state["disk"], "/dev/sda")
        self.assertEqual(install._state["install_mode"], "wipe")
        self.assertEqual(install._state["username"], "user")
        self.assertEqual(install._state["timezone"], "UTC")
        self.assertTrue(install._state["password_hash"].startswith("$6$"))

    @patch.object(server.Handler, "_require_same_origin_context", return_value=True)
    @patch.object(server.Handler, "_require_auth", return_value=True)
    def test_start_rejects_empty_password(self, *_mocks):
        disks = [{"name": "/dev/sda", "current": False, "size_bytes": 64 * 1024**3}]
        handler = self._make_handler({
            "disk": "/dev/sda",
            "install_mode": "wipe",
            "username": "user",
            "password": "",
            "confirm_backup": True,
            "confirm_erase": True,
        })
        with patch.object(server, "list_disks", return_value=disks), \
             patch.object(server, "_validate_storage_intent"), \
             patch.object(server, "list_timezones", return_value=["UTC"]), \
             patch.object(install, "_run_install"):
            handler.do_POST()

        written = handler.wfile.getvalue().decode().lower()
        self.assertIn('"started": false', written)
        self.assertIn('could not hash password', written)


class InstallerSystemTests(unittest.TestCase):
    @patch("kyth_installer.system.subprocess.run")
    def test_hash_password_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="$6$hashedpassword\n")
        res = system._hash_password("mypassword")
        self.assertEqual(res, "$6$hashedpassword")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd, ["openssl", "passwd", "-6", "-stdin"])
        self.assertEqual(mock_run.call_args[1].get("input"), "mypassword")

    def test_hash_password_empty_raises(self):
        with self.assertRaisesRegex(RuntimeError, "Password cannot be empty"):
            system._hash_password("")

    @patch("kyth_installer.system.subprocess.run")
    def test_hash_password_invalid_hash_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="invalidhash\n")
        with self.assertRaisesRegex(RuntimeError, "invalid SHA-512 crypt value"):
            system._hash_password("mypassword")

    def test_write_lines_creates_file_with_correct_permissions(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_file"
            # Simulate the elevated process (launcher always runs as root).
            with patch.object(system.os, "geteuid", return_value=0):
                system._write_lines(test_file, ["line1", "line2"], 0o644)
            self.assertEqual(test_file.read_text(), "line1\nline2\n")
            mode = test_file.stat().st_mode & 0o777
            self.assertEqual(mode, 0o644)

    def test_write_lines_creates_sensitive_file_with_restricted_permissions(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "sensitive_file"
            try:
                with patch.object(system.os, "geteuid", return_value=0):
                    system._write_lines(test_file, ["secret1", "secret2"], 0o000)
                mode = test_file.stat().st_mode & 0o777
                self.assertEqual(mode, 0o000)
                os.chmod(test_file, 0o600)
                self.assertEqual(test_file.read_text(), "secret1\nsecret2\n")
            finally:
                try:
                    os.chmod(test_file, 0o600)
                except Exception:
                    pass

    def test_write_lines_uses_elevated_mkdir_tee_chmod(self):
        """Account DB writes must go through _as_root, not bare open()."""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch, call

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "subdir" / "passwd"
            with patch.object(system, "run_command") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                system._write_lines(test_file, ["user:x:1000:1000::/home/user:"], 0o644)

            cmds = [c.args[0] for c in mock_run.call_args_list]
            # First arg is the argv list (possibly with sudo -n prefix when non-root).
            flat = [" ".join(str(p) for p in cmd) for cmd in cmds]
            self.assertTrue(any("mkdir" in s and "subdir" in s for s in flat), flat)
            self.assertTrue(any("tee" in s and "passwd" in s for s in flat), flat)
            self.assertTrue(any("chmod" in s and "644" in s for s in flat), flat)

    def test_require_root_rejects_non_root(self):
        with patch.object(system.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(RuntimeError, "must run as root"):
                system.require_root()

    def test_require_root_accepts_root(self):
        with patch.object(system.os, "geteuid", return_value=0):
            system.require_root()  # does not raise

    def test_format_os_error_includes_path_and_errno(self):
        err = OSError(13, "Permission denied")
        err.filename = "/target/etc/shadow"
        text = system.format_os_error(err)
        self.assertIn("Permission denied", text)
        self.assertIn("path=/target/etc/shadow", text)
        self.assertIn("errno=13", text)
        self.assertIn("EACCES", text)

    def test_format_install_error_wraps_permission_error(self):
        err = PermissionError(30, "Read-only file system")
        err.filename = "/var/tmp/kyth-install-root"
        text = system.format_install_error(err)
        self.assertIn("PermissionError", text)
        self.assertIn("Read-only file system", text)
        self.assertIn("/var/tmp/kyth-install-root", text)


class InstallerGptDiskTests(unittest.TestCase):
    @patch("kyth_installer.plan.subprocess.check_output")
    def test_is_gpt_disk_via_blkid(self, mock_check_output):
        mock_check_output.return_value = "gpt\n"
        self.assertTrue(plan._is_gpt_disk("/dev/sda"))
        mock_check_output.assert_called_once_with(
            ["blkid", "-o", "value", "-s", "PTTYPE", "/dev/sda"],
            text=True, stderr=plan.subprocess.DEVNULL, timeout=5
        )

    @patch("kyth_installer.plan.subprocess.check_output")
    def test_is_gpt_disk_via_parted(self, mock_check_output):
        mock_check_output.side_effect = [
            plan.subprocess.CalledProcessError(1, "blkid"),
            "Model: Virtual Disk\nPartition Table: gpt\n"
        ]
        self.assertTrue(plan._is_gpt_disk("/dev/sda"))
        self.assertEqual(mock_check_output.call_count, 2)

    @patch("kyth_installer.plan.subprocess.check_output")
    def test_is_gpt_disk_non_gpt(self, mock_check_output):
        mock_check_output.return_value = "dos\n"
        self.assertFalse(plan._is_gpt_disk("/dev/sda"))


if __name__ == "__main__":
    unittest.main()
