"""Filesystem finalization (fstab, hostname, user) — Phase 2 verbatim."""
from __future__ import annotations

import subprocess
import traceback
from pathlib import Path

from ..context import InstallRequest, InstallerContext, InstallLifecycle, InstallPhase
from ..assurance import validate_installed_target
from ..cleanup import unmount_configuration
from ..runner import run_command
from ..system import _as_root, ensure_system_accounts, find_deploy_etc, format_install_error, format_os_error  # pylint: disable=unused-import
from kyth_shared.accounts import create_installer_user as _shared_create_installer_user
from .common import _push, _record_transaction
from .compat import phase_dependency
from .finalize_identity import configure_hostname_timezone, create_installer_user
from .finalize_fstab import (
    append_fstab_line,
    configure_alongside_fstab,
    configure_manual_mounts,
    fsck_pass_for,
)
from ..recovery import write_failure_summary
from ..config import FAILURE_SUMMARY_FILE, LOG_FILE, TRANSACTION_FILE

def _blkid_uuid(part: str, log, *, timeout: float = 5) -> str | None:
    """Look up a partition's filesystem UUID via blkid, for building an
    fstab entry. Returns None (after logging a warning) on any failure —
    callers should skip that fstab entry rather than write one with a
    blank UUID. Shared by every fstab-writing path so they see the same
    lookup behavior (same timeout, same failure handling) instead of each
    reimplementing it slightly differently."""
    run_command = phase_dependency("run_command")
    try:
        result = run_command(
            ["blkid", "-s", "UUID", "-o", "value", part],
            capture_output=True, text=True, check=True, timeout=timeout,
        )
    except Exception as exc:
        log(f"Warning: could not read UUID for {part}: {exc}")
        return None
    uuid_out = result.stdout.strip()
    if not uuid_out:
        log(f"Warning: blkid returned no UUID for {part}")
        return None
    return uuid_out


def _fsck_pass_for(fstype: str) -> int:
    return fsck_pass_for(fstype)


def _append_fstab_line(etc, fstab_line: str, log, description: str) -> bool:
    return append_fstab_line(
        etc, fstab_line, log, description, format_error=format_os_error,
    )


def _configure_alongside_fstab(config_root, target_part, etc, log) -> None:
    configure_alongside_fstab(
        config_root, target_part, etc, log,
        uuid_lookup=_blkid_uuid, append_line=_append_fstab_line,
    )


def _configure_manual_mounts(config_root, etc, log, context: InstallerContext) -> None:
    configure_manual_mounts(
        config_root, etc, log, context,
        uuid_lookup=_blkid_uuid, append_line=_append_fstab_line,
    )


def _configure_hostname_timezone(etc, state, log) -> None:
    configure_hostname_timezone(etc, state, log, format_error=format_os_error)


def _create_installer_user(config_root, deploy_root, username, password_hash, log, progress) -> None:
    create_installer_user(
        config_root, deploy_root, username, password_hash, log, progress,
        creator=_shared_create_installer_user,
        ensure_accounts=phase_dependency("ensure_system_accounts"),
        format_error=format_os_error,
    )


def _persist_artifacts_to_target(
    log, context: InstallerContext, dest_name: str = "install-log"
) -> None:
    """Best-effort mirror of log/tx into the mounted target for persistence."""
    candidates: list[str] = []
    try:
        candidates.extend(list(getattr(context, "cleanup_mounts", []) or []))
    except Exception:  # nosec B110 -- best-effort, failure here is non-fatal by design
        pass
    for p in ("/var/tmp/kyth-alongside-target", "/var/tmp/kyth-install-root"):  # nosec B108 -- installer-owned bind-mount targets in the single-user live-ISO session, not a shared multi-user /tmp
        if p not in candidates:
            candidates.append(p)

    vol_sources = [LOG_FILE, TRANSACTION_FILE]
    # Only add failure summary if it exists (success path won't have it yet)
    if FAILURE_SUMMARY_FILE.is_file():
        vol_sources.append(FAILURE_SUMMARY_FILE)

    for mnt in candidates:
        try:
            import os as _os

            if not mnt or not _os.path.isdir(mnt):
                continue
            try:
                result = run_command(["findmnt", "-n", mnt], capture_output=True, timeout=3)
                if result.returncode != 0:
                    continue
            except Exception:
                pass

            dest_dir = Path(mnt) / "var" / "log" / "kyth-installer"
            try:
                run_command(_as_root(["mkdir", "-p", str(dest_dir)]), check=False)
                for src in vol_sources:
                    if src.is_file() and not src.is_symlink():
                        # For success, copy log as 'install.log' alongside existing names
                        run_command(
                            _as_root(["cp", "-a", str(src), str(dest_dir / src.name)]),
                            check=False,
                        )
                log(f"Installer artifacts persisted to {dest_dir} on the target disk.")
                break
            except Exception as exc:
                log(f"Warning: could not persist artifacts to {mnt}: {exc}")
        except Exception:  # nosec B112 -- best-effort per-item skip, failure here is non-fatal by design
            continue


def _configure_installed_system(
    root_part, target_part, disk, kernel, install_mode, config_root, alongside_mount, log, progress,
    context: InstallerContext, request: InstallRequest | None = None,
):
    run_command = phase_dependency("run_command")
    find_deploy_etc = phase_dependency("find_deploy_etc")
    ensure_system_accounts = phase_dependency("ensure_system_accounts")
    context.enter_phase(InstallPhase.CONFIGURE)
    request = request or context.request or InstallRequest.from_state(context.state)
    try:
        etc = find_deploy_etc(config_root)
        if not etc:
            raise RuntimeError("Installed deployment could not be located for final configuration.")
        if install_mode == "alongside":
            _configure_alongside_fstab(config_root, target_part, etc, log)

        # Manual partition mode: mount additional partitions and update fstab
        if install_mode == "manual":
            _configure_manual_mounts(config_root, etc, log, context)

        _configure_hostname_timezone(etc, request, log)
        progress(95)

        deploy_root = str(Path(etc).parent)
        ensure_system_accounts(deploy_root, log)

        username = request.username.strip()
        password_hash = request.password_hash
        if username and password_hash:
            _create_installer_user(config_root, deploy_root, username, password_hash, log, progress)

        checks = validate_installed_target(Path(etc), request)
        context.assurance_checks.extend(check.as_dict() for check in checks)
        for check in checks:
            log(f"Final check [{check.status}]: {check.name} — {check.detail}")
        # Persist success artifacts too — /run is tmpfs, so without this a
        # successful install leaves no post-mortem if the next boot fails.
        try:
            _persist_artifacts_to_target(log, context)
        except Exception as exc:
            log(f"Warning: could not persist success artifacts: {exc}")
    finally:
        progress(99)
        unmount_configuration(config_root, alongside_mount, run=run_command)
        if alongside_mount:
            for mountpoint in list(context.cleanup_mounts):
                if mountpoint == alongside_mount or mountpoint.startswith(f"{alongside_mount}/"):
                    context.release_mount(mountpoint)
        else:
            context.release_mount(config_root)

def _persist_failure_to_target_disk(log, context: InstallerContext, message: str) -> None:
    """Best-effort mirror of installer log + failure summary onto the target disk.

    ``/run/kyth-installer`` lives on tmpfs, so a power loss after the image
    write erases the only post-mortem artifact that covers release gate #7.
    If the target filesystem is already mounted (IMAGE/CONFIGURE phases have
    created it and registered it in ``context.cleanup_mounts``), copy the
    volatile artifacts into ``$mount/var/log/kyth-installer/`` so they survive
    a reboot or power cycle. Failures before any target mount exist have
    nothing to persist — the volatile /run copy is the only one.
    """
    # Reuse shared persist, then add the human-readable failure.txt
    _persist_artifacts_to_target(log, context)
    # Also write install-failure.txt with the human message for easy cat
    candidates: list[str] = []
    try:
        candidates.extend(list(getattr(context, "cleanup_mounts", []) or []))
    except Exception:
        pass
    for p in ("/var/tmp/kyth-alongside-target", "/var/tmp/kyth-install-root"):  # nosec B108 -- installer-owned bind-mount targets in the single-user live-ISO session, not a shared multi-user /tmp
        if p not in candidates:
            candidates.append(p)

    for mnt in candidates:
        try:
            import os as _os

            if not mnt or not _os.path.isdir(mnt):
                continue
            try:
                result = run_command(["findmnt", "-n", mnt], capture_output=True, timeout=3)
                if result.returncode != 0:
                    continue
            except Exception:
                pass

            dest_dir = Path(mnt) / "var" / "log" / "kyth-installer"
            try:
                txt = dest_dir / "install-failure.txt"
                run_command(
                    _as_root(["/usr/bin/tee", str(txt)]),
                    input=f"{message}\n\nSee also: {dest_dir}/failure.json\n",
                    text=True, stdout=subprocess.DEVNULL, check=False,
                )
                break
            except Exception:
                pass
        except Exception:
            continue


def _handle_install_failure(exc: Exception, log, context: InstallerContext) -> None:
    """Log, record, and publish an install failure. Runs inside
    _run_install_worker's except block, so a failure in any step here must
    not prevent the error event from reaching the UI — hence the nested
    try/excepts around the log write and failure-summary write."""
    message = format_install_error(exc)
    try:
        with LOG_FILE.open("a") as f:
            f.write(traceback.format_exc())
            f.write(f"\n# install error: {message}\n")
    except OSError as log_exc:
        message = (
            f"{message} "
            f"(also failed writing installer log {LOG_FILE}: "
            f"{format_os_error(log_exc, path=LOG_FILE)})"
        )
    except Exception as log_exc:
        message = f"{message} (also failed writing installer log {LOG_FILE}: {log_exc})"
    log(f"ERROR: {message}")
    context.transition(InstallLifecycle.FAILED)
    _record_transaction(context, "failed", message=message, log=log)
    try:
        write_failure_summary(FAILURE_SUMMARY_FILE, context=context, message=message)
    except Exception as summary_exc:
        log(f"Warning: could not write failure summary: {summary_exc}")
    try:
        _persist_failure_to_target_disk(log, context, message)
    except Exception as persist_exc:
        log(f"Warning: could not persist failure to target disk: {persist_exc}")
    _push({"type": "error", "message": message}, context)
