"""Install orchestration for an explicit installer runtime context."""

import os
import subprocess
import traceback
from pathlib import Path

from .config import LOG_FILE, SKIP_FETCH_CHECK
from .context import InstallLifecycle, InstallerContext
from .disk import get_root_partition
from .imagesrc import _friendly_network_error, _install_images, _network_preflight
from .plan import _get_manual_mounts, _prepare_install_plan, _validate_install_target, _validate_storage_intent
from .runner import run_command
from .streaming import StreamingCommandRunner
from kyth_shared import _get_rx_bytes

from .system import (
    _as_root,
    _require_no_symlink,
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
    if SKIP_FETCH_CHECK:
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
        rx_bytes=_get_rx_bytes,
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

def _prepare_install_context(log, context: InstallerContext):
    state = context.state
    kernel = state.get("kernel", "fedora")
    src_ref, tgt_ref = _install_images(kernel)
    _validate_storage_intent(state, context)
    if not SKIP_FETCH_CHECK:
        log("Running network preflight check...")
        net_err = _network_preflight(src_ref)
        if net_err:
            raise RuntimeError(net_err)
    install_plan = _prepare_install_plan(state, log, context)
    disk, target_partition = _validate_install_target(state, context)
    state["disk"] = disk
    if target_partition:
        state["target_partition"] = target_partition
    else:
        state.pop("target_partition", None)
    disk = state["disk"]
    install_mode = install_plan.mode
    log(f"Mode         : {install_mode}")
    log(f"Kernel       : {kernel}")
    log(f"Source imgref: {src_ref}")
    log(f"Target image : {tgt_ref}")
    log(f"Disk         : {disk}")
    log("")

    log("── Phase 1: Writing OS image to disk ─────────────────────────────")
    return disk, install_mode, kernel, src_ref, tgt_ref

def _prepare_install_storage(
    disk, install_mode, src_ref, tgt_ref, log, progress, alongside_mount,
    context: InstallerContext,
):
    state = context.state
    target_part = ""
    root_part = ""
    if install_mode in ("alongside", "manual"):
        target_part = state.get("target_partition", "")
        efi_part    = state.get("efi_partition", "")
        alongside_mount = "/var/tmp/kyth-alongside-target"  # noqa: S108 — _require_no_symlink guards this below

        log(f"Target partition : {target_part}")
        log(f"EFI partition    : {efi_part or '(none detected)'}")

        run_command(_as_root(["umount", "-l", target_part]), check=False, capture_output=True)
        run_command(_as_root(["umount", "-Rl", alongside_mount]), check=False, capture_output=True)

        log(f"Formatting {target_part} as btrfs ...")
        _run_cmd(
            ["mkfs.btrfs", "-f", "-L", "KythOS", target_part],
            5, 10, log, progress,
            publish=lambda event: _push(event, context),
        )

        # Create btrfs subvolumes @ and @home
        log("Creating Btrfs subvolumes @ and @home ...")
        btrfs_temp_root = "/var/tmp/kyth-btrfs-root"  # noqa: S108 — _require_no_symlink guards this below
        run_command(_as_root(["umount", "-l", btrfs_temp_root]), check=False, capture_output=True)
        _require_no_symlink(btrfs_temp_root)
        run_command(_as_root(["mkdir", "-p", btrfs_temp_root]), check=True)
        run_command(_as_root(["mount", target_part, btrfs_temp_root]), check=True)
        try:
            run_command(_as_root(["btrfs", "subvolume", "create", f"{btrfs_temp_root}/@"]), check=True)
            run_command(_as_root(["btrfs", "subvolume", "create", f"{btrfs_temp_root}/@home"]), check=True)
            log("Setting Btrfs default subvolume to @ ...")
            run_command(_as_root(["btrfs", "subvolume", "set-default", f"{btrfs_temp_root}/@"]), check=True)
        finally:
            run_command(_as_root(["umount", "-l", btrfs_temp_root]), check=True)

        _require_no_symlink(alongside_mount)
        run_command(_as_root(["mkdir", "-p", alongside_mount]), check=True)
        run_command(_as_root(["mount", "-o", "subvol=@", target_part, alongside_mount]), check=True)
        progress(11)

        if efi_part:
            efi_mountpoint = Path(alongside_mount) / "boot" / "efi"
            run_command(_as_root(["mkdir", "-p", str(efi_mountpoint)]), check=True)
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

        install_cmd = _build_bootc_install_cmd(
            "to-filesystem", src_ref, tgt_ref, alongside_mount,
            extra_flags=["--skip-finalize", "--karg=rootflags=subvol=@"],
        )
        _run_cmd(
            install_cmd, 12, 90, log, progress,
            stall_timeout=3600, absolute_timeout=None,
            publish=lambda event: _push(event, context),
        )

        root_part = target_part

    else:
        unmount_target_disk(disk, log)
        install_cmd = _build_bootc_install_cmd(
            "to-disk", src_ref, tgt_ref, disk,
            extra_flags=["--filesystem", "btrfs", "--wipe"],
        )
        _run_cmd(
            install_cmd, 5, 90, log, progress,
            stall_timeout=3600, absolute_timeout=None,
            publish=lambda event: _push(event, context),
        )
        root_part = get_root_partition(disk)
    return target_part, root_part, alongside_mount

def _configure_alongside_fstab(config_root, target_part, etc, log) -> None:
    """Mount the alongside-install target's @home subvolume under the ostree
    deploy root and wire it into the target system's fstab."""
    target_home = Path(config_root) / "ostree/deploy/default/var/home"
    run_command(_as_root(["mkdir", "-p", str(target_home)]), check=True)
    run_command(_as_root(["umount", "-l", str(target_home)]), check=False, capture_output=True)
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
                fstab_line = f"UUID={uuid_out} {fstab_mp} {fs} defaults,compress=zstd:1 0 2\n"
                run_command(
                    _as_root(["mkdir", "-p", str(target_path)]),
                    check=False,
                )
                # Unmount any existing mount at this path (e.g. @home subvolume)
                run_command(
                    _as_root(["umount", "-l", str(target_path)]),
                    check=False, capture_output=True,
                )
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


def _create_installer_user(etc, config_root, deploy_root, username, password_hash, log, progress) -> None:
    log(f"Creating user: {username}")
    try:
        run_command(
            _as_root([
                "useradd", "--root", deploy_root,
                "-M", "-G", "wheel,video,audio,render",
                "-s", "/bin/bash", username,
            ]),
            check=True,
        )

        shadow_path = f"{etc}/shadow"
        cat_r = run_command(
            _as_root(["cat", shadow_path]),
            capture_output=True, text=True, check=True,
        )
        new_lines = []
        hash_written = False
        for line in cat_r.stdout.splitlines(keepends=True):
            if line.startswith(f"{username}:"):
                fields = line.split(":")
                fields[1] = password_hash
                new_lines.append(":".join(fields))
                hash_written = True
            else:
                new_lines.append(line)
        if not hash_written:
            raise RuntimeError(
                f"User '{username}' not found in shadow after useradd"
            )
        run_command(
            _as_root(["tee", shadow_path]),
            input="".join(new_lines), text=True,
            stdout=subprocess.DEVNULL, check=True,
        )

        uid, gid = "1000", "1000"
        cat_r = run_command(
            _as_root(["cat", f"{etc}/passwd"]),
            capture_output=True, text=True,
        )
        for line in cat_r.stdout.splitlines():
            if line.startswith(f"{username}:"):
                parts = line.split(":")
                uid, gid = parts[2], parts[3]
                break

        var_home = (
            Path(config_root) / "ostree/deploy/default/var/home" / username
        )
        run_command(_as_root(["mkdir", "-p", str(var_home)]), check=True)
        run_command(_as_root(["chown", f"{uid}:{gid}", str(var_home)]), check=True)
        run_command(_as_root(["chmod", "700", str(var_home)]), check=True)

        # skel may be under deploy root; test via elevated path.
        skel = Path(deploy_root) / "etc/skel"
        skel_check = run_command(
            _as_root(["test", "-d", str(skel)]),
            check=False, capture_output=True,
        )
        if skel_check.returncode == 0:
            run_command(
                _as_root(["cp", "-rT", str(skel), str(var_home)]),
                check=True,
            )
            run_command(
                _as_root(["chown", "-R", f"{uid}:{gid}", str(var_home)]),
                check=True,
            )

        run_command(
            _as_root(["restorecon", "-RF", str(var_home)]),
            check=False,
        )
        log(f"User '{username}' created (uid={uid})")
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
    context: InstallerContext,
):
    state = context.state
    try:
        etc = find_deploy_etc(config_root)
        if etc:
            if install_mode == "alongside":
                _configure_alongside_fstab(config_root, target_part, etc, log)

            # Manual partition mode: mount additional partitions and update fstab
            if install_mode == "manual":
                _configure_manual_mounts(config_root, etc, log, context)

            _configure_hostname_timezone(etc, state, log)
            progress(95)

            deploy_root = str(Path(etc).parent)
            ensure_system_accounts(deploy_root, log)

            username = state.get("username", "").strip()
            password_hash = state.get("password_hash", "")
            if username and password_hash:
                _create_installer_user(etc, config_root, deploy_root, username, password_hash, log, progress)
        else:
            log("Warning: deploy/etc not found — skipping post-install configuration")
    finally:
        run_command(_as_root(["sync"]), check=False)
        progress(99)
        if alongside_mount:
            target_home = Path(alongside_mount) / "ostree/deploy/default/var/home"
            run_command(_as_root(["umount", "-Rl", str(target_home)]), check=False, capture_output=True)
            run_command(_as_root(["umount", "-Rl", alongside_mount]), check=False, capture_output=True)
        else:
            run_command(_as_root(["umount", config_root]), check=False)

def _run_install_worker(
    log, progress, alongside_mount, context: InstallerContext,
):
    state = context.state
    try:
        require_root()
        disk, install_mode, kernel, src_ref, tgt_ref = _prepare_install_context(log, context)

        target_part, root_part, alongside_mount = _prepare_install_storage(
            disk, install_mode, src_ref, tgt_ref, log, progress, alongside_mount, context
        )

        log("── Phase 2: Configuring installed system ─────────────────────────")
        progress(91)

        if alongside_mount:
            config_root = alongside_mount
        else:
            config_root = "/var/tmp/kyth-install-root"  # noqa: S108 — _require_no_symlink guards this below
            _require_no_symlink(config_root)
            run_command(_as_root(["mkdir", "-p", config_root]), check=True)
            # Detach any stale mount left by a previously crashed install attempt.
            run_command(_as_root(["umount", "-l", config_root]), check=False, capture_output=True)
            run_command(_as_root(["mount", root_part, config_root]), check=True)

        progress(93)

        _configure_installed_system(
            root_part, target_part, disk, kernel, install_mode, config_root, alongside_mount, log, progress, context
        )

        log("── Phase 3: Staging Secure Boot enrollment ───────────────────────")
        mok_state = _try_stage_mok_enrollment(log, kernel, state["mok_password"])

        progress(100)
        context.transition(InstallLifecycle.DONE)
        _push({"type": "done", "mok_state": mok_state}, context)

    except Exception as exc:
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
        _push({"type": "error", "message": message}, context)
    finally:
        state["password_hash"] = ""  # nosec B105 # nosemgrep -- clearing, not a hardcoded secret
        state["mok_password"] = ""  # nosec B105 # nosemgrep -- clearing, not a hardcoded secret
        # Guard against orphaned mounts when Phase 1 fails before the inner
        # try/finally (which holds the normal umount) is ever entered.
        if alongside_mount:
            run_command(_as_root(["umount", "-Rl", alongside_mount]), check=False, capture_output=True)

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
    except Exception as exc:
        message = format_install_error(exc)
        context.transition(InstallLifecycle.FAILED)
        _push({"type": "error", "message": message}, context)
        return

    alongside_mount = ""

    _run_install_worker(log, progress, alongside_mount, context)
