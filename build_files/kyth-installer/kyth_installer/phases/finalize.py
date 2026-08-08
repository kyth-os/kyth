"""Filesystem finalization (fstab, hostname, user) — Phase 2 verbatim."""
from __future__ import annotations

import subprocess
import traceback
from pathlib import Path

from ..config import STAGING_INSTALL_ROOT  # noqa: F401 - used via install re-export path but kept for completeness
from ..context import InstallRequest, InstallerContext, InstallLifecycle, InstallPhase
from ..assurance import validate_installed_target
from ..cleanup import unmount_configuration
from ..plan import _get_manual_mounts
from ..runner import run_command
from ..system import _as_root, _require_no_symlink, _safe_umount, ensure_system_accounts, find_deploy_etc, format_install_error, format_os_error
from kyth_shared.accounts import create_installer_user as _shared_create_installer_user
from .common import _push, _record_transaction
from ..recovery import write_failure_summary
from ..config import FAILURE_SUMMARY_FILE, LOG_FILE, TRANSACTION_FILE

def _blkid_uuid(part: str, log, *, timeout: float = 5) -> str | None:
    # Lazy import to respect tests that patch install.*
    try:
        from ..install import run_command, _as_root, _safe_umount, _require_no_symlink, ensure_system_accounts, find_deploy_etc, _get_manual_mounts
    except ImportError:
        from ..runner import run_command  # fallback
        from ..system import _as_root  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import ensure_system_accounts  # fallback
        from ..system import find_deploy_etc  # fallback
        from ..plan import _get_manual_mounts  # fallback
    """Look up a partition's filesystem UUID via blkid, for building an
    fstab entry. Returns None (after logging a warning) on any failure —
    callers should skip that fstab entry rather than write one with a
    blank UUID. Shared by every fstab-writing path so they see the same
    lookup behavior (same timeout, same failure handling) instead of each
    reimplementing it slightly differently."""
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
    """fstab fsck pass number for a non-root mount. 0 for swap and btrfs —
    btrfs has no traditional boot-time fsck integration, so passing it to
    e2fsck-style checking is a no-op at best and a boot delay at worst — 2
    for everything else with a real fsck tool. Never 1: that's reserved
    for the root filesystem, which isn't written through this path."""
    return 0 if fstype in ("linux-swap", "btrfs") else 2


def _append_fstab_line(etc, fstab_line: str, log, description: str) -> bool:
    # Lazy import to respect tests that patch install.*
    try:
        from ..install import run_command, _as_root, _safe_umount, _require_no_symlink, ensure_system_accounts, find_deploy_etc, _get_manual_mounts
    except ImportError:
        from ..runner import run_command  # fallback
        from ..system import _as_root  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import ensure_system_accounts  # fallback
        from ..system import find_deploy_etc  # fallback
        from ..plan import _get_manual_mounts  # fallback
    """Append one line to the target system's fstab. Returns whether it
    succeeded; callers decide whether that's fatal for the mount it was
    building an entry for."""
    try:
        run_command(
            _as_root(["/usr/bin/tee", "-a", str(Path(etc, "fstab"))]),
            input=fstab_line, text=True,
            stdout=subprocess.DEVNULL, check=True,
        )
    except OSError as fe:
        log(
            f"Warning: failed to update fstab for {description}: "
            f"{format_os_error(fe, path=Path(etc, 'fstab'))}"
        )
        return False
    except Exception as fe:
        log(f"Warning: failed to update fstab for {description}: {fe}")
        return False
    log(f"Fstab updated for {description}: {fstab_line.strip()}")
    return True


def _configure_alongside_fstab(config_root, target_part, etc, log) -> None:
    # Lazy import to respect tests that patch install.*
    try:
        from ..install import run_command, _as_root, _safe_umount, _require_no_symlink, ensure_system_accounts, find_deploy_etc, _get_manual_mounts
    except ImportError:
        from ..runner import run_command  # fallback
        from ..system import _as_root  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import ensure_system_accounts  # fallback
        from ..system import find_deploy_etc  # fallback
        from ..plan import _get_manual_mounts  # fallback
    """Mount the alongside-install target's @home subvolume under the ostree
    deploy root and wire it into the target system's fstab."""
    target_home = Path(config_root) / "ostree/deploy/default/var/home"
    run_command(_as_root(["mkdir", "-p", str(target_home)]), check=True)
    _safe_umount(run_command, str(target_home))
    run_command(_as_root(["mount", "-o", "subvol=@home", target_part, str(target_home)]), check=True)

    uuid_out = _blkid_uuid(target_part, log)
    if uuid_out is None:
        return
    fstab_line = f"UUID={uuid_out} /var/home btrfs subvol=@home,compress=zstd:1 0 {_fsck_pass_for('btrfs')}\n"
    _append_fstab_line(etc, fstab_line, log, "@home subvolume")


def _configure_manual_mounts(config_root, etc, log, context: InstallerContext) -> None:
    # Lazy import to respect tests that patch install.*
    try:
        from ..install import run_command, _as_root, _safe_umount, _require_no_symlink, ensure_system_accounts, find_deploy_etc, _get_manual_mounts
    except ImportError:
        from ..runner import run_command  # fallback
        from ..system import _as_root  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import ensure_system_accounts  # fallback
        from ..system import find_deploy_etc  # fallback
        from ..plan import _get_manual_mounts  # fallback
    """Mount each manually-configured partition under the ostree deploy root
    and add a matching fstab entry (mapping /home to /var/home)."""
    manual_mounts = _get_manual_mounts(context)
    for mnt in manual_mounts:
        part = mnt["partition"]
        mp = mnt["mountpoint"]
        fs = mnt["fstype"]
        try:
            uuid_out = _blkid_uuid(part, log)
            if uuid_out is None:
                log(f"Warning: skipping fstab entry for {mp} ({part}) — no UUID")
                continue
            # Map /home to /var/home in ostree layout
            fstab_mp = "/var/home" if mp == "/home" else mp
            target_path = Path(config_root) / fstab_mp.lstrip("/")
            if fs == "linux-swap":
                fstab_line = f"UUID={uuid_out} none swap defaults 0 {_fsck_pass_for(fs)}\n"
            else:
                mount_options = "defaults,compress=zstd:1" if fs == "btrfs" else "defaults"
                fstab_line = f"UUID={uuid_out} {fstab_mp} {fs} {mount_options} 0 {_fsck_pass_for(fs)}\n"
                run_command(
                    _as_root(["mkdir", "-p", str(target_path)]),
                    check=False,
                )
                # Unmount any existing mount at this path (e.g. @home subvolume)
                _safe_umount(run_command, str(target_path))
            if not _append_fstab_line(etc, fstab_line, log, f"{part} at {mp}"):
                continue
            if fs != "linux-swap":
                run_command(
                    _as_root(["mount", part, str(target_path)]),
                    check=False,
                )
            log(f"Manual mount: {part} at {mp} ({fs})")
        except Exception as me:
            log(f"Warning: failed to configure manual mount {part} at {mp}: {me}")


def _configure_hostname_timezone(etc, state, log) -> None:
    # Lazy import to respect tests that patch install.*
    try:
        from ..install import run_command, _as_root, _safe_umount, _require_no_symlink, ensure_system_accounts, find_deploy_etc, _get_manual_mounts
    except ImportError:
        from ..runner import run_command  # fallback
        from ..system import _as_root  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import ensure_system_accounts  # fallback
        from ..system import find_deploy_etc  # fallback
        from ..plan import _get_manual_mounts  # fallback
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
    # Lazy import to respect tests that patch install.*
    try:
        from ..install import run_command, _as_root, _safe_umount, _require_no_symlink, ensure_system_accounts, find_deploy_etc, _get_manual_mounts
    except ImportError:
        from ..runner import run_command  # fallback
        from ..system import _as_root  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import ensure_system_accounts  # fallback
        from ..system import find_deploy_etc  # fallback
        from ..plan import _get_manual_mounts  # fallback
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
    # Lazy import to respect tests that patch install.*
    try:
        from ..install import run_command, _as_root, _safe_umount, _require_no_symlink, ensure_system_accounts, find_deploy_etc, _get_manual_mounts
    except ImportError:
        from ..runner import run_command  # fallback
        from ..system import _as_root  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import ensure_system_accounts  # fallback
        from ..system import find_deploy_etc  # fallback
        from ..plan import _get_manual_mounts  # fallback
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
    # Lazy import to respect tests that patch install.*
    try:
        from ..install import run_command, _as_root, _safe_umount, _require_no_symlink, ensure_system_accounts, find_deploy_etc, _get_manual_mounts
    except ImportError:
        from ..runner import run_command  # fallback
        from ..system import _as_root  # fallback
        from ..system import _safe_umount  # fallback
        from ..system import _require_no_symlink  # fallback
        from ..system import ensure_system_accounts  # fallback
        from ..system import find_deploy_etc  # fallback
        from ..plan import _get_manual_mounts  # fallback
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