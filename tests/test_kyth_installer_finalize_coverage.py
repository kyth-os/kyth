from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth-installer"))
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_installer.context import InstallerContext, InstallLifecycle, InstallPhase, InstallRequest  # noqa: E402
from kyth_installer.phases import finalize  # noqa: E402


def _request(**changes) -> InstallRequest:
    state = InstallerContext().state
    state.update(
        hostname="kyth",
        timezone="UTC",
        locale="en_US.UTF-8",
        keymap="us",
        username="user",
        password_hash="$6$hash",
        install_mode="wipe",
        disk="/dev/sda",
        kernel="fedora",
    )
    state.update(changes)
    return InstallRequest.from_state(state)


class FstabFailureTests(unittest.TestCase):
    def test_append_fstab_uses_typed_rust_writer_when_helper_is_installed(self):
        log = mock.Mock()
        with (
            mock.patch.object(finalize.shutil, "which", return_value="/usr/bin/kyth-installer-exec"),
            mock.patch("kyth_installer.install.run_command") as run,
            mock.patch("kyth_installer.install._as_root", side_effect=lambda command: command),
        ):
            result = finalize._append_fstab_line(
                "/target/etc", "UUID=x /data ext4 defaults 0 2\n", log, "data"
            )

        self.assertTrue(result)
        self.assertEqual(
            run.call_args.args[0],
            ["kyth-installer-exec", "--operation", "fstab-append"],
        )
        payload = json.loads(run.call_args.kwargs["input"])
        self.assertEqual(payload["path"], "/target/etc/fstab")
        self.assertEqual(payload["line"], "UUID=x /data ext4 defaults 0 2\n")

    def test_append_fstab_success(self):
        log = mock.Mock()
        with (
            mock.patch("kyth_installer.install.run_command") as run,
            mock.patch("kyth_installer.install._as_root", side_effect=lambda cmd: cmd),
        ):
            result = finalize._append_fstab_line("/target/etc", "UUID=x /data ext4 defaults 0 2\n", log, "data")
        self.assertTrue(result)
        self.assertEqual(run.call_args.kwargs["input"], "UUID=x /data ext4 defaults 0 2\n")
        self.assertIn("Fstab updated", log.call_args.args[0])

    def test_append_fstab_os_error_includes_path_context(self):
        log = mock.Mock()
        with (
            mock.patch("kyth_installer.install.run_command", side_effect=OSError(30, "read-only")),
            mock.patch("kyth_installer.install._as_root", side_effect=lambda cmd: cmd),
        ):
            result = finalize._append_fstab_line("/target/etc", "line\n", log, "data")
        self.assertFalse(result)
        self.assertIn("fstab", log.call_args.args[0])

    def test_append_fstab_generic_failure_is_nonfatal(self):
        log = mock.Mock()
        with (
            mock.patch("kyth_installer.install.run_command", side_effect=RuntimeError("tee failed")),
            mock.patch("kyth_installer.install._as_root", side_effect=lambda cmd: cmd),
        ):
            result = finalize._append_fstab_line("/target/etc", "line\n", log, "data")
        self.assertFalse(result)
        self.assertIn("tee failed", log.call_args.args[0])

    def test_alongside_without_uuid_skips_fstab(self):
        with (
            mock.patch("kyth_installer.install.run_command"),
            mock.patch("kyth_installer.install._as_root", side_effect=lambda cmd: cmd),
            mock.patch("kyth_installer.install._safe_umount"),
            mock.patch.object(finalize, "_blkid_uuid", return_value=None),
            mock.patch.object(finalize, "_append_fstab_line") as append,
        ):
            finalize._configure_alongside_fstab("/target", "/dev/sda3", "/target/etc", mock.Mock())
        append.assert_not_called()


class UserCreationTests(unittest.TestCase):
    def test_user_creation_relocks_accounts_and_reports_progress(self):
        progress = mock.Mock()
        with (
            mock.patch.object(finalize, "_shared_create_installer_user") as create,
            mock.patch("kyth_installer.install.run_command"),
            mock.patch("kyth_installer.install._as_root", side_effect=lambda cmd: cmd),
            mock.patch("kyth_installer.install.ensure_system_accounts") as accounts,
        ):
            finalize._create_installer_user(
                "/target", "/deploy", "user", "$6$hash", mock.Mock(), progress
            )
        create.assert_called_once()
        accounts.assert_called_once_with("/deploy", mock.ANY)
        progress.assert_called_once_with(97)

    def test_user_creation_os_error_is_actionable_and_nonfatal(self):
        log = mock.Mock()
        with (
            mock.patch.object(
                finalize, "_shared_create_installer_user", side_effect=OSError(5, "I/O error")
            ),
            mock.patch("kyth_installer.install.run_command"),
            mock.patch("kyth_installer.install._as_root", side_effect=lambda cmd: cmd),
            mock.patch("kyth_installer.install.ensure_system_accounts"),
        ):
            finalize._create_installer_user("/target", "/deploy", "user", "hash", log, mock.Mock())
        self.assertTrue(any("user creation failed" in call.args[0] for call in log.call_args_list))
        self.assertTrue(any("sudo useradd" in call.args[0] for call in log.call_args_list))

    def test_user_creation_generic_error_is_actionable_and_nonfatal(self):
        log = mock.Mock()
        with (
            mock.patch.object(
                finalize, "_shared_create_installer_user", side_effect=RuntimeError("bad account")
            ),
            mock.patch("kyth_installer.install.run_command"),
            mock.patch("kyth_installer.install._as_root", side_effect=lambda cmd: cmd),
            mock.patch("kyth_installer.install.ensure_system_accounts"),
        ):
            finalize._create_installer_user("/target", "/deploy", "user", "hash", log, mock.Mock())
        self.assertTrue(any("bad account" in call.args[0] for call in log.call_args_list))


class ConfigureSystemTests(unittest.TestCase):
    def _base_patches(self, *, etc="/target/deploy/etc"):
        return (
            mock.patch("kyth_installer.install.run_command"),
            mock.patch("kyth_installer.install.find_deploy_etc", return_value=etc),
            mock.patch("kyth_installer.install.ensure_system_accounts"),
            mock.patch.object(finalize, "_configure_hostname_timezone"),
            mock.patch.object(finalize, "validate_installed_target", return_value=[]),
            mock.patch.object(finalize, "_persist_artifacts_to_target"),
            mock.patch.object(finalize, "unmount_configuration"),
        )

    def test_missing_deployment_still_unmounts_and_releases(self):
        context = InstallerContext()
        context.register_mount("/config")
        progress = mock.Mock()
        with (
            mock.patch("kyth_installer.install.run_command") as run,
            mock.patch("kyth_installer.install.find_deploy_etc", return_value=None),
            mock.patch("kyth_installer.install.ensure_system_accounts"),
            mock.patch.object(finalize, "unmount_configuration") as unmount,
        ):
            with self.assertRaisesRegex(RuntimeError, "deployment could not be located"):
                finalize._configure_installed_system(
                    "/dev/sda3", "/dev/sda3", "/dev/sda", "fedora", "wipe",
                    "/config", "", mock.Mock(), progress, context, _request(),
                )
        self.assertIs(context.phase, InstallPhase.CONFIGURE)
        progress.assert_called_once_with(99)
        unmount.assert_called_once_with("/config", "", run=run)
        self.assertNotIn("/config", context.cleanup_mounts)

    def test_manual_mode_configures_mounts_and_records_checks(self):
        context = InstallerContext()
        context.register_mount("/config")
        check = SimpleNamespace(status="pass", name="fstab", detail="valid", as_dict=lambda: {"name": "fstab"})
        log = mock.Mock()
        with (
            mock.patch("kyth_installer.install.run_command"),
            mock.patch("kyth_installer.install.find_deploy_etc", return_value="/config/deploy/etc"),
            mock.patch("kyth_installer.install.ensure_system_accounts"),
            mock.patch.object(finalize, "_configure_manual_mounts") as manual,
            mock.patch.object(finalize, "_configure_hostname_timezone"),
            mock.patch.object(finalize, "_create_installer_user") as create,
            mock.patch.object(finalize, "validate_installed_target", return_value=[check]),
            mock.patch.object(finalize, "_persist_artifacts_to_target"),
            mock.patch.object(finalize, "unmount_configuration"),
        ):
            finalize._configure_installed_system(
                "/dev/sda3", "/dev/sda3", "/dev/sda", "fedora", "manual",
                "/config", "", log, mock.Mock(), context, _request(install_mode="manual"),
            )
        manual.assert_called_once()
        create.assert_called_once()
        self.assertEqual(context.assurance_checks, [{"name": "fstab"}])
        self.assertTrue(any("Final check [pass]" in call.args[0] for call in log.call_args_list))

    def test_alongside_cleanup_releases_nested_mounts(self):
        context = InstallerContext()
        for mountpoint in ("/alongside", "/alongside/boot/efi", "/unrelated"):
            context.register_mount(mountpoint)
        with (
            mock.patch("kyth_installer.install.run_command"),
            mock.patch("kyth_installer.install.find_deploy_etc", return_value="/alongside/deploy/etc"),
            mock.patch("kyth_installer.install.ensure_system_accounts"),
            mock.patch.object(finalize, "_configure_alongside_fstab"),
            mock.patch.object(finalize, "_configure_hostname_timezone"),
            mock.patch.object(finalize, "_create_installer_user"),
            mock.patch.object(finalize, "validate_installed_target", return_value=[]),
            mock.patch.object(finalize, "_persist_artifacts_to_target"),
            mock.patch.object(finalize, "unmount_configuration"),
        ):
            finalize._configure_installed_system(
                "/dev/sda3", "/dev/sda3", "/dev/sda", "fedora", "alongside",
                "/alongside", "/alongside", mock.Mock(), mock.Mock(), context,
                _request(install_mode="alongside"),
            )
        self.assertEqual(context.cleanup_mounts, ["/unrelated"])

    def test_success_artifact_failure_is_logged_not_raised(self):
        context = InstallerContext()
        log = mock.Mock()
        with (
            mock.patch("kyth_installer.install.run_command"),
            mock.patch("kyth_installer.install.find_deploy_etc", return_value="/config/deploy/etc"),
            mock.patch("kyth_installer.install.ensure_system_accounts"),
            mock.patch.object(finalize, "_configure_hostname_timezone"),
            mock.patch.object(finalize, "_create_installer_user"),
            mock.patch.object(finalize, "validate_installed_target", return_value=[]),
            mock.patch.object(
                finalize, "_persist_artifacts_to_target", side_effect=OSError("copy failed")
            ),
            mock.patch.object(finalize, "unmount_configuration"),
        ):
            finalize._configure_installed_system(
                "/dev/sda3", "/dev/sda3", "/dev/sda", "fedora", "wipe",
                "/config", "", log, mock.Mock(), context, _request(username="", password_hash=""),
            )
        self.assertTrue(any("success artifacts" in call.args[0] for call in log.call_args_list))


class ConfigureInstalledSystemRollbackTests(unittest.TestCase):
    """Direct coverage for kyth_installer.phases.finalize_configure transactional paths."""

    def _call(self, **overrides):
        from kyth_installer.phases import finalize_configure as fc

        context = InstallerContext()
        context.register_mount("/config")
        log = mock.Mock()
        progress = mock.Mock()
        etc = "/config/deploy/etc"

        # Path mock for fstab handling + deploy_root
        mock_fstab = mock.Mock()
        mock_fstab.is_file.return_value = overrides.get("fstab_is_file", False)
        if overrides.get("read_bytes_error"):
            mock_fstab.read_bytes.side_effect = OSError("read fail")
        else:
            mock_fstab.read_bytes.return_value = b"original fstab"
        if overrides.get("write_error"):
            mock_fstab.write_bytes.side_effect = OSError("write fail")
        if overrides.get("unlink_error"):
            mock_fstab.unlink.side_effect = OSError("unlink fail")

        mock_etc_path = mock.MagicMock()
        mock_etc_path.__truediv__.return_value = mock_fstab
        mock_etc_path.parent = pathlib.Path("/config/deploy")
        # For validate_installed_target(Path(etc), ...) we pass mock_etc_path as Path(etc)
        mock_path_cls = mock.Mock(return_value=mock_etc_path)

        find_deploy_etc = mock.Mock(return_value=etc)
        ensure_system_accounts = mock.Mock()
        configure_alongside = mock.Mock()
        configure_manual = mock.Mock()
        configure_hostname = mock.Mock(side_effect=overrides.get("hostname_side_effect"))
        create_user = mock.Mock()
        validate_target = mock.Mock(return_value=[])
        persist = mock.Mock(side_effect=overrides.get("persist_side_effect"))
        unmount = mock.Mock()
        run_cmd = mock.Mock()

        request = _request()

        # Patch Path in finalize_configure
        with mock.patch.object(fc, "Path", mock_path_cls):
            try:
                fc.configure_installed_system(
                    target_part="/dev/sda3",
                    install_mode=overrides.get("install_mode", "wipe"),
                    config_root="/config",
                    alongside_mount="",
                    log=log,
                    progress=progress,
                    context=context,
                    request=request,
                    find_deploy_etc=find_deploy_etc,
                    ensure_system_accounts=ensure_system_accounts,
                    configure_alongside_fstab=configure_alongside,
                    configure_manual_mounts=configure_manual,
                    configure_hostname_timezone=configure_hostname,
                    create_installer_user=create_user,
                    validate_installed_target=validate_target,
                    persist_artifacts=persist,
                    unmount_configuration=unmount,
                    run_command=run_cmd,
                )
                raised = None
            except Exception as exc:
                raised = exc

        return {
            "context": context,
            "log": log,
            "progress": progress,
            "mock_fstab": mock_fstab,
            "mock_path_cls": mock_path_cls,
            "unmount": unmount,
            "raised": raised,
        }

    def test_fstab_read_oserror_sets_backup_none(self):
        result = self._call(fstab_is_file=True, read_bytes_error=True)
        self.assertIsNone(result["raised"])
        # Should not have raised; backup was None due to OSError then continued
        result["mock_fstab"].read_bytes.assert_called_once()

    def test_rollback_unlinks_when_backup_none_and_file_exists(self):
        # Exercise rollback path where backup is restored via write or unlink
        # (previous _call helper already validates the OSError backup path)
        from kyth_installer.phases import finalize_configure as fc

        context = InstallerContext()
        context.register_mount("/config")
        log = mock.Mock()
        progress = mock.Mock()
        mock_fstab = mock.Mock()
        # First is_file check returns False? Actually we need read_bytes not called then backup None
        # Simulate: fstab does not exist at backup time, but does exist at rollback (partial write)
        # Simpler: force backup None via OSError, then during rollback is_file True -> unlink
        call_count = {"is_file": 0}

        def is_file_side_effect():
            call_count["is_file"] += 1
            # First call: backup check -> True but read will raise OSError -> backup None
            # Second call: rollback check -> True -> unlink
            return True

        mock_fstab.is_file.side_effect = is_file_side_effect
        mock_fstab.read_bytes.side_effect = OSError("read fail")
        mock_etc_path = mock.MagicMock()
        mock_etc_path.__truediv__.return_value = mock_fstab
        mock_etc_path.parent = pathlib.Path("/config/deploy")
        mock_path_cls = mock.Mock(return_value=mock_etc_path)

        with mock.patch.object(fc, "Path", mock_path_cls):
            with self.assertRaises(RuntimeError):
                fc.configure_installed_system(
                    target_part="/dev/sda3",
                    install_mode="wipe",
                    config_root="/config",
                    alongside_mount="",
                    log=log,
                    progress=progress,
                    context=context,
                    request=_request(),
                    find_deploy_etc=mock.Mock(return_value="/config/deploy/etc"),
                    ensure_system_accounts=mock.Mock(),
                    configure_alongside_fstab=mock.Mock(),
                    configure_manual_mounts=mock.Mock(),
                    configure_hostname_timezone=mock.Mock(side_effect=RuntimeError("fail")),
                    create_installer_user=mock.Mock(),
                    validate_installed_target=mock.Mock(return_value=[]),
                    persist_artifacts=mock.Mock(),
                    unmount_configuration=mock.Mock(),
                    run_command=mock.Mock(),
                )
        mock_fstab.unlink.assert_called_once()
        self.assertTrue(any("Rolled back" in c.args[0] for c in log.call_args_list))

    def test_rollback_restores_backup_when_present(self):
        from kyth_installer.phases import finalize_configure as fc

        context = InstallerContext()
        context.register_mount("/config")
        log = mock.Mock()
        progress = mock.Mock()
        mock_fstab = mock.Mock()
        mock_fstab.is_file.return_value = True
        mock_fstab.read_bytes.return_value = b"orig"
        mock_etc_path = mock.MagicMock()
        mock_etc_path.__truediv__.return_value = mock_fstab
        mock_etc_path.parent = pathlib.Path("/config/deploy")
        mock_path_cls = mock.Mock(return_value=mock_etc_path)
        with mock.patch.object(fc, "Path", mock_path_cls):
            with self.assertRaises(RuntimeError):
                fc.configure_installed_system(
                    target_part="/dev/sda3",
                    install_mode="wipe",
                    config_root="/config",
                    alongside_mount="",
                    log=log,
                    progress=progress,
                    context=context,
                    request=_request(),
                    find_deploy_etc=mock.Mock(return_value="/config/deploy/etc"),
                    ensure_system_accounts=mock.Mock(),
                    configure_alongside_fstab=mock.Mock(),
                    configure_manual_mounts=mock.Mock(),
                    configure_hostname_timezone=mock.Mock(side_effect=RuntimeError("fail2")),
                    create_installer_user=mock.Mock(),
                    validate_installed_target=mock.Mock(return_value=[]),
                    persist_artifacts=mock.Mock(),
                    unmount_configuration=mock.Mock(),
                    run_command=mock.Mock(),
                )
        mock_fstab.write_bytes.assert_called_once_with(b"orig")
        self.assertTrue(any("Rolled back" in c.args[0] for c in log.call_args_list))

    def test_rollback_write_oserror_is_logged(self):
        from kyth_installer.phases import finalize_configure as fc

        context = InstallerContext()
        context.register_mount("/config")
        log = mock.Mock()
        progress = mock.Mock()
        mock_fstab = mock.Mock()
        mock_fstab.is_file.return_value = True
        mock_fstab.read_bytes.return_value = b"orig"
        mock_fstab.write_bytes.side_effect = OSError("write fail")
        mock_etc_path = mock.MagicMock()
        mock_etc_path.__truediv__.return_value = mock_fstab
        mock_etc_path.parent = pathlib.Path("/config/deploy")
        mock_path_cls = mock.Mock(return_value=mock_etc_path)
        with mock.patch.object(fc, "Path", mock_path_cls):
            with self.assertRaises(RuntimeError):
                fc.configure_installed_system(
                    target_part="/dev/sda3",
                    install_mode="wipe",
                    config_root="/config",
                    alongside_mount="",
                    log=log,
                    progress=progress,
                    context=context,
                    request=_request(),
                    find_deploy_etc=mock.Mock(return_value="/config/deploy/etc"),
                    ensure_system_accounts=mock.Mock(),
                    configure_alongside_fstab=mock.Mock(),
                    configure_manual_mounts=mock.Mock(),
                    configure_hostname_timezone=mock.Mock(side_effect=RuntimeError("fail3")),
                    create_installer_user=mock.Mock(),
                    validate_installed_target=mock.Mock(return_value=[]),
                    persist_artifacts=mock.Mock(),
                    unmount_configuration=mock.Mock(),
                    run_command=mock.Mock(),
                )
        self.assertTrue(any("rollback failed" in c.args[0] for c in log.call_args_list))

    def test_rollback_no_file_when_backup_none_skips_unlink(self):
        from kyth_installer.phases import finalize_configure as fc

        context = InstallerContext()
        context.register_mount("/config")
        log = mock.Mock()
        progress = mock.Mock()
        mock_fstab = mock.Mock()
        # First call (backup): is_file False -> backup None, second call (rollback): is_file False -> no unlink
        mock_fstab.is_file.return_value = False
        mock_etc_path = mock.MagicMock()
        mock_etc_path.__truediv__.return_value = mock_fstab
        mock_etc_path.parent = pathlib.Path("/config/deploy")
        mock_path_cls = mock.Mock(return_value=mock_etc_path)
        with mock.patch.object(fc, "Path", mock_path_cls):
            with self.assertRaises(RuntimeError):
                fc.configure_installed_system(
                    target_part="/dev/sda3",
                    install_mode="wipe",
                    config_root="/config",
                    alongside_mount="",
                    log=log,
                    progress=progress,
                    context=context,
                    request=_request(),
                    find_deploy_etc=mock.Mock(return_value="/config/deploy/etc"),
                    ensure_system_accounts=mock.Mock(),
                    configure_alongside_fstab=mock.Mock(),
                    configure_manual_mounts=mock.Mock(),
                    configure_hostname_timezone=mock.Mock(side_effect=RuntimeError("fail4")),
                    create_installer_user=mock.Mock(),
                    validate_installed_target=mock.Mock(return_value=[]),
                    persist_artifacts=mock.Mock(),
                    unmount_configuration=mock.Mock(),
                    run_command=mock.Mock(),
                )
        mock_fstab.unlink.assert_not_called()
        mock_fstab.write_bytes.assert_not_called()

    def test_rollback_unlink_oserror_is_logged(self):
        from kyth_installer.phases import finalize_configure as fc

        context = InstallerContext()
        context.register_mount("/config")
        log = mock.Mock()
        progress = mock.Mock()
        mock_fstab = mock.Mock()
        mock_fstab.is_file.return_value = True
        mock_fstab.read_bytes.side_effect = OSError("read fail")
        mock_fstab.unlink.side_effect = OSError("unlink fail")
        mock_etc_path = mock.MagicMock()
        mock_etc_path.__truediv__.return_value = mock_fstab
        mock_etc_path.parent = pathlib.Path("/config/deploy")
        mock_path_cls = mock.Mock(return_value=mock_etc_path)
        with mock.patch.object(fc, "Path", mock_path_cls):
            with self.assertRaises(RuntimeError):
                fc.configure_installed_system(
                    target_part="/dev/sda3",
                    install_mode="wipe",
                    config_root="/config",
                    alongside_mount="",
                    log=log,
                    progress=progress,
                    context=context,
                    request=_request(),
                    find_deploy_etc=mock.Mock(return_value="/config/deploy/etc"),
                    ensure_system_accounts=mock.Mock(),
                    configure_alongside_fstab=mock.Mock(),
                    configure_manual_mounts=mock.Mock(),
                    configure_hostname_timezone=mock.Mock(side_effect=RuntimeError("fail5")),
                    create_installer_user=mock.Mock(),
                    validate_installed_target=mock.Mock(return_value=[]),
                    persist_artifacts=mock.Mock(),
                    unmount_configuration=mock.Mock(),
                    run_command=mock.Mock(),
                )
        self.assertTrue(any("rollback failed" in c.args[0] for c in log.call_args_list))


class InstallFailureTests(unittest.TestCase):
    def test_failure_handler_publishes_error_and_records_diagnostics(self):
        context = InstallerContext()
        context.transition(InstallLifecycle.VALIDATED)
        context.transition(InstallLifecycle.INSTALLING)
        log = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp:
            log_path = pathlib.Path(tmp) / "installer.log"
            log_path.write_text("start\n", encoding="utf-8")
            with (
                mock.patch.object(finalize, "LOG_FILE", log_path),
                mock.patch.object(finalize, "_record_transaction") as record,
                mock.patch.object(finalize, "write_failure_summary") as summary,
                mock.patch.object(finalize, "_persist_failure_to_target_disk") as persist,
            ):
                try:
                    raise RuntimeError("image failed")
                except RuntimeError as exc:
                    finalize._handle_install_failure(exc, log, context)

        self.assertIs(context.lifecycle, InstallLifecycle.FAILED)
        record.assert_called_once()
        summary.assert_called_once()
        persist.assert_called_once()
        self.assertEqual(context.events.events[-1]["type"], "error")
        self.assertIn("image failed", context.events.events[-1]["message"])

    def test_secondary_failures_do_not_block_error_event(self):
        context = InstallerContext()
        context.transition(InstallLifecycle.VALIDATED)
        context.transition(InstallLifecycle.INSTALLING)
        log = mock.Mock()
        with (
            mock.patch.object(finalize, "LOG_FILE", pathlib.Path("/missing/installer.log")),
            mock.patch.object(finalize, "_record_transaction"),
            mock.patch.object(finalize, "write_failure_summary", side_effect=OSError("summary failed")),
            mock.patch.object(
                finalize, "_persist_failure_to_target_disk", side_effect=OSError("persist failed")
            ),
        ):
            finalize._handle_install_failure(RuntimeError("primary failure"), log, context)
        self.assertIs(context.lifecycle, InstallLifecycle.FAILED)
        self.assertEqual(context.events.events[-1]["type"], "error")
        self.assertTrue(any("summary failed" in call.args[0] for call in log.call_args_list))
        self.assertTrue(any("persist failed" in call.args[0] for call in log.call_args_list))


if __name__ == "__main__":
    unittest.main()
