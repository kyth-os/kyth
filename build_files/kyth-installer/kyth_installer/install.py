"""Install orchestration for an explicit installer runtime context."""

import os
import re
import shutil
import subprocess
import traceback
from pathlib import Path

from .assurance import run_preflight, validate_installed_target
from .config import FAILURE_SUMMARY_FILE, LOG_FILE, SKIP_FETCH_CHECK, TRANSACTION_FILE
from .cleanup import clear_secrets_and_orphan_mount, unmount_configuration
from .context import InstallLifecycle, InstallRequest, InstallerContext, InstallPhase
from .disk import get_root_partition
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

def _push(event: dict, context: InstallerContext) -> None:
    context.events.publish(event)


def _record_transaction(
    context: InstallerContext,
    status: str,
    *,
    message: str = "",
    log=None,
) -> None:
    try:
        write_transaction_state(
            TRANSACTION_FILE,
            context=context,
            status=status,
            message=message,
        )
    except Exception as exc:
        if log is not None:
            log(f"Warning: could not update installer transaction report: {exc}")


def _build_bootc_install_cmd(
    subcmd: str,
    src_ref: str,
    tgt_ref: str,
    target: str,
    extra_flags: list[str] | None = None,
) -> list[str]:
    cmd: list[str] = [
        "bootc", "install", subcmd,
        "--source-imgref", src_ref,
        "--target-imgref", tgt_ref,
    ]
    # --acknowledge-destructive only exists on `to-filesystem` (it silences the
    # warning when the target is the running system's root). `to-disk` has no
    # such flag at all — bootc rejects it with "unexpected argument" — and
    # relies solely on --wipe to confirm the destructive intent.
    if subcmd == "to-filesystem":
        cmd.append("--acknowledge-destructive")
    if extra_flags:
        cmd.extend(extra_flags)
    if SKIP_FETCH_CHECK and "--skip-fetch-check" not in cmd:
        cmd.append("--skip-fetch-check")
    cmd.append(target)
    return cmd


def _run_cmd(
    cmd: list[str],
    pct_start: int,
    pct_end: int,
    log,
    progress,
    stall_timeout: int = 600,
    absolute_timeout: int | None = 3600,
    publish=None,
) -> None:
    full_cmd = _as_root(cmd)
    def error_factory(returncode: int, recent_output: list[str], argv: list[str]) -> Exception:
        lowered = "\n".join(recent_output).lower()
        network_tokens = (
            "network is unreachable",
            "no route to host",
            "temporary failure in name resolution",
            "name or service not known",
            "could not resolve",
            "connection timed out",
            "i/o timeout",
            "tls handshake timeout",
            "connection reset",
            "connection refused",
        )
        if any(token in lowered for token in network_tokens):
            return RuntimeError(
                _friendly_network_error(
                    "The image download lost network access before it finished."
                )
            )
        detail = "\n".join(recent_output[-10:]) or "No command output was captured."
        return RuntimeError(
            f"Command failed (exit {returncode}):\n  {' '.join(argv)}\n\n{detail}"
        )

    StreamingCommandRunner(
        rx_bytes=get_rx_bytes,
        publish=publish or (lambda _event: None),
    ).run(
        full_cmd,
        pct_start,
        pct_end,
        log,
        progress,
        stall_timeout=stall_timeout,
        absolute_timeout=absolute_timeout,
        error_factory=error_factory,
    )

def _prepare_install_context(log, context: InstallerContext) -> ResolvedInstallPlan:
    context.enter_phase(InstallPhase.PREPARE)
    request = context.request or InstallRequest.from_state(context.state)
    kernel = request.kernel
    src_ref, tgt_ref = _install_images(kernel)
    source = resolve_source_refs(src_ref, tgt_ref)
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
    storage_plan = _prepare_install_plan(request, log, context)

    # Revalidate the effective target immediately before execution. Guided
    # free-space/NTFS plans resolve to an alongside target without rewriting
    # the original request object.
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


def _prepare_storage_for_plan(
    plan: ResolvedInstallPlan,
    log,
    progress,
    alongside_mount: str,
    context: InstallerContext,
):
    """Execute storage preparation from a resolved immutable plan."""
    return _prepare_install_storage(
        plan.disk,
        plan.mode,
        plan.source_ref,
        plan.target_ref,
        log,
        progress,
        alongside_mount,
        context,
        target_partition=plan.target_partition,
        efi_partition=plan.efi_partition,
    )

def _prepare_install_storage(
    disk, install_mode, src_ref, tgt_ref, log, progress, alongside_mount,
    context: InstallerContext,
    *,
    target_partition: str | None = None,
    efi_partition: str | None = None,
):
    context.enter_phase(InstallPhase.STORAGE)
    if install_mode in ("alongside", "manual"):
        target_part = target_partition if target_partition is not None else context.state.get("target_partition", "")
        efi_part = efi_partition if efi_partition is not None else context.state.get("efi_partition", "")
        alongside_mount = "/var/tmp/kyth-alongside-target"  # noqa: S108 — _require_no_symlink guards this below
        return _prepare_partition_target_storage(
            target_part, efi_part, alongside_mount, src_ref, tgt_ref, log, progress, context
        )
    return _prepare_wipe_disk_storage(disk, src_ref, tgt_ref, log, progress, alongside_mount, context)


def _create_btrfs_subvolumes(target_part, log, progress, context: InstallerContext) -> None:
    """Format `target_part` as btrfs and lay out the @ / @home subvolumes.

    Mounts target_part at a private temp root just long enough to create the
    subvolumes and set @ as default; the temp mount must not outlive this
    function regardless of success or failure, hence the finally.
    """
    log(f"Formatting {target_part} as btrfs ...")
    _run_cmd(
        ["mkfs.btrfs", "-f", "-L", "KythOS", target_part],
        5, 10, log, progress,
        publish=lambda event: _push(event, context),
    )

    log("Creating Btrfs subvolumes @ and @home ...")
    btrfs_temp_root = "/var/tmp/kyth-btrfs-root"  # noqa: S108 — _require_no_symlink guards this below
    _safe_umount(run_command, btrfs_temp_root)
    _require_no_symlink(btrfs_temp_root)
    run_command(_as_root(["mkdir", "-p", btrfs_temp_root]), check=True)
    context.register_mount(btrfs_temp_root)
    run_command(_as_root(["mount", target_part, btrfs_temp_root]), check=True)
    try:
        run_command(_as_root(["btrfs", "subvolume", "create", f"{btrfs_temp_root}/@"]), check=True)
        run_command(_as_root(["btrfs", "subvolume", "create", f"{btrfs_temp_root}/@home"]), check=True)
        log("Setting Btrfs default subvolume to @ ...")
        run_command(_as_root(["btrfs", "subvolume", "set-default", f"{btrfs_temp_root}/@"]), check=True)
    finally:
        _safe_umount(run_command, btrfs_temp_root, check=True)
        context.release_mount(btrfs_temp_root)


def _mount_efi_for_alongside(alongside_mount, efi_part, log, context: InstallerContext) -> None:
    """Mount efi_part under alongside_mount/boot/efi.

    Bind-mounts from efi_part's current mountpoint when the live session
    already has it mounted (e.g. /boot/efi), rather than mounting the device
    a second time.
    """
    efi_mountpoint = Path(alongside_mount) / "boot" / "efi"
    run_command(_as_root(["mkdir", "-p", str(efi_mountpoint)]), check=True)
    context.register_mount(str(efi_mountpoint))
    try:
        result = run_command(
            ["findmnt", "-n", "-o", "MOUNTPOINT", efi_part],
            capture_output=True, text=True, check=True, timeout=5,
        )
        current_efi_mnt = result.stdout.strip()
    except Exception:
        current_efi_mnt = ""
    if current_efi_mnt:
        run_command(
            _as_root(["mount", "--bind", current_efi_mnt, str(efi_mountpoint)]),
            check=True,
        )
        log(f"EFI bind-mounted from {current_efi_mnt}")
    else:
        run_command(
            _as_root(["mount", efi_part, str(efi_mountpoint)]),
            check=True,
        )
        log(f"EFI mounted from {efi_part}")


def _snapshot_efi_boot_entries(log) -> str:
    """Best-effort capture of 'efibootmgr -v' output for later comparison.

    Returns "" (never raises) when efibootmgr is unavailable — legacy BIOS
    boot, a container test environment, or a live session with no UEFI
    firmware access — since this is a diagnostic safety net, not a
    requirement the install should ever fail on.
    """
    if shutil.which("efibootmgr") is None:
        return ""
    try:
        result = run_command(_as_root(["efibootmgr", "-v"]), capture_output=True, text=True, timeout=10)
        return result.stdout if result.returncode == 0 else ""
    except Exception:
        return ""


_EFI_BOOT_ENTRY_RE = re.compile(r"^Boot[0-9A-Fa-f]{4}\*?\s+(.+)$")


def _warn_if_efi_boot_entries_disappeared(before: str, after: str, log) -> None:
    """Warn (never raise) if a named EFI boot entry present before the
    install — e.g. "Windows Boot Manager" — is gone from NVRAM afterward.

    bootc's bootupd step registers KythOS's own boot entry and can rewrite
    BootOrder; this is the safety net for it silently dropping another OS's
    entry rather than just reordering it. The other OS's files/bootloader on
    disk are untouched either way — only the firmware's menu entry is at risk.
    """
    if not before or not after:
        return

    def entry_labels(text: str) -> set[str]:
        labels = set()
        for line in text.splitlines():
            match = _EFI_BOOT_ENTRY_RE.match(line)
            if match:
                labels.add(match.group(1).strip())
        return labels

    lost = entry_labels(before) - entry_labels(after)
    if lost:
        log(
            "Warning: these EFI boot entries were present before the install "
            f"but are missing from firmware NVRAM afterward: {', '.join(sorted(lost))}. "
            "The other OS on disk is unaffected — only its boot menu entry may "
            "be gone. Use your firmware's boot menu (often F12/Esc at power-on) "
            "or 'efibootmgr' to recreate the entry if needed."
        )


def _prepare_partition_target_storage(
    target_part, efi_part, alongside_mount, src_ref, tgt_ref, log, progress,
    context: InstallerContext,
):
    """Storage prep for the alongside/manual install modes: format the
    user-selected target partition as btrfs, lay out @ / @home subvolumes,
    mount it (plus EFI if present) under alongside_mount, then write the OS
    image into that mountpoint via `bootc install to-filesystem`.
    """
    log(f"Target partition : {target_part}")
    log(f"EFI partition    : {efi_part or '(none detected)'}")

    _safe_umount(run_command, target_part)
    run_command(_as_root(["umount", "-Rl", alongside_mount]), check=False, capture_output=True)

    _create_btrfs_subvolumes(target_part, log, progress, context)

    _require_no_symlink(alongside_mount)
    run_command(_as_root(["mkdir", "-p", alongside_mount]), check=True)
    context.register_mount(alongside_mount)
    run_command(_as_root(["mount", "-o", "subvol=@", target_part, alongside_mount]), check=True)
    progress(11)

    if efi_part:
        _mount_efi_for_alongside(alongside_mount, efi_part, log, context)

    install_cmd = _build_bootc_install_cmd(
        "to-filesystem", src_ref, tgt_ref, alongside_mount,
        # --skip-fetch-check unconditionally here (not gated behind the
        # SKIP_FETCH_CHECK env toggle, which controls the unrelated
        # network-preflight check below): this target mountpoint already
        # has other partitions (e.g. a bind-mounted /boot/efi) mounted
        # under it, which is exactly the case the partition CLI exercises.
        # See plan.py's install_mode
        # docstring for the "alongside" mode.
        extra_flags=["--skip-finalize", "--karg=rootflags=subvol=@", "--skip-fetch-check"],
    )
    efi_before = _snapshot_efi_boot_entries(log)
    context.enter_phase(InstallPhase.IMAGE)
    _run_cmd(
        install_cmd, 12, 90, log, progress,
        stall_timeout=3600, absolute_timeout=None,
        publish=lambda event: _push(event, context),
    )
    _warn_if_efi_boot_entries_disappeared(efi_before, _snapshot_efi_boot_entries(log), log)

    return target_part, target_part, alongside_mount


def _prepare_wipe_disk_storage(disk, src_ref, tgt_ref, log, progress, alongside_mount, context: InstallerContext):
    """Storage prep for the wipe install mode: unmount anything blocking the
    disk, then write the OS image via `bootc install to-disk`.
    """
    unmount_target_disk(disk, log)
    install_cmd = _build_bootc_install_cmd(
        "to-disk", src_ref, tgt_ref, disk,
        extra_flags=["--filesystem", "btrfs", "--wipe"],
    )
    context.enter_phase(InstallPhase.IMAGE)
    _run_cmd(
        install_cmd, 5, 90, log, progress,
        stall_timeout=3600, absolute_timeout=None,
        publish=lambda event: _push(event, context),
    )
    return "", get_root_partition(disk), alongside_mount

def _configure_alongside_fstab(config_root, target_part, etc, log) -> None:
    """Mount the alongside-install target's @home subvolume under the ostree
    deploy root and wire it into the target system's fstab."""
    target_home = Path(config_root) / "ostree/deploy/default/var/home"
    run_command(_as_root(["mkdir", "-p", str(target_home)]), check=True)
    _safe_umount(run_command, str(target_home))
    run_command(_as_root(["mount", "-o", "subvol=@home", target_part, str(target_home)]), check=True)

    try:
        result = run_command(
            ["blkid", "-s", "UUID", "-o", "value", target_part],
            capture_output=True, text=True, check=True,
        )
        uuid_out = result.stdout.strip()
        if uuid_out:
            fstab_path = Path(etc, "fstab")
            fstab_line = f"UUID={uuid_out} /var/home btrfs subvol=@home,compress=zstd:1 0 0\n"
            run_command(
                _as_root(["/usr/bin/tee", "-a", str(fstab_path)]),
                input=fstab_line, text=True,
                stdout=subprocess.DEVNULL, check=True
            )
            log(f"Fstab updated with Btrfs subvolume @home: {fstab_line.strip()}")
    except OSError as fe:
        log(
            "Warning: failed to update fstab with @home subvolume: "
            f"{format_os_error(fe, path=Path(etc, 'fstab'))}"
        )
    except Exception as fe:
        log(f"Warning: failed to update fstab with @home subvolume: {fe}")


def _configure_manual_mounts(config_root, etc, log, context: InstallerContext) -> None:
    """Mount each manually-configured partition under the ostree deploy root
    and add a matching fstab entry (mapping /home to /var/home)."""
    manual_mounts = _get_manual_mounts(context)
    for mnt in manual_mounts:
        part = mnt["partition"]
        mp = mnt["mountpoint"]
        fs = mnt["fstype"]
        try:
            result = run_command(
                ["blkid", "-s", "UUID", "-o", "value", part],
                capture_output=True, text=True, check=True, timeout=5,
            )
            uuid_out = result.stdout.strip()
            if not uuid_out:
                log(f"Warning: could not get UUID for {part}, skipping fstab entry for {mp}")
                continue
            # Map /home to /var/home in ostree layout
            fstab_mp = "/var/home" if mp == "/home" else mp
            target_path = Path(config_root) / fstab_mp.lstrip("/")
            if fs == "linux-swap":
                fstab_line = f"UUID={uuid_out} none swap defaults 0 0\n"
            else:
                mount_options = "defaults,compress=zstd:1" if fs == "btrfs" else "defaults"
                fstab_line = f"UUID={uuid_out} {fstab_mp} {fs} {mount_options} 0 2\n"
                run_command(
                    _as_root(["mkdir", "-p", str(target_path)]),
                    check=False,
                )
                # Unmount any existing mount at this path (e.g. @home subvolume)
                _safe_umount(run_command, str(target_path))
            run_command(
                _as_root(["/usr/bin/tee", "-a", str(Path(etc, "fstab"))]),
                input=fstab_line, text=True,
                stdout=subprocess.DEVNULL, check=True,
            )
            if fs != "linux-swap":
                run_command(
                    _as_root(["mount", part, str(target_path)]),
                    check=False,
                )
            log(f"Manual mount: {part} at {mp} ({fs})")
        except Exception as me:
            log(f"Warning: failed to configure manual mount {part} at {mp}: {me}")


def _configure_hostname_timezone(etc, state, log) -> None:
    hostname_path = str(Path(etc, "hostname"))
    try:
        run_command(
            _as_root(["/usr/bin/tee", hostname_path]),
            input=f"{state['hostname']}\n", text=True,
            stdout=subprocess.DEVNULL, check=True,
        )
    except OSError as exc:
        raise OSError(format_os_error(exc, path=hostname_path)) from exc
    log(f"Hostname : {state['hostname']}")

    localtime_path = str(Path(etc, "localtime"))
    try:
        run_command(
            _as_root(["ln", "-snf",
                      f"/usr/share/zoneinfo/{state['timezone']}",
                      localtime_path]),
            check=True,
        )
    except OSError as exc:
        raise OSError(format_os_error(exc, path=localtime_path)) from exc
    log(f"Timezone : {state['timezone']}")

    locale_path = str(Path(etc, "locale.conf"))
    run_command(
        _as_root(["/usr/bin/tee", locale_path]),
        input=f"LANG={state.get('locale', 'en_US.UTF-8')}\n", text=True,
        stdout=subprocess.DEVNULL, check=True,
    )
    vconsole_path = str(Path(etc, "vconsole.conf"))
    run_command(
        _as_root(["/usr/bin/tee", vconsole_path]),
        input=f"KEYMAP={state.get('keymap', 'us')}\n", text=True,
        stdout=subprocess.DEVNULL, check=True,
    )
    log(f"Locale   : {state.get('locale', 'en_US.UTF-8')}")
    log(f"Keyboard : {state.get('keymap', 'us')}")


def _create_installer_user(config_root, deploy_root, username, password_hash, log, progress) -> None:
    log(f"Creating user: {username}")
    try:
        _shared_create_installer_user(
            deploy_root, config_root, username, password_hash, log,
            run=lambda argv, **kw: run_command(_as_root(argv), **kw),
        )
        # Re-lock /etc/shadow now that this user's entry exists in it.
        ensure_system_accounts(deploy_root, log)
        progress(97)
    except OSError as ue:
        log(
            "Warning: user creation failed: "
            f"{format_os_error(ue)}"
        )
        log("You can create a user after first boot with: sudo useradd -m -G wheel USERNAME")
    except Exception as ue:
        log(f"Warning: user creation failed: {ue}")
        log("You can create a user after first boot with: sudo useradd -m -G wheel USERNAME")


def _configure_installed_system(
    root_part, target_part, disk, kernel, install_mode, config_root, alongside_mount, log, progress,
    context: InstallerContext, request: InstallRequest | None = None,
):
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
    finally:
        progress(99)
        unmount_configuration(config_root, alongside_mount, run=run_command)
        if alongside_mount:
            for mountpoint in list(context.cleanup_mounts):
                if mountpoint == alongside_mount or mountpoint.startswith(f"{alongside_mount}/"):
                    context.release_mount(mountpoint)
        else:
            context.release_mount(config_root)

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
    _push({"type": "error", "message": message}, context)


def _run_install_worker(
    log, progress, alongside_mount, context: InstallerContext,
):
    # The execution service owns these transitions in production. Keeping the
    # worker independently invokable also supports the partition CLI and
    # focused phase tests without weakening transition validation.
    if context.lifecycle is InstallLifecycle.IDLE:
        context.transition(InstallLifecycle.VALIDATED)
        context.transition(InstallLifecycle.INSTALLING)
    request = context.request or InstallRequest.from_state(context.state)
    try:
        require_root()
        resolved = _prepare_install_context(log, context)

        target_part, root_part, alongside_mount = _prepare_storage_for_plan(
            resolved, log, progress, alongside_mount, context
        )
        _record_transaction(context, "image_installed", log=log)

        log("── Phase 2: Configuring installed system ─────────────────────────")
        progress(91)

        if alongside_mount:
            config_root = alongside_mount
        else:
            config_root = "/var/tmp/kyth-install-root"  # noqa: S108 — _require_no_symlink guards this below
            _require_no_symlink(config_root)
            run_command(_as_root(["mkdir", "-p", config_root]), check=True)
            # Detach any stale mount left by a previously crashed install attempt.
            _safe_umount(run_command, config_root)
            context.register_mount(config_root)
            run_command(_as_root(["mount", root_part, config_root]), check=True)

        progress(93)

        _configure_installed_system(
            root_part, target_part, resolved.disk, resolved.kernel, resolved.mode,
            config_root, alongside_mount, log, progress, context, resolved.request,
        )

        log("── Phase 3: Staging Secure Boot enrollment ───────────────────────")
        context.enter_phase(InstallPhase.SECURE_BOOT)
        mok_state = _try_stage_mok_enrollment(log, resolved.kernel, resolved.request.mok_password)

        progress(100)
        context.enter_phase(InstallPhase.COMPLETE)
        context.transition(InstallLifecycle.DONE)
        _record_transaction(context, "complete", log=log)
        _push({"type": "done", "mok_state": mok_state}, context)

    except Exception as exc:
        _handle_install_failure(exc, log, context)
    finally:
        # Guard against orphaned mounts when Phase 1 fails before the inner
        # try/finally (which holds the normal umount) is ever entered.
        clear_secrets_and_orphan_mount(context.state, alongside_mount, run=run_command)
        context.clear_secrets()
        cleanup_registered_mounts(context, run=run_command)

def _run_install(context: InstallerContext) -> None:
    context.events.clear()

    def log(msg: str) -> None:
        _push({"type": "log", "text": msg}, context)
        try:
            with LOG_FILE.open("a") as f:
                f.write(msg + "\n")
        except OSError as exc:
            # Still surface progress over SSE even if the log file is unusable.
            _push({
                "type": "log",
                "text": (
                    f"(installer log write failed for {LOG_FILE}: "
                    f"{format_os_error(exc, path=LOG_FILE)})"
                ),
            }, context)

    def progress(pct: int) -> None:
        _push({"type": "progress", "value": pct}, context)

    try:
        require_root()
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        # LOG_FILE sits under the world-writable /tmp by default — remove
        # whatever's there first (unlink doesn't follow a symlink, it just
        # drops the link itself), then create fresh with O_EXCL | O_NOFOLLOW
        # so a symlink raced back in between the two calls makes this fail
        # loudly instead of writing through it as root. /tmp's sticky bit
        # protects the file for the rest of the run once this succeeds.
        LOG_FILE.unlink(missing_ok=True)
        fd = os.open(str(LOG_FILE), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        _record_transaction(context, "started")
    except Exception as exc:
        message = format_install_error(exc)
        context.transition(InstallLifecycle.FAILED)
        _push({"type": "error", "message": message}, context)
        return

    alongside_mount = ""

    _run_install_worker(log, progress, alongside_mount, context)
