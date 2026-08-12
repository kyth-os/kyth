"""Storage preparation for install — Phase 2 verbatim from install.py."""
from __future__ import annotations

import pathlib
import re
import shutil
from pathlib import Path

from ..context import InstallerContext, InstallPhase
from ..plan import ResolvedInstallPlan
from ..system import unmount_target_disk  # pylint: disable=unused-import
from .common import _assert_still_on_ac, _disk_image_hold, _push

def _prepare_storage_for_plan(
    plan: ResolvedInstallPlan,
    log,
    progress,
    alongside_mount: str,
    context: InstallerContext,
):
    # Lazy import to respect tests that patch install.*
    """Execute storage preparation from a resolved immutable plan."""
    try:
        from ..install import _as_root, _require_no_symlink, _safe_umount, unmount_target_disk, _run_cmd, _build_bootc_install_cmd  # pylint: disable=unused-import
    except ImportError:
        from ..runner import run_command  # fallback  # pylint: disable=unused-import
        from ..system import _as_root  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import unmount_target_disk  # fallback
        from ..disk import get_root_partition  # fallback  # pylint: disable=unused-import
        from .bootc_cmd import _run_cmd  # fallback
        from .bootc_cmd import _build_bootc_install_cmd  # fallback
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
    # Lazy import to respect tests that patch install.*
    try:
        from ..install import _as_root, _require_no_symlink, _safe_umount, unmount_target_disk, _run_cmd, _build_bootc_install_cmd  # pylint: disable=unused-import
    except ImportError:
        from ..runner import run_command  # fallback  # pylint: disable=unused-import
        from ..system import _as_root  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import unmount_target_disk  # fallback
        from ..disk import get_root_partition  # fallback  # pylint: disable=unused-import
        from .bootc_cmd import _run_cmd  # fallback
        from .bootc_cmd import _build_bootc_install_cmd  # fallback
    from ..execution import check_cancelled

    check_cancelled(context)
    _assert_still_on_ac(log)
    context.enter_phase(InstallPhase.STORAGE)
    if install_mode in ("alongside", "manual"):
        target_part = target_partition if target_partition is not None else context.state.get("target_partition", "")
        efi_part = efi_partition if efi_partition is not None else context.state.get("efi_partition", "")
        from ..config import STAGING_ALONGSIDE_MOUNT
        alongside_mount = STAGING_ALONGSIDE_MOUNT
        return _prepare_partition_target_storage(
            target_part, efi_part, alongside_mount, src_ref, tgt_ref, log, progress, context
        )
    return _prepare_wipe_disk_storage(disk, src_ref, tgt_ref, log, progress, alongside_mount, context)


def _create_btrfs_subvolumes(target_part, log, progress, context: InstallerContext) -> None:
    # Lazy import to respect tests that patch install.*
    """Format `target_part` as btrfs and lay out the @ / @home subvolumes.

    Mounts target_part at a private temp root just long enough to create the
    subvolumes and set @ as default; the temp mount must not outlive this
    function regardless of success or failure, hence the finally.
    """
    try:
        from ..install import run_command, _as_root, _require_no_symlink, _safe_umount, unmount_target_disk, _run_cmd, _build_bootc_install_cmd  # pylint: disable=unused-import
    except ImportError:
        from ..runner import run_command  # fallback  # pylint: disable=unused-import
        from ..system import _as_root  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import unmount_target_disk  # fallback
        from ..disk import get_root_partition  # fallback  # pylint: disable=unused-import
        from .bootc_cmd import _run_cmd  # fallback
        from .bootc_cmd import _build_bootc_install_cmd  # fallback
    log(f"Formatting {target_part} as btrfs ...")
    _run_cmd(
        ["mkfs.btrfs", "-f", "-L", "KythOS", target_part],
        5, 10, log, progress,
        publish=lambda event: _push(event, context),
    )

    log("Creating Btrfs subvolumes @ and @home ...")
    from ..config import STAGING_BTRFS_ROOT
    btrfs_temp_root = STAGING_BTRFS_ROOT  # noqa: S108 — _require_no_symlink guards this below
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
    # Lazy import to respect tests that patch install.*
    """Mount efi_part under alongside_mount/boot/efi.

    Bind-mounts from efi_part's current mountpoint when the live session
    already has it mounted (e.g. /boot/efi), rather than mounting the device
    a second time.
    """
    try:
        from ..install import run_command, _as_root, _require_no_symlink, _safe_umount, unmount_target_disk, _run_cmd, _build_bootc_install_cmd  # pylint: disable=unused-import
    except ImportError:
        from ..runner import run_command  # fallback  # pylint: disable=unused-import
        from ..system import _as_root  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import unmount_target_disk  # fallback
        from ..disk import get_root_partition  # fallback  # pylint: disable=unused-import
        from .bootc_cmd import _run_cmd  # fallback
        from .bootc_cmd import _build_bootc_install_cmd  # fallback
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
    # Lazy import to respect tests that patch install.*
    """Best-effort capture of 'efibootmgr -v' output for later comparison.

    Returns "" (never raises) when efibootmgr is unavailable — legacy BIOS
    boot, a container test environment, or a live session with no UEFI
    firmware access — since this is a diagnostic safety net, not a
    requirement the install should ever fail on.
    """
    try:
        from ..install import run_command, _as_root, _require_no_symlink, _safe_umount, unmount_target_disk, _run_cmd, _build_bootc_install_cmd  # pylint: disable=unused-import
    except ImportError:
        from ..runner import run_command  # fallback  # pylint: disable=unused-import
        from ..system import _as_root  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import unmount_target_disk  # fallback
        from ..disk import get_root_partition  # fallback  # pylint: disable=unused-import
        from .bootc_cmd import _run_cmd  # fallback
        from .bootc_cmd import _build_bootc_install_cmd  # fallback
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
    # Lazy import to respect tests that patch install.*
    """Storage prep for the alongside/manual install modes: format the
    user-selected target partition as btrfs, lay out @ / @home subvolumes,
    mount it (plus EFI if present) under alongside_mount, then write the OS
    image into that mountpoint via `bootc install to-filesystem`.
    """
    try:
        from ..install import run_command, _as_root, _require_no_symlink, _safe_umount, unmount_target_disk, _run_cmd, _build_bootc_install_cmd  # pylint: disable=unused-import
    except ImportError:
        from ..runner import run_command  # fallback  # pylint: disable=unused-import
        from ..system import _as_root  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import unmount_target_disk  # fallback
        from ..disk import get_root_partition  # fallback  # pylint: disable=unused-import
        from .bootc_cmd import _run_cmd  # fallback
        from .bootc_cmd import _build_bootc_install_cmd  # fallback
    log(f"Target partition : {target_part}")
    log(f"EFI partition    : {efi_part or '(none detected)'}")

    _safe_umount(run_command, target_part)
    run_command(_as_root(["umount", "-Rl", alongside_mount]), check=False, capture_output=True)
    if efi_part:
        try:
            with tempfile.TemporaryDirectory() as td:
                ro = run_command(_as_root(["mount", "-o", "ro", efi_part, td]), check=False, capture_output=True)
                if ro.returncode == 0:
                    has_ms = pathlib.Path(td, "EFI", "Microsoft").exists() or pathlib.Path(td, "EFI", "microsoft").exists()
                    run_command(_as_root(["umount", td]), check=False, capture_output=True)
                    if has_ms:
                        log(f"ESP {efi_part} contains Windows bootloader — will not format, only reuse.")
        except Exception as exc:
            log(f"Warning: could not inspect ESP {efi_part}: {exc}")
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
    with _disk_image_hold(context.state.get("disk") or target_part, log):
        _run_cmd(
        install_cmd, 12, 90, log, progress,
        stall_timeout=3600, absolute_timeout=None,
            publish=lambda event: _push(event, context),
            cancel_event=context.cancel_requested,
            io_stall_timeout=600,
            net_stall_timeout=600,
        )
        _warn_if_efi_boot_entries_disappeared(efi_before, _snapshot_efi_boot_entries(log), log)

    return target_part, target_part, alongside_mount


def _prepare_wipe_disk_storage(disk, src_ref, tgt_ref, log, progress, alongside_mount, context: InstallerContext):
    # Lazy import to respect tests that patch install.*
    """Storage prep for the wipe install mode: unmount anything blocking the
    disk, then write the OS image via `bootc install to-disk`.
    """
    try:
        from ..install import _as_root, _require_no_symlink, _safe_umount, unmount_target_disk, get_root_partition, _run_cmd, _build_bootc_install_cmd
    except ImportError:
        from ..runner import run_command  # fallback  # pylint: disable=unused-import
        from ..system import _as_root  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import unmount_target_disk  # fallback
        from ..disk import get_root_partition  # fallback  # pylint: disable=unused-import
        from .bootc_cmd import _run_cmd  # fallback
        from .bootc_cmd import _build_bootc_install_cmd  # fallback
    unmount_target_disk(disk, log)
    install_cmd = _build_bootc_install_cmd(
        "to-disk", src_ref, tgt_ref, disk,
        extra_flags=["--filesystem", "btrfs", "--wipe"],
    )
    context.enter_phase(InstallPhase.IMAGE)
    with _disk_image_hold(disk, log):
        _run_cmd(
            install_cmd, 5, 90, log, progress,
        stall_timeout=3600, absolute_timeout=None,
        publish=lambda event: _push(event, context),
            cancel_event=context.cancel_requested,
            io_stall_timeout=600,
            net_stall_timeout=600,
    )
    return "", get_root_partition(disk), alongside_mount
