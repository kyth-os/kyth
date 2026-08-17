"""plan.py is a thin compatibility facade: each of these functions binds
this module's production dependencies (real disk/partition/command
callables) and forwards to plan_query/plan_commit/plan_validate, which own
the actual logic and have their own dependency-injected test coverage.
These tests exist to prove the wiring itself — that each facade function
calls the right delegate with the right dependency bundle — not to
re-exercise logic already covered elsewhere.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "build_files" / "kyth-installer"))

from kyth_installer import plan  # noqa: E402


class ValidateTargetFacadeTests(unittest.TestCase):
    def test_validate_efi_target_forwards_with_production_dependencies(self):
        with mock.patch.object(plan, "_pv_validate_efi_target", return_value="ok") as delegate:
            result = plan._validate_efi_target("sda", "sda1")

        self.assertEqual(result, "ok")
        delegate.assert_called_once()
        args, kwargs = delegate.call_args
        self.assertEqual(args, ("sda", "sda1"))
        dependencies = kwargs["dependencies"]
        self.assertEqual(dependencies.parent_disk, plan._parent_disk)
        self.assertEqual(dependencies.list_partitions, plan.list_partitions)
        self.assertEqual(dependencies.probe_storage, plan._probe_storage)
        self.assertEqual(dependencies.get_journal, plan.partition_ops.get_journal)

    def test_validate_efi_target_honors_an_explicit_dependencies_override(self):
        sentinel = object()
        with mock.patch.object(plan, "_pv_validate_efi_target", return_value="ok") as delegate:
            plan._validate_efi_target("sda", "sda1", dependencies=sentinel)

        # setdefault must not clobber a caller-supplied override.
        self.assertIs(delegate.call_args.kwargs["dependencies"], sentinel)

    def test_validate_partition_target_forwards_with_production_dependencies(self):
        with mock.patch.object(plan, "_pv_validate_partition_target", return_value="ok") as delegate:
            result = plan._validate_partition_target("sda", "sda2")

        self.assertEqual(result, "ok")
        dependencies = delegate.call_args.kwargs["dependencies"]
        self.assertEqual(dependencies.parent_disk, plan._parent_disk)
        self.assertEqual(dependencies.get_journal, plan.partition_ops.get_journal)


class PlanQueryFacadeTests(unittest.TestCase):
    def test_suggest_windows_resize_target_forwards_to_plan_query(self):
        with mock.patch.object(plan._plan_query, "suggest_windows_resize_target", return_value={"disk": "sda"}) as delegate:
            result = plan.suggest_windows_resize_target(snapshot="snap")

        self.assertEqual(result, {"disk": "sda"})
        delegate.assert_called_once_with(
            list_disks=plan.list_disks, probe_storage=plan._probe_storage, snapshot="snap",
        )

    def test_find_bootcurrent_esp_forwards_to_plan_query(self):
        with mock.patch.object(plan._plan_query, "find_bootcurrent_esp", return_value="/dev/sda1") as delegate:
            result = plan.find_bootcurrent_esp()

        self.assertEqual(result, "/dev/sda1")
        delegate.assert_called_once_with(
            run_command=plan.run_command, as_root=plan._as_root, which=plan.shutil.which,
        )

    def test_required_guided_space_forwards_to_plan_query(self):
        with mock.patch.object(plan._plan_query, "required_guided_space", return_value=1234) as delegate:
            result = plan._required_guided_space("sda")

        self.assertEqual(result, 1234)
        delegate.assert_called_once_with(
            "sda", is_gpt=plan._is_gpt_disk, has_bios_boot=plan._has_bios_boot_partition,
        )

    def test_get_manual_mounts_forwards_to_plan_query(self):
        with mock.patch.object(plan._plan_query, "get_manual_mounts", return_value=[{"mount": "/data"}]) as delegate:
            result = plan._get_manual_mounts(context="ctx")

        self.assertEqual(result, [{"mount": "/data"}])
        delegate.assert_called_once_with(
            "ctx", get_journal=plan.partition_ops.get_journal, list_partitions=plan.list_partitions,
        )


class GuidedInstallPlanFacadeTests(unittest.TestCase):
    def test_prepare_ntfs_install_plan_forwards_with_ntfs_target_functions(self):
        with mock.patch.object(plan._plan_commit, "prepare_guided_install_plan", return_value="plan") as delegate:
            result = plan._prepare_ntfs_install_plan({"install_mode": "resize_ntfs"}, log=print)

        self.assertEqual(result, "plan")
        delegate.assert_called_once_with(
            {"install_mode": "resize_ntfs"}, print,
            validate_target=plan._validate_resize_ntfs_target,
            prepare_target=plan._prepare_ntfs_resize_target,
        )

    def test_prepare_free_space_install_plan_forwards_with_free_space_target_functions(self):
        with mock.patch.object(plan._plan_commit, "prepare_guided_install_plan", return_value="plan") as delegate:
            result = plan._prepare_free_space_install_plan({"install_mode": "free_space"}, log=print)

        self.assertEqual(result, "plan")
        delegate.assert_called_once_with(
            {"install_mode": "free_space"}, print,
            validate_target=plan._validate_free_space_target,
            prepare_target=plan._prepare_free_space_target,
        )


if __name__ == "__main__":
    unittest.main()
