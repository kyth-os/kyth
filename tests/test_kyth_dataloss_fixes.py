"""Data-loss fix regressions: wipe preflight, honest journal messages,
reboot-persistent NTFS already-shrunk detection, setup-restore dotfile
backup, and pre-gaming no-snapshot warnings."""

import contextlib
import subprocess  # nosec B404
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer import fsresize, plan_commit, plan_validate  # noqa: E402
from kyth_installer.storage_snapshot import StorageSnapshot  # noqa: E402
from kyth_shared import gaming_snapshot, setup_transfer  # noqa: E402


def _snapshot(parts):
    return StorageSnapshot(
        disks=({"name": "/dev/sda", "size_bytes": 512 * 1024**3},),
        partitions=tuple(parts),
        free_regions=(), efi_partition=None, is_gpt=True,
    )


def _validate_deps(snapshot):
    return plan_validate.ValidationDependencies(
        parent_disk=lambda target: "/dev/sda",
        list_partitions=lambda disk: [],
        probe_storage=lambda disk, **kwargs: snapshot,
        get_journal=lambda context: None,
    )


class WipePreflightTests(unittest.TestCase):
    def test_wipe_fails_closed_on_locked_bitlocker(self):
        snapshot = _snapshot([
            {"name": "/dev/sda1", "efi": True, "fstype": "vfat"},
            {"name": "/dev/sda2", "efi": False, "fstype": "bitlocker"},
        ])
        with self.assertRaisesRegex(RuntimeError, "BitLocker"):
            plan_validate._validate_install_target(
                {"disk": "/dev/sda", "install_mode": "wipe"},
                dependencies=_validate_deps(snapshot),
            )

    def test_wipe_passes_without_esp_but_non_wipe_needs_it(self):
        snapshot = _snapshot([
            {"name": "/dev/sda1", "efi": False, "fstype": "ext4"},
        ])
        disk, target = plan_validate._validate_install_target(
            {"disk": "/dev/sda", "install_mode": "wipe"},
            dependencies=_validate_deps(snapshot),
        )
        self.assertEqual((disk, target), ("/dev/sda", None))

    def test_wipe_probe_includes_partitions(self):
        seen = {}

        def probe(disk, **kwargs):
            seen.update(kwargs)
            return _snapshot([{"name": "/dev/sda1", "efi": False, "fstype": "ext4"}])

        deps = plan_validate.ValidationDependencies(
            parent_disk=lambda target: "/dev/sda",
            list_partitions=lambda disk: [],
            probe_storage=probe,
            get_journal=lambda context: None,
        )
        plan_validate._validate_install_target(
            {"disk": "/dev/sda", "install_mode": "wipe"}, dependencies=deps,
        )
        self.assertTrue(seen.get("include_partitions"), seen)


class PartialWriteWarningTests(unittest.TestCase):
    def _deps(self, **changes):
        values = {
            "is_gpt": lambda _disk: False,
            "has_bios_boot": lambda _disk: True,
            "list_partitions": mock.Mock(return_value=[{"name": "/dev/sda2"}]),
            "block_size": lambda _disk: 512,
            "latest_partition": mock.Mock(return_value="/dev/sda2"),
            "partition_number": lambda _part: 2,
            "human_size": lambda size: f"{size} bytes",
            "run_command": mock.Mock(),
            "as_root": lambda argv: argv,
            "settle": mock.Mock(),
            "disk_hold": lambda _disk, _log: contextlib.nullcontext(),
            "guard_factory": lambda *_args, **_kwargs: contextlib.nullcontext(),
            "disk_service_factory": mock.Mock(return_value=object()),
        }
        values.update(changes)
        return plan_commit.CommitDependencies(**values)

    def test_guarded_pre_step_warns_table_restore_is_not_full_rollback(self):
        logs = []
        created = plan_commit.commit_new_kythos_partition(
            "/dev/sda", 1024, 4096, logs.append, dependencies=self._deps(),
            before_partition=lambda: None,
        )
        self.assertEqual(created, "/dev/sda2")
        self.assertTrue(
            any("NOT undone" in message for message in logs),
            logs,
        )

    def test_no_warning_without_pre_step(self):
        logs = []
        plan_commit.commit_new_kythos_partition(
            "/dev/sda", 1024, 4096, logs.append, dependencies=self._deps(),
        )
        self.assertFalse(any("NOT undone" in message for message in logs), logs)


class JournalHonestyTests(unittest.TestCase):
    def test_rollback_message_is_table_only(self):
        from kyth_installer.partition_ops_journal import Journal

        journal = Journal.__new__(Journal)
        journal._snapshot_saved = True
        journal._backup_dir = None
        journal._disk_service = mock.Mock()
        journal._disk_service.dry_run = True
        journal.ops = [{"kind": "create", "params": {}, "index": 0}]
        journal._committed = True
        journal._root_partition = "/dev/sda2"
        logs = []
        journal.rollback(logs.append)
        self.assertEqual(journal.ops, [])
        self.assertTrue(
            any("table only" in message for message in logs), logs,
        )

    def test_guard_restore_message_is_table_only(self):
        from kyth_installer import storage_guard

        disk_service = mock.Mock()
        disk_service.dry_run = False
        logs = []
        with self.assertRaises(RuntimeError):
            with storage_guard.PartitionTableGuard(
                "/dev/sda", logs.append, disk_service=disk_service,
            ):
                raise RuntimeError("mkpart failed")
        disk_service.restore_table.assert_called_once()
        self.assertTrue(
            any("table only" in message for message in logs), logs,
        )


class NtfsAlreadyShrunkTests(unittest.TestCase):
    def test_refuses_second_shrink_when_filesystem_smaller_than_partition(self):
        log = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "already smaller"):
            plan_commit._fail_if_ntfs_already_shrunk(
                "/dev/sda2", 100 * 1024**3, log,
                ntfs_fs_size=lambda _part: 60 * 1024**3,
            )

    def test_passes_when_filesystem_matches_partition_or_no_probe(self):
        log = mock.Mock()
        plan_commit._fail_if_ntfs_already_shrunk(
            "/dev/sda2", 100 * 1024**3, log,
            ntfs_fs_size=lambda _part: 100 * 1024**3,
        )
        # No probe wired: in-session marker check below still applies.
        plan_commit._fail_if_ntfs_already_shrunk("/dev/sda2", 100 * 1024**3, log)

    def test_fails_closed_when_probe_errors(self):
        # A wired probe that cannot read the volume must block the shrink:
        # ntfsresize refuses dirty/hibernated/damaged volumes — exactly the
        # ones that must not be shrunk. (The probe itself raises on nonzero
        # exit; unattemptable/unparsable still yields None and falls back to
        # the in-session marker check.)
        log = mock.Mock()
        def boom(_part):
            raise OSError("dirty volume")
        with self.assertRaisesRegex(RuntimeError, "Could not read the live NTFS"):
            plan_commit._fail_if_ntfs_already_shrunk(
                "/dev/sda2", 100 * 1024**3, log, ntfs_fs_size=boom,
            )
        plan_commit._fail_if_ntfs_already_shrunk(
            "/dev/sda2", 100 * 1024**3, log, ntfs_fs_size=lambda _part: None,
        )

    def test_prepare_ntfs_refuses_already_shrunk_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            deps = {
                "normal_device_path": lambda value: value or "",
                "validate_target": mock.Mock(
                    return_value=("/dev/sda", "/dev/sda2", 20 * 1024**3)
                ),
                "required_tools": ("ntfsresize", "parted"),
                "which": lambda command: f"/usr/bin/{command}",
                "unmount_target_disk": mock.Mock(),
                "partition_size": mock.Mock(return_value=100 * 1024**3),
                "partition_number": lambda _partition: 2,
                "block_size": lambda _disk: 512,
                "partition_start": lambda _partition: 1000,
                "shrink_filesystem_guarded": mock.Mock(),
                "run_command": mock.Mock(),
                "as_root": lambda command: command,
                "settle": mock.Mock(),
                "commit_partition": mock.Mock(return_value="/dev/sda3"),
                "marker_root": Path(tmp),
                "ntfs_fs_size": lambda _part: 60 * 1024**3,
            }
            with self.assertRaisesRegex(RuntimeError, "already smaller"):
                plan_commit.prepare_ntfs_resize_target(
                    {"resize_partition": "/dev/sda2"}, mock.Mock(), **deps,
                )
            deps["shrink_filesystem_guarded"].assert_not_called()

    def test_ntfs_size_probe_parses_info_output(self):
        completed = subprocess.CompletedProcess(
            args=["ntfsresize"], returncode=0,
            stdout="Current volume size: 62914560000 bytes (61440 MB)\n", stderr="",
        )
        with mock.patch.object(fsresize, "_run_typed", return_value=completed):
            self.assertEqual(
                fsresize.ntfs_filesystem_size_bytes("/dev/sda2"), 62914560000,
            )
        failed = subprocess.CompletedProcess(
            args=["ntfsresize"], returncode=1, stdout="", stderr="",
        )
        # Nonzero exit = ntfsresize refused the volume (dirty/hibernated/
        # damaged): the probe raises so callers fail closed instead of
        # shrinking blind.
        with mock.patch.object(fsresize, "_run_typed", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, "refused to read"):
                fsresize.ntfs_filesystem_size_bytes("/dev/sda2")
        with mock.patch.object(
            fsresize, "_run_typed", side_effect=OSError("no helper"),
        ):
            self.assertIsNone(fsresize.ntfs_filesystem_size_bytes("/dev/sda2"))


class NtfsProbeEdgeTests(unittest.TestCase):
    def test_probe_returns_none_on_unparsable_output(self):
        completed = subprocess.CompletedProcess(
            args=['ntfsresize'], returncode=0,
            stdout='garbage with no size line', stderr='',
        )
        with mock.patch.object(fsresize, '_run_typed', return_value=completed):
            self.assertIsNone(fsresize.ntfs_filesystem_size_bytes('/dev/sda2'))

    def test_shrink_falls_back_to_partition_when_parent_probe_breaks(self):
        # lsblk unavailable: parent lookup fails -> partition itself is used
        # for the encryption check rather than aborting the probe.
        with mock.patch(
            "kyth_installer.assurance._battery_check", return_value=None
        ), mock.patch(
            "kyth_installer.disk._parent_disk", side_effect=OSError("no lsblk")
        ), mock.patch(
            "kyth_installer.assurance._encryption_check"
        ) as enc:
            enc.return_value = None
            fsresize.validate_shrink_request('/dev/sda2', 'ext4')
        enc.assert_called_once()
        self.assertEqual(enc.call_args.kwargs.get('disk'), '/dev/sda2')


class SetupRestoreBackupTests(unittest.TestCase):
    def _archive_with(self, tmp: Path, files: dict):
        payload = tmp / "payload" / setup_transfer.ARCHIVE_PREFIX
        (payload / "files").mkdir(parents=True)
        for rel, text in files.items():
            target = payload / "files" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        (payload / "manifest.json").write_text(
            __import__("json").dumps({
                "format": "KythOS setup transfer",
                "version": setup_transfer.ARCHIVE_VERSION,
                "copied_paths": sorted(files),
                "flatpaks": [],
            }), encoding="utf-8",
        )
        archive = tmp / "setup.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(payload.parent, arcname=".", recursive=True)
        # Re-pack with the exact prefix layout _safe_extract expects.
        archive.unlink()
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(payload, arcname=setup_transfer.ARCHIVE_PREFIX, recursive=True)
        return archive

    def test_restore_backs_up_existing_dotfiles_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            (home / ".config").mkdir(parents=True)
            (home / ".config/kdeglobals").write_text("current-settings", encoding="utf-8")
            archive = self._archive_with(
                tmp_path, {".config/kdeglobals": "restored-settings"},
            )
            with mock.patch.object(Path, "home", return_value=home):
                setup_transfer.restore_setup(str(archive))
            backups = list(
                (home / ".local/share/kyth/setup-restore-backup").glob("*/.config/kdeglobals")
            )
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "current-settings")
            self.assertEqual(
                (home / ".config/kdeglobals").read_text(encoding="utf-8"),
                "restored-settings",
            )

    def test_no_backup_dir_when_nothing_existed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            archive = self._archive_with(
                tmp_path, {".config/kdeglobals": "restored-settings"},
            )
            with mock.patch.object(Path, "home", return_value=home):
                setup_transfer.restore_setup(str(archive))
            self.assertFalse(
                (home / ".local/share/kyth/setup-restore-backup").exists(),
            )


class GamingSnapshotWarningTests(unittest.TestCase):
    def test_no_tool_result_is_a_warning_not_silent_ok(self):
        with mock.patch.object(
            gaming_snapshot, "run",
            side_effect=[
                mock.Mock(returncode=1, stdout=""),
                mock.Mock(returncode=1, stdout=""),
            ],
        ):
            result = gaming_snapshot.create_pre_gaming_snapshot()
        self.assertFalse(result["ok"])
        self.assertTrue(result.get("warning"))
        self.assertNotIn("safe to proceed", result["error"])
        self.assertIn("WITHOUT", result["error"])

    def test_snapshot_success_shape_unchanged(self):
        with mock.patch.object(
            gaming_snapshot, "run",
            return_value=mock.Mock(returncode=0, stdout="17\n"),
        ):
            result = gaming_snapshot.create_pre_gaming_snapshot()
        self.assertEqual(result, {"ok": True, "id": "17", "tool": "snapper"})

    def test_apply_master_surfaces_no_snapshot_warning(self):
        from kyth_shared import gaming_master

        warning = {"ok": False, "warning": True, "error": "proceeding WITHOUT a snapshot"}
        snapshot_module = mock.Mock(
            ensure_snapshot_before_master=mock.Mock(return_value=warning),
        )
        with (
            mock.patch.object(gaming_master, "load_master", return_value={"profile": "gaming"}),
            mock.patch.object(gaming_master, "_thermal_high", return_value=False),
            mock.patch.object(gaming_master, "_battery_low", return_value=False),
            mock.patch.dict("sys.modules", {"kyth_shared.gaming_snapshot": snapshot_module}),
        ):
            # apply_master imports gaming_snapshot dynamically at call time,
            # so the sys.modules entry above is what it sees — no reload.
            out = gaming_master.apply_master(dry_run=False)
        # The no-snapshot state must be visible to the caller, not dropped.
        self.assertIn("snapshot", out)
        self.assertIn("WITHOUT", out["snapshot"])


if __name__ == "__main__":
    unittest.main()
