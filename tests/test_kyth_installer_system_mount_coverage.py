import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))

from kyth_installer import system, system_mount  # noqa: E402


class SystemMountCoverageTests(unittest.TestCase):
    def test_mount_and_unmount_use_typed_helper_when_installed(self):
        run = mock.Mock(return_value=SimpleNamespace(returncode=0))
        root = mock.Mock(side_effect=lambda argv: ["sudo", *argv])
        with mock.patch.object(
            system_mount.shutil, "which", return_value="/usr/bin/kyth-installer-exec"
        ):
            system_mount.mount_filesystem(
                "/dev/sda2", "/target", options=["subvol=@"],
                run=run, as_root=root, check=True,
            )
            system_mount.unmount_filesystem(
                "/target", recursive=True, lazy=True,
                run=run, as_root=root, check=False,
            )

        self.assertEqual(run.call_count, 2)
        self.assertEqual(
            run.call_args_list[0].args[0],
            ["sudo", "kyth-installer-exec", "--operation", "disk"],
        )
        mount_payload = json.loads(run.call_args_list[0].kwargs["input"])
        self.assertEqual(mount_payload["options"], ["subvol=@"])
        unmount_payload = json.loads(run.call_args_list[1].kwargs["input"])
        self.assertTrue(unmount_payload["recursive"])
        self.assertTrue(unmount_payload["lazy"])

    def test_lsblk_parser_walks_nested_mounts_deepest_first(self):
        payload = {
            "blockdevices": [{
                "name": "/dev/sda", "mountpoints": [],
                "children": [{
                    "name": "/dev/sda1", "mountpoints": ["/target", "/target/home"]
                }],
            }]
        }
        with mock.patch.object(
            system_mount, "run_command",
            return_value=SimpleNamespace(stdout=json.dumps(payload)),
        ):
            mounts = system_mount._orig_lsblk_target_mounts("/dev/sda")
        self.assertEqual(mounts[0], ("/dev/sda1", "/target/home"))

    def test_compatibility_shims_use_patched_facade_dependencies(self):
        run = mock.Mock(return_value="run")
        unmount = mock.Mock(return_value="unmounted")
        settle = mock.Mock(return_value="settled")
        root = mock.Mock(return_value=["root"])
        mounts = mock.Mock(return_value=[])
        with (
            mock.patch.object(system, "run_command", run),
            mock.patch.object(system, "_safe_umount", unmount),
            mock.patch.object(system, "_settle", settle),
            mock.patch.object(system, "_as_root", root),
            mock.patch.object(system, "_lsblk_target_mounts", mounts),
        ):
            self.assertEqual(system_mount.run_command(["true"]), "run")
            self.assertEqual(system_mount._safe_umount(run, "/target"), "unmounted")
            self.assertEqual(system_mount._settle(), "settled")
            self.assertEqual(system_mount._as_root(["true"]), ["root"])
            self.assertEqual(system_mount._lsblk_target_mounts("/dev/sda"), [])

    def test_unmount_failure_with_empty_output_is_still_fail_closed(self):
        run = mock.Mock(return_value=SimpleNamespace(returncode=1, stdout="", stderr=""))
        with (
            mock.patch.object(
                system_mount, "_lsblk_target_mounts",
                side_effect=[[('/dev/sda1', '/target')], [('/dev/sda1', '/target')]],
            ),
            mock.patch.object(system_mount, "run_command", run),
            mock.patch.object(system_mount, "_safe_umount"),
        ):
            with self.assertRaisesRegex(RuntimeError, "still has mounted partitions"):
                system_mount.unmount_target_disk("/dev/sda", mock.Mock())


if __name__ == "__main__":
    unittest.main()
