"""Install orchestration: shared mutable run state, SSE event log, and the
background worker thread that performs the actual bootc install.

_state/_events/_install_lock are process-wide singletons that server.py
reads and mutates directly (module-qualified, e.g. install._state) rather
than importing by name, since re-binding via `from .install import _state`
would not see later mutations.
"""

import codecs
import os
import select
import subprocess
import threading
import time
import traceback
from collections import deque
from pathlib import Path

from .config import LOG_FILE, SKIP_FETCH_CHECK
from .disk import get_root_partition
from .imagesrc import _friendly_network_error, _install_images, _network_preflight
from .plan import _get_manual_mounts, _prepare_install_plan, _validate_install_target, _validate_storage_intent
from .runner import run_command
from kyth_shared import _NetStatsTracker, _get_rx_bytes, _parse_size_bytes  # noqa: F401

from .system import (
    _as_root,
    _try_stage_mok_enrollment,
    ensure_system_accounts,
    find_deploy_etc,
    format_install_error,
    format_os_error,
    require_root,
    unmount_target_disk,
)

_state: dict = {
    "disk": "",
    "install_mode": "wipe",       # "wipe" or "alongside"
    "target_partition": "",       # alongside only
    "efi_partition": "",          # alongside only (may be auto-detected)
    "hostname": "kyth", "timezone": "UTC",
    "username": "", "password_hash": "", "kernel": "fedora",
    "mok_password": "",
}

_events: list[dict] = []
_events_lock = threading.Lock()
_new_event = threading.Condition(_events_lock)
_install_lock = threading.Lock()


def _push(event: dict) -> None:
    with _new_event:
        _events.append(event)
        _new_event.notify_all()


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
        "--acknowledge-destructive",
    ]
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
) -> None:
    full_cmd = _as_root(cmd)
    log(f"$ {' '.join(full_cmd)}")
    proc = subprocess.Popen(
        full_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
    )
    if proc.stdout is None:
        proc.kill()
        proc.wait()
        raise RuntimeError("Could not capture installer command output.")

    monitor_stop = threading.Event()
    recent_output: deque[str] = deque(maxlen=30)
    tracker: _NetStatsTracker | None = None

    def _net_monitor() -> None:
        nonlocal tracker
        while not monitor_stop.wait(1):
            total = output_state.get("total", 0)
            rx_start = output_state.get("rx_start", 0)
            if total <= 0 or rx_start <= 0:
                tracker = None
                continue
            if tracker is None:
                tracker = _NetStatsTracker(total, rx_start)
            stats = tracker.tick(_get_rx_bytes())
            frac = min(0.95, stats["downloaded"] / total)
            progress(int(pct_start + frac * (pct_end - pct_start)))
            _push({"type": "stats",
                   "downloaded": stats["downloaded"],
                   "total":      total,
                   "speed":      stats["speed"],
                   "eta_sec":    stats["eta_sec"]})

    monitor_thread = threading.Thread(target=_net_monitor, daemon=True)
    monitor_thread.start()

    started = time.monotonic()
    last_activity = started
    last_rx = _get_rx_bytes()
    pending = ""
    last_line = None
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def emit_line(line: str) -> None:
        nonlocal last_line
        stripped = line.strip()
        if not stripped or stripped == last_line:
            return
        last_line = stripped
        log(stripped)
        recent_output.append(stripped)
        if "layers needed:" in stripped:
            try:
                details = stripped.split("layers needed:", 1)[1]
                size_str = details.split("(", 1)[1].rstrip(")") if "(" in details else ""
                output_state["total"] = _parse_size_bytes(size_str)
                output_state["rx_start"] = _get_rx_bytes()
            except Exception:
                pass

    def consume_output(text: str, final: bool = False) -> None:
        nonlocal pending
        pending += text
        while True:
            indexes = [idx for idx in (pending.find("\n"), pending.find("\r")) if idx >= 0]
            if not indexes:
                break
            split_at = min(indexes)
            emit_line(pending[:split_at])
            pending = pending[split_at + 1:]
        if final and pending:
            emit_line(pending)
            pending = ""

    try:
        fd = proc.stdout.fileno()
        while True:
            ready, _, _ = select.select([fd], [], [], 1)
            if ready:
                chunk = os.read(fd, 64 * 1024)
                if not chunk:
                    break
                last_activity = time.monotonic()
                consume_output(decoder.decode(chunk))

            now = time.monotonic()
            rx_now = _get_rx_bytes()
            if rx_now > last_rx:
                last_rx = rx_now
                last_activity = now
            if absolute_timeout is not None and now - started > absolute_timeout:
                raise RuntimeError(
                    f"Command exceeded absolute timeout of {absolute_timeout // 60} min"
                )
            if now - last_activity > stall_timeout:
                raise RuntimeError(
                    "Command timed out after "
                    f"{stall_timeout // 60} min with no output or network traffic"
                )

        consume_output(decoder.decode(b"", final=True), final=True)
        proc.wait()
    except Exception:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        raise
    finally:
        monitor_stop.set()
        monitor_thread.join(timeout=2)
        proc.stdout.close()
    if proc.returncode != 0:
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
            raise RuntimeError(
                _friendly_network_error(
                    "The image download lost network access before it finished."
                )
            )
        detail = "\n".join(list(recent_output)[-10:]) or "No command output was captured."
        raise RuntimeError(f"Command failed (exit {proc.returncode}):\n  {' '.join(full_cmd)}\n\n{detail}")
    progress(pct_end)

def _prepare_install_context(log):
    kernel = _state.get("kernel", "fedora")
    src_ref, tgt_ref = _install_images(kernel)
    _validate_storage_intent(_state)
    if not SKIP_FETCH_CHECK:
        log("Running network preflight check...")
        net_err = _network_preflight(src_ref)
        if net_err:
            raise RuntimeError(net_err)
    install_plan = _prepare_install_plan(_state, log)
    disk, target_partition = _validate_install_target(_state)
    _state["disk"] = disk
    if target_partition:
        _state["target_partition"] = target_partition
    else:
        _state.pop("target_partition", None)
    disk = _state["disk"]
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
    disk, install_mode, src_ref, tgt_ref, log, progress, alongside_mount
):
    target_part = ""
    root_part = ""
    if install_mode in ("alongside", "manual"):
        target_part = _state.get("target_partition", "")
        efi_part    = _state.get("efi_partition", "")
        alongside_mount = "/var/tmp/kyth-alongside-target"

        log(f"Target partition : {target_part}")
        log(f"EFI partition    : {efi_part or '(none detected)'}")

        run_command(_as_root(["umount", "-l", target_part]), check=False, capture_output=True)
        run_command(_as_root(["umount", "-Rl", alongside_mount]), check=False, capture_output=True)

        log(f"Formatting {target_part} as btrfs ...")
        _run_cmd(["mkfs.btrfs", "-f", "-L", "KythOS", target_part], 5, 10, log, progress)

        # Create btrfs subvolumes @ and @home
        log("Creating Btrfs subvolumes @ and @home ...")
        btrfs_temp_root = "/var/tmp/kyth-btrfs-root"
        run_command(_as_root(["umount", "-l", btrfs_temp_root]), check=False, capture_output=True)
        run_command(_as_root(["mkdir", "-p", btrfs_temp_root]), check=True)
        run_command(_as_root(["mount", target_part, btrfs_temp_root]), check=True)
        try:
            run_command(_as_root(["btrfs", "subvolume", "create", f"{btrfs_temp_root}/@"]), check=True)
            run_command(_as_root(["btrfs", "subvolume", "create", f"{btrfs_temp_root}/@home"]), check=True)
            log("Setting Btrfs default subvolume to @ ...")
            run_command(_as_root(["btrfs", "subvolume", "set-default", f"{btrfs_temp_root}/@"]), check=True)
        finally:
            run_command(_as_root(["umount", "-l", btrfs_temp_root]), check=True)

        run_command(_as_root(["mkdir", "-p", alongside_mount]), check=True)
        run_command(_as_root(["mount", "-o", "subvol=@", target_part, alongside_mount]), check=True)
        progress(11)

        if efi_part:
            efi_mountpoint = Path(alongside_mount) / "boot" / "efi"
            run_command(_as_root(["mkdir", "-p", str(efi_mountpoint)]), check=True)
            try:
                current_efi_mnt = subprocess.check_output(
                    ["findmnt", "-n", "-o", "MOUNTPOINT", efi_part],
                    text=True, stderr=subprocess.DEVNULL, timeout=5,
                ).strip()
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
        _run_cmd(install_cmd, 12, 90, log, progress, stall_timeout=3600, absolute_timeout=None)

        root_part = target_part

    else:
        unmount_target_disk(disk, log)
        install_cmd = _build_bootc_install_cmd(
            "to-disk", src_ref, tgt_ref, disk,
            extra_flags=["--filesystem", "btrfs", "--wipe"],
        )
        _run_cmd(install_cmd, 5, 90, log, progress, stall_timeout=3600, absolute_timeout=None)
        root_part = get_root_partition(disk)
    return target_part, root_part, alongside_mount

def _configure_installed_system(
    root_part, target_part, disk, kernel, install_mode, config_root, alongside_mount, log, progress
):
    try:
        etc = find_deploy_etc(config_root)
        if etc:
            if install_mode == "alongside":
                target_home = Path(config_root) / "ostree/deploy/default/var/home"
                run_command(_as_root(["mkdir", "-p", str(target_home)]), check=True)
                run_command(_as_root(["umount", "-l", str(target_home)]), check=False, capture_output=True)
                run_command(_as_root(["mount", "-o", "subvol=@home", target_part, str(target_home)]), check=True)

                try:
                    uuid_out = subprocess.check_output(["blkid", "-s", "UUID", "-o", "value", target_part], text=True).strip()
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

            # Manual partition mode: mount additional partitions and update fstab
            if install_mode == "manual":
                manual_mounts = _get_manual_mounts()
                for mnt in manual_mounts:
                    part = mnt["partition"]
                    mp = mnt["mountpoint"]
                    fs = mnt["fstype"]
                    try:
                        uuid_out = subprocess.check_output(
                            ["blkid", "-s", "UUID", "-o", "value", part],
                            text=True, timeout=5
                        ).strip()
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

            hostname_path = str(Path(etc, "hostname"))
            try:
                run_command(
                    _as_root(["/usr/bin/tee", hostname_path]),
                    input=f"{_state['hostname']}\n", text=True,
                    stdout=subprocess.DEVNULL, check=True,
                )
            except OSError as exc:
                raise OSError(format_os_error(exc, path=hostname_path)) from exc
            log(f"Hostname : {_state['hostname']}")

            localtime_path = str(Path(etc, "localtime"))
            try:
                run_command(
                    _as_root(["ln", "-snf",
                              f"/usr/share/zoneinfo/{_state['timezone']}",
                              localtime_path]),
                    check=True,
                )
            except OSError as exc:
                raise OSError(format_os_error(exc, path=localtime_path)) from exc
            log(f"Timezone : {_state['timezone']}")
            progress(95)

            deploy_root = str(Path(etc).parent)
            ensure_system_accounts(deploy_root, log)

            username = _state.get("username", "").strip()
            password_hash = _state.get("password_hash", "")
            if username and password_hash:
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

def _run_install_worker(log, progress, alongside_mount):
    try:
        require_root()
        disk, install_mode, kernel, src_ref, tgt_ref = _prepare_install_context(log)

        target_part, root_part, alongside_mount = _prepare_install_storage(
            disk, install_mode, src_ref, tgt_ref, log, progress, alongside_mount
        )

        log("── Phase 2: Configuring installed system ─────────────────────────")
        progress(91)

        if alongside_mount:
            config_root = alongside_mount
        else:
            config_root = "/var/tmp/kyth-install-root"
            run_command(_as_root(["mkdir", "-p", config_root]), check=True)
            # Detach any stale mount left by a previously crashed install attempt.
            run_command(_as_root(["umount", "-l", config_root]), check=False, capture_output=True)
            run_command(_as_root(["mount", root_part, config_root]), check=True)

        progress(93)

        _configure_installed_system(
            root_part, target_part, disk, kernel, install_mode, config_root, alongside_mount, log, progress
        )

        log("── Phase 3: Staging Secure Boot enrollment ───────────────────────")
        mok_state = _try_stage_mok_enrollment(log, kernel, _state["mok_password"])

        progress(100)
        _push({"type": "done", "mok_state": mok_state})

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
        _push({"type": "error", "message": message})
    finally:
        _state["password_hash"] = ""
        _state["mok_password"] = ""
        # Guard against orphaned mounts when Phase 1 fails before the inner
        # try/finally (which holds the normal umount) is ever entered.
        if alongside_mount:
            run_command(_as_root(["umount", "-Rl", alongside_mount]), check=False, capture_output=True)

def _run_install() -> None:
    with _events_lock:
        _events.clear()

    def log(msg: str) -> None:
        _push({"type": "log", "text": msg})
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
            })

    def progress(pct: int) -> None:
        _push({"type": "progress", "value": pct})

    try:
        require_root()
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOG_FILE.write_text("")
        os.chmod(LOG_FILE, 0o600)
    except Exception as exc:
        message = format_install_error(exc)
        _push({"type": "error", "message": message})
        return

    alongside_mount = ""

    _run_install_worker(log, progress, alongside_mount)
