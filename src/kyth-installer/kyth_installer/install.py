"""Install orchestration for an explicit installer runtime context."""

import shutil  # pylint: disable=unused-import
from pathlib import Path  # pylint: disable=unused-import

from .assurance import run_preflight, validate_installed_target  # pylint: disable=unused-import
from .config import SKIP_FETCH_CHECK
from .context import InstallRequest, InstallerContext, InstallPhase
from .disk import get_root_partition  # pylint: disable=unused-import
from .plan import InstallPlan
from .imagesrc import (
    _install_images,
    _network_preflight,
    resolve_source_refs,
)
from .plan import (  # pylint: disable=unused-import
    ResolvedInstallPlan,
    _get_manual_mounts,  # pylint: disable=unused-import
    _prepare_install_plan,
    request_with_install_plan,
    _validate_install_target,
    _validate_storage_intent,
)
from .runner import run_command  # pylint: disable=unused-import  # noqa: F401
from kyth_shared import get_rx_bytes  # pylint: disable=unused-import
from kyth_shared.accounts import create_installer_user as _shared_create_installer_user

from .phases.common import (
    _assert_still_on_ac,
    _record_transaction,
)
from .phases.bootc_cmd import _build_bootc_install_cmd, _run_cmd  # pylint: disable=unused-import
from .system import (  # pylint: disable=unused-import
    _as_root,  # pylint: disable=unused-import
    _require_no_symlink,  # pylint: disable=unused-import
    _safe_umount,  # pylint: disable=unused-import
    ensure_directory,  # pylint: disable=unused-import
    mount_filesystem,  # pylint: disable=unused-import
    _try_stage_mok_enrollment,  # pylint: disable=unused-import
    ensure_system_accounts,  # pylint: disable=unused-import
    find_deploy_etc,  # pylint: disable=unused-import
    format_install_error,  # pylint: disable=unused-import
    require_root,  # pylint: disable=unused-import
    unmount_target_disk,  # pylint: disable=unused-import
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
    checks = run_preflight(source, disk=request.disk)
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
    effective_request = request_with_install_plan(request, storage_plan)
    disk, target_partition = _validate_install_target(effective_request, context)
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
from .phases.storage import (  # pylint: disable=unused-import  # noqa: F401
    _prepare_install_storage,  # pylint: disable=unused-import
    _snapshot_efi_boot_entries,  # pylint: disable=unused-import
    _warn_if_efi_boot_entries_disappeared,  # pylint: disable=unused-import
)
from .phases.finalize import (  # pylint: disable=unused-import  # noqa: F401
    _blkid_uuid,  # pylint: disable=unused-import
    _configure_alongside_fstab,  # pylint: disable=unused-import
    _configure_hostname_timezone,  # pylint: disable=unused-import
    _configure_manual_mounts,  # pylint: disable=unused-import
    _fsck_pass_for,  # pylint: disable=unused-import
)
from .phases.run import _run_install, _run_install_worker  # pylint: disable=unused-import  # noqa: F401
