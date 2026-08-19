"""Installed-system configuration orchestration for installer finalization."""

from __future__ import annotations

from pathlib import Path

from ..context import InstallPhase, InstallRequest


def configure_installed_system(
    *, target_part, install_mode, config_root, alongside_mount, log, progress,
    context, request: InstallRequest | None, find_deploy_etc,
    ensure_system_accounts, configure_alongside_fstab, configure_manual_mounts,
    configure_hostname_timezone, create_installer_user, validate_installed_target,
    persist_artifacts, unmount_configuration, run_command,
) -> None:
    """Configure and validate the deployment, then always release its mounts (transactional: fstab backup/restore on failure)."""
    context.enter_phase(InstallPhase.CONFIGURE)
    request = request or context.request or InstallRequest.from_state(context.state)
    # Transactional guard: backup fstab so partial writes don't leave unbootable target
    fstab_backup: bytes | None = None
    fstab_path: Path | None = None
    try:
        etc = find_deploy_etc(config_root)
        if not etc:
            raise RuntimeError("Installed deployment could not be located for final configuration.")
        fstab_path = Path(etc) / "fstab"
        try:
            fstab_backup = fstab_path.read_bytes() if fstab_path.is_file() else None
        except OSError:
            fstab_backup = None
        if install_mode == "alongside":
            configure_alongside_fstab(config_root, target_part, etc, log)
        if install_mode == "manual":
            configure_manual_mounts(config_root, etc, log, context)

        configure_hostname_timezone(etc, request, log)
        progress(95)
        deploy_root = str(Path(etc).parent)
        ensure_system_accounts(deploy_root, log)

        username = request.username.strip()
        if username and request.password_hash:
            create_installer_user(
                config_root, deploy_root, username, request.password_hash, log, progress,
            )

        checks = validate_installed_target(Path(etc), request)
        context.assurance_checks.extend(check.as_dict() for check in checks)
        for check in checks:
            log(f"Final check [{check.status}]: {check.name} — {check.detail}")
        try:
            persist_artifacts(log, context)
        except Exception as exc:
            log(f"Warning: could not persist success artifacts: {exc}")
    except Exception:
        # Rollback fstab on any failure before unmount — prevents unbootable partial write
        if fstab_path is not None:
            try:
                if fstab_backup is None:
                    if fstab_path.is_file():
                        fstab_path.unlink()
                else:
                    fstab_path.write_bytes(fstab_backup)
                log("Rolled back fstab to pre-configure state due to error")
            except OSError as rb_exc:
                log(f"Warning: fstab rollback failed: {rb_exc}")
        raise
    finally:
        progress(99)
        unmount_configuration(config_root, alongside_mount, run=run_command)
        if alongside_mount:
            for mountpoint in list(context.cleanup_mounts):
                if mountpoint == alongside_mount or mountpoint.startswith(f"{alongside_mount}/"):
                    context.release_mount(mountpoint)
        else:
            context.release_mount(config_root)
