"""Install orchestration for an explicit installer runtime context."""

import os
import re
import shutil
import subprocess
import threading
import traceback
from pathlib import Path
import pathlib

from .assurance import run_preflight, validate_installed_target
from .config import FAILURE_SUMMARY_FILE, LOG_FILE, SKIP_FETCH_CHECK, TRANSACTION_FILE
from .cleanup import clear_secrets_and_orphan_mount, unmount_configuration
from .context import InstallLifecycle, InstallRequest, InstallerContext, InstallPhase
from .disk import get_root_partition
from .plan import InstallPlan
from .imagesrc import (
    _friendly_network_error,
    _install_images,
    _network_preflight,
    resolve_source_refs,
)
from .plan import (
    ResolvedInstallPlan,
    _get_manual_mounts,
    _prepare_install_plan,
    _validate_install_target,
    _validate_storage_intent,
)
from .runner import run_command
from .recovery import cleanup_registered_mounts, write_failure_summary, write_transaction_state
from .streaming import StreamingCommandRunner
from kyth_shared import get_rx_bytes
from kyth_shared.accounts import create_installer_user as _shared_create_installer_user

from .phases.common import (
    _assert_still_on_ac,
    _disk_image_hold,
    _push,
    _record_transaction,
    _start_power_watch,
    _stop_power_watch,
)
from .phases.bootc_cmd import _build_bootc_install_cmd, _run_cmd
from .system import (
    _as_root,
    _require_no_symlink,
    _safe_umount,
    _try_stage_mok_enrollment,
    ensure_system_accounts,
    find_deploy_etc,
    format_install_error,
    format_os_error,
    require_root,
    unmount_target_disk,
)



def _prepare_install_context(log, context: InstallerContext) -> ResolvedInstallPlan:
    from .execution import check_cancelled

    check_cancelled(context)
    context.enter_phase(InstallPhase.PREPARE)
    request = context.request or InstallRequest.from_state(context.state)
    kernel = request.kernel
    src_ref, tgt_ref = _install_images(kernel)
    source = resolve_source_refs(src_ref, tgt_ref)
    if source.digest:
        base = src_ref.split("@", 1)[0]
        if ":" in base and not base.startswith("oci:"):
            src_ref = f"{base}@{source.digest}"
        log(f"Pinned source to digest: {source.digest}")
    _validate_storage_intent(request, context)
    if not SKIP_FETCH_CHECK:
        log("Running network preflight check...")
        net_err = _network_preflight(src_ref)
        if net_err:
            raise RuntimeError(net_err)
    checks = run_preflight(source)
    context.assurance_checks = [check.as_dict() for check in checks]
    for check in checks:
        log(f"Preflight [{check.status}]: {check.name} — {check.detail}")

    _assert_still_on_ac(log)
    storage_plan = _prepare_install_plan(request, log, context)
    resolved = _resolve_and_record_plan(request, storage_plan, src_ref, tgt_ref, source, context, log)

    log(f"Mode         : {resolved.mode}")
    log(f"Kernel       : {kernel}")
    log(f"Source imgref: {src_ref}")
    if source.digest:
        log(f"Source digest: {source.digest}")
    log(f"Source type  : {source.kind}{' (verified)' if source.verified else ''}")
    log(f"Target image : {tgt_ref}")
    log(f"Disk         : {resolved.disk}")
    log("")

    log("── Phase 1: Writing OS image to disk ─────────────────────────────")
    return resolved


def _resolve_and_record_plan(
    request: InstallRequest,
    storage_plan: InstallPlan,
    src_ref: str,
    tgt_ref: str,
    source,
    context: InstallerContext,
    log,
) -> ResolvedInstallPlan:
    effective_state = request.as_state()
    effective_state["install_mode"] = storage_plan.mode
    if storage_plan.disk:
        effective_state["disk"] = storage_plan.disk
    if storage_plan.target_partition:
        effective_state["target_partition"] = storage_plan.target_partition
    disk, target_partition = _validate_install_target(effective_state, context)
    storage_plan = type(storage_plan)(storage_plan.mode, disk=disk, target_partition=target_partition)

    resolved = ResolvedInstallPlan(
        request=request,
        storage=storage_plan,
        source_ref=src_ref,
        target_ref=tgt_ref,
        source_digest=source.digest,
        source_kind=source.kind,
        source_verified=source.verified,
    )
    context.set_plan(resolved)
    _record_transaction(context, "prepared", log=log)
    return resolved


# Phase 2 verbatim — canonical implementations now live in phases/
from .phases.storage import (
    _EFI_BOOT_ENTRY_RE,
    _create_btrfs_subvolumes,
    _mount_efi_for_alongside,
    _prepare_install_storage,
    _prepare_partition_target_storage,
    _prepare_storage_for_plan,
    _prepare_wipe_disk_storage,
    _snapshot_efi_boot_entries,
    _warn_if_efi_boot_entries_disappeared,
)
from .phases.finalize import (
    _append_fstab_line,
    _blkid_uuid,
    _configure_alongside_fstab,
    _configure_hostname_timezone,
    _configure_installed_system,
    _configure_manual_mounts,
    _create_installer_user,
    _fsck_pass_for,
    _handle_install_failure,
)
from .phases.run import _run_install, _run_install_worker

