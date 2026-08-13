import contextlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from types import SimpleNamespace

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

    def ntfs_dependencies(self, **changes):
        values = {
            "normal_device_path": lambda value: value or "",
            "validate_target": mock.Mock(
                return_value=("/dev/sda", "/dev/sda2", 20)
            ),
            "required_tools": ("ntfsresize", "parted"),
            "which": lambda command: f"/usr/bin/{command}",
            "unmount_target_disk": mock.Mock(),
            "partition_size": mock.Mock(side_effect=[100, 80]),
            "partition_number": lambda _partition: 2,
            "block_size": lambda _disk: 1,
            "partition_start": lambda _partition: 1000,
            "shrink_filesystem_guarded": mock.Mock(),
            "run_command": mock.Mock(),
            "as_root": lambda command: command,
            "settle": mock.Mock(),
            "commit_partition": mock.Mock(return_value="/dev/sda3"),
        }
        values.update(changes)
        return values

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

    def test_partition_commit_tolerates_reread_and_visibility_failures(self):
        commands = mock.Mock(side_effect=[None, RuntimeError("reread"), None, None])
        partitions = mock.Mock(side_effect=[[], RuntimeError("scan failed")])
        log = mock.Mock()
        deps = self.dependencies(
            is_gpt=lambda _disk: False,
            run_command=commands, list_partitions=partitions,
            latest_partition=mock.Mock(return_value="/dev/sda2"),
        )
        created = plan_commit.commit_new_kythos_partition(
            "/dev/sda", 1024, 4096, log, dependencies=deps,
        )
        self.assertEqual(created, "/dev/sda2")
        self.assertIn("could not verify", log.call_args_list[-2].args[0])

    def test_partition_commit_fails_when_created_partition_is_not_discoverable(self):
        deps = self.dependencies(
            is_gpt=lambda _disk: False,
            latest_partition=mock.Mock(return_value=None),
        )
        with self.assertRaisesRegex(RuntimeError, "could not find"):
            plan_commit.commit_new_kythos_partition(
                "/dev/sda", 1024, 4096, mock.Mock(), dependencies=deps,
            )

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

    def test_ntfs_shrink_tolerates_marker_write_failure(self):
        marker_root = mock.Mock()
        marker_root.mkdir.side_effect = PermissionError("read-only runtime")
        shrink = mock.Mock()
        plan_commit.shrink_ntfs_filesystem_guarded(
            "/dev/sda2", 100, 20, mock.Mock(), shrink_filesystem=shrink,
            human_size=str, marker_root=marker_root,
        )
        shrink.assert_called_once()

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

    def test_free_space_preparation_rejects_disk_drift(self):
        validate = mock.Mock(side_effect=[
            ("/dev/sda", 10, 100), ("/dev/sdb", 20, 90),
        ])
        commit = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "target disk changed"):
            plan_commit.prepare_free_space_target(
                {}, mock.Mock(), validate_target=validate, required_tools=("parted",),
                which=lambda _name: "/usr/bin/parted",
                unmount_target_disk=mock.Mock(), commit_partition=commit,
            )
        commit.assert_not_called()

    def test_ntfs_preparation_revalidates_and_commits_freed_tail(self):
        dependencies = self.ntfs_dependencies()
        result = plan_commit.prepare_ntfs_resize_target(
            {"resize_partition": "/dev/sda2"}, mock.Mock(), **dependencies,
        )
        self.assertEqual(result, ("/dev/sda", "/dev/sda3"))
        self.assertEqual(dependencies["validate_target"].call_count, 2)
        dependencies["shrink_filesystem_guarded"].assert_called_once_with(
            "/dev/sda2", 80, 20, mock.ANY,
        )
        commit_call = dependencies["commit_partition"].call_args
        self.assertEqual(commit_call.args[:3], ("/dev/sda", 1080, 1100))
        commit_call.kwargs["before_partition"]()
        command = dependencies["run_command"].call_args
        self.assertEqual(command.args[0][-3:], ["resizepart", "2", "1079B"])
        self.assertEqual(command.kwargs["input"], "Yes\n")

    def test_ntfs_preparation_stops_on_session_marker_or_missing_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker_root = Path(tmp)
            (marker_root / "ntfs-shrunk-_dev_sda2").touch()
            dependencies = self.ntfs_dependencies(marker_root=marker_root)
            with self.assertRaisesRegex(RuntimeError, "already shrunk"):
                plan_commit.prepare_ntfs_resize_target(
                    {"resize_partition": "/dev/sda2"}, mock.Mock(), **dependencies,
                )
            dependencies["validate_target"].assert_not_called()

        dependencies = self.ntfs_dependencies(which=lambda _command: None)
        with self.assertRaisesRegex(RuntimeError, "ntfsresize, parted"):
            plan_commit.prepare_ntfs_resize_target(
                {"resize_partition": "/dev/sda2"}, mock.Mock(), **dependencies,
            )
        dependencies["unmount_target_disk"].assert_not_called()

    def test_ntfs_preparation_continues_when_marker_probe_is_unavailable(self):
        dependencies = self.ntfs_dependencies(
            normal_device_path=mock.Mock(side_effect=OSError("device lookup failed")),
        )
        result = plan_commit.prepare_ntfs_resize_target(
            {"resize_partition": "/dev/sda2"}, mock.Mock(), **dependencies,
        )
        self.assertEqual(result, ("/dev/sda", "/dev/sda3"))

        dependencies = self.ntfs_dependencies(normal_device_path=lambda _value: "")
        result = plan_commit.prepare_ntfs_resize_target(
            {}, mock.Mock(), **dependencies,
        )
        self.assertEqual(result, ("/dev/sda", "/dev/sda3"))

    def test_ntfs_preparation_rejects_target_drift_before_shrink(self):
        dependencies = self.ntfs_dependencies(validate_target=mock.Mock(side_effect=[
            ("/dev/sda", "/dev/sda2", 20),
            ("/dev/sda", "/dev/sda3", 20),
        ]))
        with self.assertRaisesRegex(RuntimeError, "NTFS target changed"):
            plan_commit.prepare_ntfs_resize_target(
                {"resize_partition": "/dev/sda2"}, mock.Mock(), **dependencies,
            )
        dependencies["shrink_filesystem_guarded"].assert_not_called()

    def test_ntfs_boundary_mismatch_and_post_shrink_failure_propagate(self):
        dependencies = self.ntfs_dependencies(
            partition_size=mock.Mock(side_effect=[100, 70]),
        )
        plan_commit.prepare_ntfs_resize_target(
            {"resize_partition": "/dev/sda2"}, mock.Mock(), **dependencies,
        )
        callback = dependencies["commit_partition"].call_args.kwargs["before_partition"]
        with self.assertRaisesRegex(RuntimeError, "requested NTFS boundary"):
            callback()

        dependencies = self.ntfs_dependencies(
            commit_partition=mock.Mock(side_effect=RuntimeError("mkfs failed")),
        )
        with self.assertRaisesRegex(RuntimeError, "mkfs failed"):
            plan_commit.prepare_ntfs_resize_target(
                {"resize_partition": "/dev/sda2"}, mock.Mock(), **dependencies,
            )
        dependencies["shrink_filesystem_guarded"].assert_called_once()
        call = dependencies["commit_partition"].call_args
        self.assertIn("restoring", call.kwargs["failure_message"])
        self.assertIn("already shrunk", call.kwargs["restored_message"])

    def test_plan_dispatch_validates_before_each_mode(self):
        validate = mock.Mock(return_value=SimpleNamespace(valid=True, errors=()))
        ntfs = mock.Mock(return_value="ntfs-plan")
        free = mock.Mock(return_value="free-plan")
        explicit = mock.Mock(return_value="explicit-plan")
        modes = (
            ("resize_ntfs", "ntfs-plan"),
            ("free_space", "free-plan"),
            ("wipe", "explicit-plan"),
        )
        for mode, expected in modes:
            with self.subTest(mode=mode):
                result = plan_commit.prepare_install_plan(
                    {"install_mode": mode}, mock.Mock(), object(),
                    validate_report=validate,
                    plan_from_state=lambda state: SimpleNamespace(mode=state["install_mode"]),
                    prepare_ntfs=ntfs, prepare_free_space=free,
                    prepare_explicit=explicit,
                )
                self.assertEqual(result, expected)

    def test_explicit_modes_preserve_mode_and_resolved_targets(self):
        validate = mock.Mock(return_value=("/dev/sda", "/dev/sda2"))
        context = object()
        for mode in ("wipe", "alongside", "manual"):
            with self.subTest(mode=mode):
                result = plan_commit.prepare_explicit_install_plan(
                    SimpleNamespace(mode=mode), {"install_mode": mode}, context,
                    validate_target=validate,
                )
                self.assertEqual(result.mode, mode)
                self.assertEqual(result.disk, "/dev/sda")
                self.assertEqual(result.target_partition, "/dev/sda2")
                validate.assert_called_with({"install_mode": mode}, context)

    def test_explicit_preparation_propagates_validation_failure(self):
        with self.assertRaisesRegex(RuntimeError, "manual root is missing"):
            plan_commit.prepare_explicit_install_plan(
                SimpleNamespace(mode="manual"), {}, object(),
                validate_target=mock.Mock(
                    side_effect=RuntimeError("manual root is missing")
                ),
            )

    def test_guided_preparation_revalidates_before_target_mutation(self):
        validate = mock.Mock()
        prepare = mock.Mock(return_value=("/dev/sda", "/dev/sda3"))
        result = plan_commit.prepare_guided_install_plan(
            {"install_mode": "free_space"}, mock.Mock(),
            validate_target=validate, prepare_target=prepare,
        )
        self.assertEqual(result.mode, "alongside")
        self.assertEqual(result.target_partition, "/dev/sda3")
        validate.assert_called_once()
        prepare.assert_called_once()

    def test_plan_dispatch_stops_on_report_error(self):
        with self.assertRaisesRegex(RuntimeError, "unsafe layout"):
            plan_commit.prepare_install_plan(
                {}, mock.Mock(), validate_report=mock.Mock(return_value=SimpleNamespace(
                    valid=False, errors=("unsafe layout",),
                )),
                plan_from_state=mock.Mock(), prepare_ntfs=mock.Mock(),
                prepare_free_space=mock.Mock(), prepare_explicit=mock.Mock(),
            )


if __name__ == "__main__":
    unittest.main()
