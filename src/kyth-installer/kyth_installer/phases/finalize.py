"""Filesystem finalization (fstab, hostname, user) — Phase 2 verbatim."""
from __future__ import annotations

import json
import os
import shutil
import subprocess  # pylint: disable=unused-import
import traceback
from pathlib import Path

from ..context import InstallRequest, InstallerContext, InstallLifecycle
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
from .finalize_artifacts import persist_artifacts, persist_failure_message
from .finalize_configure import configure_installed_system
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
        if shutil.which("kyth-installer-exec"):
            result = run_command(
                _as_root(["kyth-installer-exec", "--operation", "uuid-probe"]),
                input=json.dumps({"device": part}, separators=(",", ":")),
                capture_output=True, text=True, check=True, timeout=timeout,
            )
            uuid_out = json.loads(result.stdout).get("uuid", "").strip()
            if not uuid_out:
                log(f"Warning: native UUID probe returned no UUID for {part}")
                return None
            return uuid_out
        result = run_command(
            ["blkid", "-s", "UUID", "-o", "value", part],
            capture_output=True, text=True, check=True, timeout=timeout,
        )
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
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
    if shutil.which("kyth-installer-exec"):
        run_command = phase_dependency("run_command")
        as_root = phase_dependency("_as_root")
        try:
            run_command(
                as_root(["kyth-installer-exec", "--operation", "fstab-append"]),
                input=json.dumps({
                    "path": str(Path(etc, "fstab")),
                    "line": fstab_line,
                }, separators=(",", ":")),
                text=True,
                stdout=subprocess.DEVNULL,
                check=True,
                timeout=30,
            )
        except OSError as exc:
            log(f"Warning: failed to update fstab for {description}: {format_os_error(exc, path=Path(etc, 'fstab'))}")
            return False
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
            log(f"Warning: failed to update fstab for {description}: {exc}")
            return False
        log(f"Fstab updated for {description}: {fstab_line.strip()}")
        return True
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
    del dest_name  # retained for API compatibility
    sources = [LOG_FILE, TRANSACTION_FILE]
    if FAILURE_SUMMARY_FILE.is_file():
        sources.append(FAILURE_SUMMARY_FILE)
    persist_artifacts(
        log, context, sources, run_command=run_command, as_root=_as_root,
    )


def _configure_installed_system(
    root_part, target_part, disk, kernel, install_mode, config_root, alongside_mount, log, progress,
    context: InstallerContext, request: InstallRequest | None = None,
):
    run_command = phase_dependency("run_command")
    find_deploy_etc = phase_dependency("find_deploy_etc")
    ensure_system_accounts = phase_dependency("ensure_system_accounts")
    configure_installed_system(
        target_part=target_part, install_mode=install_mode, config_root=config_root,
        alongside_mount=alongside_mount, log=log, progress=progress, context=context,
        request=request, find_deploy_etc=find_deploy_etc,
        ensure_system_accounts=ensure_system_accounts,
        configure_alongside_fstab=_configure_alongside_fstab,
        configure_manual_mounts=_configure_manual_mounts,
        configure_hostname_timezone=_configure_hostname_timezone,
        create_installer_user=_create_installer_user,
        validate_installed_target=validate_installed_target,
        persist_artifacts=_persist_artifacts_to_target,
        unmount_configuration=unmount_configuration, run_command=run_command,
    )

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
    persist_failure_message(
        log, context, message, persist=_persist_artifacts_to_target,
        run_command=run_command, as_root=_as_root,
    )


def _handle_install_failure(exc: Exception, log, context: InstallerContext) -> None:
    """Log, record, and publish an install failure. Runs inside
    _run_install_worker's except block, so a failure in any step here must
    not prevent the error event from reaching the UI — hence the nested
    try/excepts around the log write and failure-summary write."""
    message = format_install_error(exc)
    try:
        fd = os.open(str(LOG_FILE), os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, traceback.format_exc().encode("utf-8", errors="replace"))
            os.write(fd, f"\n# install error: {message}\n".encode("utf-8", errors="replace"))
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as log_exc:
        message = (
            f"{message} "
            f"(also failed writing installer log {LOG_FILE}: "
            f"{format_os_error(log_exc, path=LOG_FILE)})"
        )
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as log_exc:  # noqa: BLE001 -- narrow: best-effort production path
        message = f"{message} (also failed writing installer log {LOG_FILE}: {log_exc})"
    log(f"ERROR: {message}")
    context.transition(InstallLifecycle.FAILED)
    _record_transaction(context, "failed", message=message, log=log)
    try:
        write_failure_summary(FAILURE_SUMMARY_FILE, context=context, message=message)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as summary_exc:  # noqa: BLE001 -- narrow: best-effort production path
        log(f"Warning: could not write failure summary: {summary_exc}")
    try:
        _persist_failure_to_target_disk(log, context, message)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as persist_exc:  # noqa: BLE001 -- narrow: best-effort production path
        log(f"Warning: could not persist failure to target disk: {persist_exc}")
    _push({"type": "error", "message": message}, context)
