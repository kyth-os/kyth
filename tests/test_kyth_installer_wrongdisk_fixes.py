"""Wrong-disk / data-loss regression tests for the installer backend.

Covers, in finding rank order:
 1. live-disk/current flag fires via probe-independent fallbacks and
    list_disks() fails closed when discovery is fully degraded;
 2. the ESP must live on the target disk;
 3. alongside targets get a fstype/label content gate before mkfs;
 4. the acknowledgement gate covers format/resize and accepts the
    canonical acknowledged-irreversible key;
 5. new_table is refused while any partition is mounted/in use;
 6. _latest_partition_on_disk never returns pre-existing partitions;
 7. Journal.commit() validates before mutating;
 8. wipe preflight probes partitions so BitLocker fires at preview.
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

import kyth_installer.disk as disk  # noqa: E402
from kyth_installer import partition_ops  # noqa: E402
from kyth_installer import partition_ops_journal as journal_mod  # noqa: E402
from kyth_installer import plan_validate, validation  # noqa: E402
from kyth_installer.context import InstallerContext  # noqa: E402
from kyth_installer.disk import _probe, _query  # noqa: E402
from kyth_installer.services.installer_service import InstallerService  # noqa: E402
from kyth_installer.storage_snapshot import StorageSnapshot  # noqa: E402

GIB = 1024**3


def _deps(**changes):
    values = {
        "parent_disk": lambda _p: "/dev/sda",
        "list_partitions": lambda _d: [],
        "probe_storage": lambda *_a, **_k: None,
        "get_journal": lambda _c: None,
    }
    values.update(changes)
    return plan_validate.ValidationDependencies(**values)


class RunningSystemDiskFallbackTests(unittest.TestCase):
    def test_mountinfo_resolves_root_without_subprocess(self):
        text = (
            "24 1 8:3 / / rw,relatime - ext4 /dev/nvme0n1p3 rw\n"
            "25 1 0:22 / /sys/fs/cgroup ro - cgroup2 cgroup2 ro\n"
        )
        with mock.patch("builtins.open", mock.mock_open(read_data=text)):
            self.assertEqual(
                _probe._running_system_disk_from_mountinfo(), "/dev/nvme0n1p3"
            )

    def test_mountinfo_ignores_non_block_roots(self):
        text = " pleb\n1 1 0:1 / / rw - overlay overlay rw\n"
        with mock.patch("builtins.open", mock.mock_open(read_data=text)):
            self.assertEqual(_probe._running_system_disk_from_mountinfo(), "")

    def test_cmdline_direct_root_device(self):
        self.assertEqual(
            _probe._running_system_disk_from_cmdline(
                "BOOT_IMAGE=/vmlinuz root=/dev/sda2 ro quiet"
            ),
            "/dev/sda2",
        )

    def test_cmdline_uuid_resolves_via_blkid(self):
        out = SimpleNamespace(stdout="/dev/sda2: UUID=\"abc\"\n")
        with mock.patch.object(disk, "run_command", return_value=out) as run:
            resolved = _probe._running_system_disk_from_cmdline(
                "root=UUID=abc ro"
            )
        self.assertEqual(resolved, "/dev/sda2")
        self.assertIn("UUID=abc", run.call_args.args[0])

    def test_cmdline_live_and_empty_tokens_resolve_to_nothing(self):
        self.assertEqual(
            _probe._running_system_disk_from_cmdline("root=live:CDLABEL=x ro"), ""
        )
        self.assertEqual(_probe._running_system_disk_from_cmdline("ro quiet"), "")

    def test_full_chain_falls_back_past_dead_findmnt(self):
        with mock.patch.object(disk, "_findmnt_source", side_effect=OSError), \
             mock.patch.object(_probe, "_running_system_disk_from_mountinfo", return_value=""), \
             mock.patch.object(_probe, "_running_system_disk_from_cmdline", return_value="/dev/sda1"):
            self.assertEqual(_probe._running_system_disk(), "/dev/sda1")

    def test_list_disks_fails_closed_when_discovery_is_degraded(self):
        with mock.patch.object(disk, "_lsblk_tree", return_value={}), \
             mock.patch.object(disk, "_running_system_disk", return_value=""), \
             mock.patch.object(disk, "_lsblk_blockdevices") as blockdevices:
            self.assertEqual(_query.list_disks(), [])
            blockdevices.assert_not_called()

    def test_wipe_of_current_disk_refused_outside_live_session(self):
        body = {
            "disk": "/dev/sda", "install_mode": "wipe",
            "username": "u", "password": "p", "hostname": "kyth",
        }
        disks = [{
            "name": "/dev/sda", "size_bytes": 128 * GIB, "current": True,
        }]
        with mock.patch.object(validation.disk, "list_disks", return_value=disks), \
             mock.patch.object(validation.disk, "list_partitions", return_value=[]), \
             mock.patch.object(validation.disk, "find_efi_partition", return_value=""), \
             mock.patch.object(validation.config, "_IS_LIVE_SESSION", False):
            with self.assertRaisesRegex(validation.InstallRequestError, "current KythOS session"):
                validation._storage_state(body, object())


class EspOnTargetDiskTests(unittest.TestCase):
    def test_requested_esp_on_other_disk_rejected(self):
        deps = _deps(
            parent_disk=lambda p: "/dev/sdb",
            list_partitions=lambda _d: [{"name": "/dev/sdb1", "efi": True}],
        )
        with self.assertRaisesRegex(RuntimeError, "not on the target disk"):
            plan_validate._validate_efi_target(
                {"efi_partition": "/dev/sdb1"}, "/dev/sda2", "/dev/sda1",
                dependencies=deps, install_disk="/dev/sda",
            )

    def test_requested_esp_on_target_disk_accepted(self):
        deps = _deps(
            parent_disk=lambda _p: "/dev/sda",
            list_partitions=lambda _d: [{"name": "/dev/sda1", "efi": True}],
        )
        self.assertEqual(
            plan_validate._validate_efi_target(
                {"efi_partition": "/dev/sda1"}, "/dev/sda2", None,
                dependencies=deps, install_disk="/dev/sda",
            ),
            "/dev/sda1",
        )

    def test_discovered_esp_confirmed_against_snapshot_without_live_rescan(self):
        parts = {"/dev/sda1": {"name": "/dev/sda1", "efi": True}}
        deps = _deps(
            parent_disk=lambda _p: "/dev/sda",
            list_partitions=mock.Mock(side_effect=AssertionError("live probe")),
        )
        self.assertEqual(
            plan_validate._validate_efi_target(
                {}, "/dev/sda2", "/dev/sda1",
                dependencies=deps, install_disk="/dev/sda",
                snapshot_parts=parts,
            ),
            "/dev/sda1",
        )
        deps.list_partitions.assert_not_called()

    def test_stale_discovered_esp_rejected(self):
        deps = _deps(parent_disk=lambda _p: "/dev/sda")
        with self.assertRaisesRegex(RuntimeError, "no longer a valid EFI"):
            plan_validate._validate_efi_target(
                {}, "/dev/sda2", "/dev/sda1",
                dependencies=deps, install_disk="/dev/sda",
                snapshot_parts={"/dev/sda1": {"name": "/dev/sda1", "efi": False}},
            )

    def test_cli_path_rejects_cross_disk_esp(self):
        with mock.patch.object(
            validation.disk, "_parent_disk",
            side_effect=lambda p: "/dev/sdb" if p == "/dev/sdb1" else "/dev/sda",
        ), mock.patch.object(
            validation.disk, "list_disks",
            return_value=[{"name": "/dev/sda", "size_bytes": 128 * GIB}],
        ), mock.patch.object(
            validation.disk, "list_partitions", return_value=[],
        ), mock.patch.object(
            validation.disk, "find_efi_partition", return_value="",
        ), mock.patch.object(
            validation.plan, "_validate_storage_intent", return_value=None,
        ):
            with self.assertRaisesRegex(
                validation.InstallRequestError, "not on the target disk"
            ):
                validation.validate_partition_install_request(
                    target_partition="/dev/sda2", efi_partition="/dev/sdb1",
                    hostname="kyth", timezone="UTC", username="",
                    password="", context=object(),
                )


class AlongsideContentGateTests(unittest.TestCase):
    def _check(self, part, label="target partition"):
        snap = StorageSnapshot(
            disks=(), partitions=(part,), free_regions=(),
            efi_partition=None, is_gpt=False,
        )
        return plan_validate._validate_partition_target(
            "/dev/sda", part["name"], label,
            snapshot=snap, dependencies=_deps(),
        )

    def _big(self, **changes):
        part = {"name": "/dev/sda2", "size_bytes": 64 * GIB}
        part.update(changes)
        return part

    def test_ntfs_and_bitlocker_targets_refused(self):
        for fstype in ("ntfs", "ntfs3", "bitlocker"):
            with self.subTest(fstype=fstype), \
                 self.assertRaisesRegex(RuntimeError, "would destroy|destroy its contents|format it"):
                self._check(self._big(fstype=fstype, label="Windows"))

    def test_labeled_non_btrfs_volume_refused(self):
        with self.assertRaisesRegex(RuntimeError, "appears to hold data"):
            self._check(self._big(fstype="ext4", label="Data"))

    def test_btrfs_unlabeled_and_empty_targets_allowed(self):
        self.assertTrue(self._check(self._big(fstype="btrfs", label="KythOS")))
        self.assertTrue(self._check(self._big(fstype="ext4")))
        self.assertTrue(self._check(self._big()))


class CommitAckGateTests(unittest.TestCase):
    def _service_with_format_journal(self):
        context = InstallerContext()
        service = InstallerService(context)
        journal = partition_ops.init_journal("/dev/sda", context)
        journal.add_op("format", {"partition": "/dev/sda2", "fs_type": "ext4", "label": ""})
        return service, journal

    def test_format_journal_requires_acknowledgement(self):
        service, journal = self._service_with_format_journal()
        with mock.patch.object(journal, "commit") as commit:
            res = service.commit_partitions({"disk": "/dev/sda"})
        self.assertFalse(res["ok"])
        self.assertIn("acknowledgements", res["message"])
        commit.assert_not_called()

    def test_resize_journal_requires_acknowledgement(self):
        context = InstallerContext()
        service = InstallerService(context)
        journal = partition_ops.init_journal("/dev/sda", context)
        journal.add_op("resize", {"partition": "/dev/sda2", "new_size_bytes": 1024})
        with mock.patch.object(journal, "commit") as commit:
            res = service.commit_partitions(
                {"disk": "/dev/sda", "confirm_erase": True, "confirm_backup": True}
            )
        # Legacy keys still pass the gate; validation (not the ack gate)
        # decides the outcome from here.
        self.assertEqual(res["message"], "Validation failed.")
        commit.assert_not_called()

    def test_canonical_acknowledged_irreversible_accepted(self):
        service, journal = self._service_with_format_journal()
        with mock.patch.object(journal, "validate", return_value=[]), \
             mock.patch.object(journal, "commit", return_value="/dev/sda2") as commit:
            res = service.commit_partitions({
                "disk": "/dev/sda", "confirm_erase": True,
                "acknowledged-irreversible": True,
            })
        self.assertTrue(res["ok"])
        commit.assert_called_once()

    def test_legacy_confirm_backup_still_accepted(self):
        service, journal = self._service_with_format_journal()
        with mock.patch.object(journal, "validate", return_value=[]), \
             mock.patch.object(journal, "commit", return_value="/dev/sda2") as commit:
            res = service.commit_partitions({
                "disk": "/dev/sda", "confirm_erase": True, "confirm_backup": True,
            })
        self.assertTrue(res["ok"])
        commit.assert_called_once()


class NewTableInUseTests(unittest.TestCase):
    def _journal(self, parts):
        service = mock.MagicMock(dry_run=True)
        with mock.patch.object(
            journal_mod, "_normal_device_path", side_effect=lambda value: value
        ):
            journal = journal_mod.Journal("/dev/sda", disk_service=service)
        patches = [
            mock.patch.object(journal_mod, "list_partitions", return_value=parts),
            mock.patch.object(journal_mod, "_parent_disk", return_value="/dev/sda"),
            mock.patch.object(journal_mod, "list_disks", return_value=[]),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        return journal

    def test_new_table_refused_while_partition_mounted(self):
        journal = self._journal([
            {"name": "/dev/sda1", "fstype": "ext4", "current": True},
        ])
        journal.add_op("new_table", {"table_type": "gpt"})
        errors = journal.validate()
        self.assertTrue(
            any("new partition table" in error and "in use" in error for error in errors),
            errors,
        )

    def test_new_table_refused_while_lvm_mapping_active(self):
        journal = self._journal([
            {"name": "/dev/sda1", "fstype": "ext4", "in_use": True},
        ])
        journal.add_op("new_table", {"table_type": "gpt"})
        self.assertTrue(journal.validate())

    def test_new_table_allowed_on_idle_disk(self):
        journal = self._journal([
            {"name": "/dev/sda1", "fstype": "ext4",
             "start_bytes": 1024**2, "size_bytes": 50 * GIB},
        ])
        journal.add_op("new_table", {"table_type": "gpt"})
        journal.add_op("create", {"start_bytes": 4 * 1024**2, "size_bytes": 8 * GIB,
                                  "fs_type": "btrfs", "mountpoint": "/"})
        self.assertEqual(journal.validate(), [])


class CommitValidatesFirstTests(unittest.TestCase):
    def test_commit_raises_before_any_disk_mutation(self):
        service = mock.MagicMock(dry_run=True)
        with mock.patch.object(
            journal_mod, "_normal_device_path", side_effect=lambda value: value
        ):
            journal = journal_mod.Journal("/dev/sda", disk_service=service)
        journal.add_op("format", {"partition": "/dev/sda9", "fs_type": "ext4", "label": ""})
        with mock.patch.object(journal_mod, "list_partitions", return_value=[]), \
             mock.patch.object(journal_mod, "_parent_disk", return_value="/dev/sda"), \
             mock.patch.object(journal_mod, "list_disks", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "Partition validation failed"):
                journal.commit(lambda _msg: None)
        service.backup_table.assert_not_called()
        service.format_filesystem.assert_not_called()
        self.assertFalse(journal.committed)


class WipePreflightAtPreviewTests(unittest.TestCase):
    def test_preview_report_fails_closed_on_bitlocker(self):
        seen = {}

        def probe(disk, **kwargs):
            seen.update(kwargs)
            return StorageSnapshot(
                disks=({"name": "/dev/sda", "size_bytes": 512 * GIB},),
                partitions=(
                    {"name": "/dev/sda1", "efi": True, "fstype": "vfat"},
                    {"name": "/dev/sda2", "efi": False, "fstype": "bitlocker"},
                ),
                free_regions=(), efi_partition="/dev/sda1", is_gpt=True,
            )

        deps = plan_validate.ReportDependencies(
            as_request=lambda state: SimpleNamespace(
                disk="/dev/sda",
                as_state=lambda: {"disk": "/dev/sda", "install_mode": "wipe"},
            ),
            normalized_mode=lambda _request: "wipe",
            probe_storage=probe,
            validate_install=mock.Mock(),
            validate_resize=mock.Mock(),
            validate_free_space=mock.Mock(),
        )
        # Wire validate_install through the real implementation so the
        # preflight actually runs.
        real_deps = plan_validate.ValidationDependencies(
            parent_disk=lambda _p: "/dev/sda",
            list_partitions=lambda _d: [],
            probe_storage=probe,
            get_journal=lambda _c: None,
        )
        deps = plan_validate.ReportDependencies(
            as_request=deps.as_request,
            normalized_mode=deps.normalized_mode,
            probe_storage=probe,
            validate_install=lambda *a, **k: plan_validate._validate_install_target(
                *a, dependencies=real_deps, **k
            ),
            validate_resize=mock.Mock(),
            validate_free_space=mock.Mock(),
        )
        report = plan_validate.build_plan_report({"disk": "/dev/sda"}, dependencies=deps)
        self.assertTrue(seen.get("include_partitions"), seen)
        self.assertFalse(report.valid)
        self.assertTrue(any("BitLocker" in error for error in report.errors))

    def test_request_validation_probes_partitions_for_wipe(self):
        body = {"disk": "/dev/sda", "install_mode": "wipe"}
        parts = (
            {"name": "/dev/sda1", "efi": True, "fstype": "vfat"},
            {"name": "/dev/sda2", "efi": False, "fstype": "bitlocker"},
        )
        with mock.patch.object(
            validation.disk, "list_disks",
            return_value=[{"name": "/dev/sda", "size_bytes": 512 * GIB}],
        ), mock.patch.object(
            validation.disk, "list_partitions", return_value=list(parts),
        ) as list_parts, mock.patch.object(
            validation.disk, "find_efi_partition", return_value="/dev/sda1",
        ):
            with self.assertRaisesRegex(validation.InstallRequestError, "BitLocker"):
                validation._storage_state(body, object())
        list_parts.assert_called()


class CoverageGapTests(unittest.TestCase):
    """Cover the new fallback/exception branches so the coverage floor holds."""

    def test_fallback_exception_continues_to_next_fallback(self):
        with mock.patch.object(disk, "_findmnt_source", return_value=""), \
             mock.patch.object(
                 _probe, "_running_system_disk_from_mountinfo",
                 side_effect=OSError("unreadable"),
             ), \
             mock.patch.object(
                 _probe, "_running_system_disk_from_cmdline",
                 return_value="/dev/sda1",
             ):
            self.assertEqual(_probe._running_system_disk(), "/dev/sda1")

    def test_mountinfo_unreadable_resolves_to_nothing(self):
        real_open = open

        def fake_open(path, *args, **kwargs):
            if str(path) == "/proc/self/mountinfo":
                raise OSError("denied")
            return real_open(path, *args, **kwargs)

        with mock.patch("builtins.open", fake_open):
            self.assertEqual(_probe._running_system_disk_from_mountinfo(), "")

    def test_mountinfo_without_separator_line_is_skipped(self):
        text = (
            "this line has no separator at all\n"
            "25 1 8:1 / / rw,relatime - ext4 /dev/sda1 rw\n"
        )
        with mock.patch("builtins.open", mock.mock_open(read_data=text)):
            self.assertEqual(
                _probe._running_system_disk_from_mountinfo(), "/dev/sda1"
            )

    def test_mountinfo_without_root_mount_resolves_to_nothing(self):
        text = "25 1 8:1 / /boot rw,relatime - ext4 /dev/sda1 rw\n"
        with mock.patch("builtins.open", mock.mock_open(read_data=text)):
            self.assertEqual(_probe._running_system_disk_from_mountinfo(), "")

    def test_cmdline_unreadable_resolves_to_nothing(self):
        with mock.patch.object(
            Path, "read_text", side_effect=OSError("denied")
        ):
            self.assertEqual(_probe._running_system_disk_from_cmdline(), "")

    def test_mountinfo_short_line_is_skipped(self):
        text = "- x\n25 1 8:1 / / rw,relatime - ext4 /dev/sda1 rw\n"
        with mock.patch("builtins.open", mock.mock_open(read_data=text)):
            self.assertEqual(
                _probe._running_system_disk_from_mountinfo(), "/dev/sda1"
            )

    def test_cmdline_empty_root_value_is_skipped(self):
        self.assertEqual(
            _probe._running_system_disk_from_cmdline("root= ro quiet"), ""
        )

    def test_cmdline_skips_non_root_tokens(self):
        self.assertEqual(
            _probe._running_system_disk_from_cmdline(
                "BOOT_IMAGE=/vmlinuz ro root=/dev/sdb1 quiet"
            ),
            "/dev/sdb1",
        )

    def test_cmdline_unresolvable_uuid_resolves_to_nothing(self):
        out = SimpleNamespace(stdout="")
        with mock.patch.object(disk, "run_command", return_value=out):
            self.assertEqual(
                _probe._running_system_disk_from_cmdline("root=UUID=missing ro"),
                "",
            )

    def test_blkid_probe_failure_resolves_to_nothing(self):
        with mock.patch.object(disk, "run_command", side_effect=OSError("no blkid")):
            self.assertEqual(_probe._blkid_device("UUID=abc"), "")

    def test_blkid_without_device_lines_resolves_to_nothing(self):
        out = SimpleNamespace(stdout="not a device line\n")
        with mock.patch.object(disk, "run_command", return_value=out):
            self.assertEqual(_probe._blkid_device("UUID=abc"), "")

    def test_snapshot_esp_read_only_rejected(self):
        parts = {
            "/dev/sda1": {"name": "/dev/sda1", "efi": True, "read_only": True}
        }
        deps = _deps(parent_disk=lambda _p: "/dev/sda")
        with self.assertRaisesRegex(RuntimeError, "read-only"):
            plan_validate._validate_efi_target(
                {}, "/dev/sda2", "/dev/sda1",
                dependencies=deps, install_disk="/dev/sda",
                snapshot_parts=parts,
            )

    def test_stale_discovered_esp_rejected_without_snapshot(self):
        # Discovered (not requested) ESP, no snapshot: live re-scan finds it
        # invalid -> the `if not requested` raise, not the requested one.
        deps = _deps(
            parent_disk=lambda _p: "/dev/sda",
            list_partitions=lambda _d: [
                {"name": "/dev/sda1", "efi": False}
            ],
        )
        with self.assertRaisesRegex(RuntimeError, "no longer a valid EFI"):
            plan_validate._validate_efi_target(
                {}, "/dev/sda2", "/dev/sda1",
                dependencies=deps, install_disk="/dev/sda",
            )

    def test_requested_esp_read_only_rejected(self):
        deps = _deps(
            parent_disk=lambda _p: "/dev/sdb",
            list_partitions=lambda _d: [
                {"name": "/dev/sdb1", "efi": True, "read_only": True}
            ],
        )
        with self.assertRaisesRegex(RuntimeError, "read-only"):
            plan_validate._validate_efi_target(
                {"efi_partition": "/dev/sdb1"}, "/dev/sdb2", None,
                dependencies=deps, install_disk="/dev/sdb",
            )

    def test_requested_esp_rejected_when_not_an_esp(self):
        deps = _deps(
            parent_disk=lambda _p: "/dev/sdb",
            list_partitions=lambda _d: [
                {"name": "/dev/sdb1", "efi": False}
            ],
        )
        with self.assertRaisesRegex(RuntimeError, "no longer a valid EFI"):
            plan_validate._validate_efi_target(
                {"efi_partition": "/dev/sdb1"}, "/dev/sdb2", None,
                dependencies=deps, install_disk="/dev/sdb",
            )

    def test_bitlocker_partition_refuses_resize(self):
        # Exercise the per-partition check itself (line 357+): neutralize the
        # snapshot preflight, which would otherwise reject the locked volume
        # first — both layers must refuse independently.
        snapshot = StorageSnapshot(
            disks=({"name": "/dev/sda"},),
            partitions=(
                {"name": "/dev/sda1", "efi": True, "fstype": "vfat",
                 "size_bytes": 512 * 1024**2},
                {"name": "/dev/sda2", "fstype": "bitlocker",
                 "size_bytes": 200 * 1024**3},
            ),
            free_regions=(), efi_partition="/dev/sda1", is_gpt=False,
        )
        deps = plan_validate.GuidedValidationDependencies(
            probe_storage=lambda *_a, **_k: None,
            parent_disk=lambda _p: "/dev/sda",
            partition_size=lambda _p: 200 * 1024**3,
        )
        with mock.patch.object(
            plan_validate, "_check_storage_preflight", return_value=None
        ), self.assertRaisesRegex(RuntimeError, "BitLocker"):
            plan_validate.validate_resize_ntfs_target(
                {"disk": "/dev/sda", "resize_partition": "/dev/sda2",
                 "resize_gib": 40},
                snapshot=snapshot, dependencies=deps,
            )


if __name__ == "__main__":
    unittest.main()
