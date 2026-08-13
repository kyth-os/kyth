import contextlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer import plan_commit  # noqa: E402


class PlanCommitTests(unittest.TestCase):
    def dependencies(self, **changes):
        values = {
            "is_gpt": lambda _disk: True,
            "has_bios_boot": lambda _disk: False,
            "list_partitions": mock.Mock(return_value=[]),
            "block_size": lambda _disk: 512,
            "latest_partition": mock.Mock(return_value="/dev/sda1"),
            "partition_number": lambda _part: 1,
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

    def test_bios_helper_is_skipped_when_not_required(self):
        deps = self.dependencies(is_gpt=lambda _disk: False)
        self.assertEqual(
            plan_commit.ensure_bios_boot_partition(
                "/dev/sda", 1024, mock.Mock(), dependencies=deps,
            ),
            1024,
        )
        deps.run_command.assert_not_called()

    def test_bios_helper_retries_discovery_and_fails_closed(self):
        deps = self.dependencies(latest_partition=mock.Mock(side_effect=[None, None]))
        with self.assertRaisesRegex(RuntimeError, "BIOS boot partition"):
            plan_commit.ensure_bios_boot_partition(
                "/dev/sda", 1024**2, mock.Mock(), dependencies=deps,
            )
        deps.settle.assert_called_once()

    def test_partition_commit_formats_discovered_target(self):
        partitions = mock.Mock(side_effect=[[], [{"name": "/dev/sda2"}]])
        latest = mock.Mock(side_effect=["/dev/sda1", "/dev/sda2"])
        deps = self.dependencies(list_partitions=partitions, latest_partition=latest)
        created = plan_commit.commit_new_kythos_partition(
            "/dev/sda", 1024**2, 40 * 1024**3, mock.Mock(), dependencies=deps,
        )
        self.assertEqual(created, "/dev/sda2")
        commands = [call.args[0] for call in deps.run_command.call_args_list]
        self.assertTrue(any(command[0] == "mkfs.btrfs" for command in commands))

    def test_partition_commit_logs_guarded_pre_step_failure(self):
        log = mock.Mock()
        deps = self.dependencies()
        with self.assertRaisesRegex(RuntimeError, "resize failed"):
            plan_commit.commit_new_kythos_partition(
                "/dev/sda", 1024, 2048, log, dependencies=deps,
                before_partition=mock.Mock(side_effect=RuntimeError("resize failed")),
            )
        self.assertIn("resize failed", log.call_args.args[0])

    def test_ntfs_shrink_records_marker_and_surfaces_failure_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shrink = mock.Mock()
            plan_commit.shrink_ntfs_filesystem_guarded(
                "/dev/sda2", 100, 20, mock.Mock(), shrink_filesystem=shrink,
                human_size=str, marker_root=root,
            )
            self.assertEqual((root / "ntfs-shrunk-_dev_sda2").read_text(), "100\n")
        log = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "shrink failed"):
            plan_commit.shrink_ntfs_filesystem_guarded(
                "/dev/sda2", 100, 20, log,
                shrink_filesystem=mock.Mock(side_effect=RuntimeError("shrink failed")),
                human_size=str,
            )
        self.assertIn("no partition table change", log.call_args.args[0])

    def test_free_space_preparation_revalidates_after_unmount(self):
        validate = mock.Mock(side_effect=[("/dev/sda", 10, 100), ("/dev/sda", 20, 90)])
        commit = mock.Mock(return_value="/dev/sda3")
        result = plan_commit.prepare_free_space_target(
            {}, mock.Mock(), validate_target=validate, required_tools=("parted",),
            which=lambda _name: "/usr/bin/parted", unmount_target_disk=mock.Mock(),
            commit_partition=commit,
        )
        self.assertEqual(result, ("/dev/sda", "/dev/sda3"))
        commit.assert_called_once_with("/dev/sda", 20, 90, mock.ANY)
        with self.assertRaisesRegex(RuntimeError, "missing"):
            plan_commit.prepare_free_space_target(
                {}, mock.Mock(), validate_target=mock.Mock(return_value=("/dev/sda", 1, 2)),
                required_tools=("parted",), which=lambda _name: None,
                unmount_target_disk=mock.Mock(), commit_partition=mock.Mock(),
            )


if __name__ == "__main__":
    unittest.main()
