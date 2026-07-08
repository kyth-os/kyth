"""Install orchestration: shared mutable run state, SSE event log, and the
background worker thread that performs the actual bootc install.

_state/_events/_install_lock are process-wide singletons that server.py
reads and mutates directly (module-qualified, e.g. install._state) rather
than importing by name, since re-binding via `from .install import _state`
would not see later mutations.
"""

import os
import select
import subprocess
import threading
import time
import traceback
from pathlib import Path

from .config import LOG_FILE, SKIP_FETCH_CHECK
from .disk import get_root_partition
from .imagesrc import _friendly_network_error, _install_images
from .plan import _prepare_install_plan, _validate_install_target
from .system import (
    _as_root,
    _try_stage_mok_enrollment,
    ensure_system_accounts,
    find_deploy_etc,
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


def _get_rx_bytes() -> int:
    try:
        total = 0
        with open("/proc/net/dev") as f:
            for line in f:
                if ":" not in line:
                    continue
                iface, data = line.split(":", 1)
                if iface.strip() == "lo":
                    continue
                total += int(data.split()[0])
        return total
    except Exception:
        return 0


def _parse_size_bytes(size_str: str) -> int:
    try:
        parts = size_str.strip().split()
        value = float(parts[0])
        unit  = parts[1].upper().rstrip("B") if len(parts) > 1 else ""
        mult  = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
        return int(value * mult.get(unit, 0))
    except Exception:
        return 0


def _run_install() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text("")
    os.chmod(LOG_FILE, 0o600)

    def log(msg: str) -> None:
        _push({"type": "log", "text": msg})
        with LOG_FILE.open("a") as f:
            f.write(msg + "\n")

    def progress(pct: int) -> None:
        _push({"type": "progress", "value": pct})

    def run_cmd(cmd: list[str], pct_start: int, pct_end: int) -> None:
        full_cmd = _as_root(cmd)
        log(f"$ {' '.join(full_cmd)}")
        proc = subprocess.Popen(
            full_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )

        _total_bytes:  list[int]  = [0]
        _rx_start:     list[int]  = [0]
        _monitor_stop: list[bool] = [False]

        def _net_monitor() -> None:
            rx_prev = 0
            t_prev  = time.monotonic()
            speed_samples: list[float] = []
            while not _monitor_stop[0]:
                time.sleep(1)
                if _total_bytes[0] == 0 or _rx_start[0] == 0:
                    continue
                rx_now     = _get_rx_bytes()
                t_now      = time.monotonic()
                downloaded = min(_total_bytes[0], max(0, rx_now - _rx_start[0]))
                frac       = min(0.95, downloaded / _total_bytes[0])
                progress(int(pct_start + frac * (pct_end - pct_start)))
                dt = t_now - t_prev
                if dt > 0 and rx_prev > 0:
                    speed_samples.append((rx_now - rx_prev) / dt)
                    if len(speed_samples) > 5:
                        speed_samples.pop(0)
                rx_prev = rx_now
                t_prev  = t_now
                if speed_samples:
                    avg_speed = sum(speed_samples) / len(speed_samples)
                    remaining = max(0, _total_bytes[0] - downloaded)
                    _push({"type": "stats",
                           "downloaded": downloaded,
                           "total":      _total_bytes[0],
                           "speed":      int(avg_speed),
                           "eta_sec":    int(remaining / avg_speed) if avg_speed > 0 else 0})

        monitor_thread = threading.Thread(target=_net_monitor, daemon=True)
        monitor_thread.start()

        STALL_TIMEOUT = 600
        last_output   = time.monotonic()
        recent_output: list[str] = []
        while True:
            ready, _, _ = select.select([proc.stdout], [], [], 30)
            if ready:
                line = proc.stdout.readline()
                if not line:
                    break
                last_output = time.monotonic()
                stripped = line.rstrip()
                log(stripped)
                recent_output.append(stripped)
                recent_output = recent_output[-30:]
                if "layers needed:" in stripped:
                    try:
                        m = stripped.split("layers needed:")[1]
                        size_str = m.split("(")[1].rstrip(")") if "(" in m else ""
                        _total_bytes[0] = _parse_size_bytes(size_str)
                        _rx_start[0]    = _get_rx_bytes()
                    except Exception:
                        pass
            else:
                if time.monotonic() - last_output > STALL_TIMEOUT:
                    proc.kill()
                    raise RuntimeError(
                        f"Command timed out (no output for {STALL_TIMEOUT // 60} min)"
                    )

        _monitor_stop[0] = True
        monitor_thread.join(timeout=2)
        proc.wait()
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
            raise RuntimeError(
                f"Command failed (exit {proc.returncode}):\n  {' '.join(full_cmd)}"
            )
        progress(pct_end)

    alongside_mount = ""

    try:
        install_plan = _prepare_install_plan(_state, log)
        disk, target_partition = _validate_install_target(_state)
        _state["disk"] = disk
        if target_partition:
            _state["target_partition"] = target_partition
        else:
            _state.pop("target_partition", None)
        disk = _state["disk"]
        kernel = _state.get("kernel", "fedora")
        install_mode = install_plan.mode
        src_ref, tgt_ref = _install_images(kernel)
        log(f"Mode         : {install_mode}")
        log(f"Kernel       : {kernel}")
        log(f"Source imgref: {src_ref}")
        log(f"Target image : {tgt_ref}")
        log(f"Disk         : {disk}")
        log("")

        log("── Phase 1: Writing OS image to disk ─────────────────────────────")

        if install_mode == "alongside":
            target_part = _state.get("target_partition", "")
            efi_part    = _state.get("efi_partition", "")
            alongside_mount = "/var/tmp/kyth-alongside-target"

            log(f"Target partition : {target_part}")
            log(f"EFI partition    : {efi_part or '(none detected)'}")

            subprocess.run(_as_root(["umount", "-l", target_part]), check=False, capture_output=True)
            subprocess.run(_as_root(["umount", "-Rl", alongside_mount]), check=False, capture_output=True)

            log(f"Formatting {target_part} as btrfs ...")
            run_cmd(["mkfs.btrfs", "-f", target_part], 5, 10)

            # Create btrfs subvolumes @ and @home
            log("Creating Btrfs subvolumes @ and @home ...")
            btrfs_temp_root = "/var/tmp/kyth-btrfs-root"
            subprocess.run(_as_root(["umount", "-l", btrfs_temp_root]), check=False, capture_output=True)
            Path(btrfs_temp_root).mkdir(parents=True, exist_ok=True)
            subprocess.run(_as_root(["mount", target_part, btrfs_temp_root]), check=True)
            try:
                subprocess.run(_as_root(["btrfs", "subvolume", "create", f"{btrfs_temp_root}/@"]), check=True)
                subprocess.run(_as_root(["btrfs", "subvolume", "create", f"{btrfs_temp_root}/@home"]), check=True)
            finally:
                subprocess.run(_as_root(["umount", "-l", btrfs_temp_root]), check=True)

            Path(alongside_mount).mkdir(parents=True, exist_ok=True)
            subprocess.run(_as_root(["mount", "-o", "subvol=@", target_part, alongside_mount]), check=True)
            progress(11)

            if efi_part:
                efi_mountpoint = Path(alongside_mount) / "boot" / "efi"
                efi_mountpoint.mkdir(parents=True, exist_ok=True)
                try:
                    current_efi_mnt = subprocess.check_output(
                        ["findmnt", "-n", "-o", "MOUNTPOINT", efi_part],
                        text=True, stderr=subprocess.DEVNULL, timeout=5,
                    ).strip()
                except Exception:
                    current_efi_mnt = ""
                if current_efi_mnt:
                    subprocess.run(
                        _as_root(["mount", "--bind", current_efi_mnt, str(efi_mountpoint)]),
                        check=True,
                    )
                    log(f"EFI bind-mounted from {current_efi_mnt}")
                else:
                    subprocess.run(
                        _as_root(["mount", efi_part, str(efi_mountpoint)]),
                        check=True,
                    )
                    log(f"EFI mounted from {efi_part}")

            install_cmd = [
                "bootc", "install", "to-filesystem",
                "--source-imgref", src_ref,
                "--target-imgref", tgt_ref,
                "--generic-image",
                "--acknowledge-destructive",
            ]
            if SKIP_FETCH_CHECK:
                install_cmd.append("--skip-fetch-check")
            install_cmd.append(alongside_mount)
            run_cmd(install_cmd, 12, 90)

            root_part = target_part

        else:
            unmount_target_disk(disk, log)
            install_cmd = [
                "bootc", "install", "to-disk",
                "--source-imgref", src_ref,
                "--target-imgref", tgt_ref,
                "--filesystem", "btrfs",
                "--generic-image",
                "--wipe",
            ]
            if SKIP_FETCH_CHECK:
                install_cmd.append("--skip-fetch-check")
            install_cmd.append(disk)
            run_cmd(install_cmd, 5, 90)
            root_part = get_root_partition(disk)

        log("── Phase 2: Configuring installed system ─────────────────────────")
        progress(91)

        if alongside_mount:
            config_root = alongside_mount
        else:
            config_root = "/var/tmp/kyth-install-root"
            Path(config_root).mkdir(parents=True, exist_ok=True)
            # Detach any stale mount left by a previously crashed install attempt.
            subprocess.run(_as_root(["umount", "-l", config_root]), check=False, capture_output=True)
            subprocess.run(_as_root(["mount", root_part, config_root]), check=True)

        progress(93)

        try:
            etc = find_deploy_etc(config_root)
            if etc:
                if install_mode == "alongside":
                    target_home = Path(config_root) / "ostree/deploy/default/var/home"
                    target_home.mkdir(parents=True, exist_ok=True)
                    subprocess.run(_as_root(["umount", "-l", str(target_home)]), check=False, capture_output=True)
                    subprocess.run(_as_root(["mount", "-o", "subvol=@home", target_part, str(target_home)]), check=True)

                    try:
                        uuid_out = subprocess.check_output(["blkid", "-s", "UUID", "-o", "value", target_part], text=True).strip()
                        if uuid_out:
                            fstab_path = Path(etc, "fstab")
                            fstab_line = f"UUID={uuid_out} /var/home btrfs subvol=@home,compress=zstd:1 0 0\n"
                            subprocess.run(
                                _as_root(["/usr/bin/tee", "-a", str(fstab_path)]),
                                input=fstab_line, text=True,
                                stdout=subprocess.DEVNULL, check=True
                            )
                            log(f"Fstab updated with Btrfs subvolume @home: {fstab_line.strip()}")
                    except Exception as fe:
                        log(f"Warning: failed to update fstab with @home subvolume: {fe}")
                subprocess.run(
                    _as_root(["/usr/bin/tee", str(Path(etc, "hostname"))]),
                    input=f"{_state['hostname']}\n", text=True,
                    stdout=subprocess.DEVNULL, check=True,
                )
                log(f"Hostname : {_state['hostname']}")

                subprocess.run(
                    _as_root(["ln", "-snf",
                              f"/usr/share/zoneinfo/{_state['timezone']}",
                              str(Path(etc, "localtime"))]),
                    check=True,
                )
                log(f"Timezone : {_state['timezone']}")
                progress(95)

                deploy_root = str(Path(etc).parent)
                ensure_system_accounts(deploy_root, log)

                username = _state.get("username", "").strip()
                password_hash = _state.get("password_hash", "")
                if username and password_hash:
                    log(f"Creating user: {username}")
                    try:
                        subprocess.run(
                            _as_root([
                                "useradd", "--root", deploy_root,
                                "-M", "-G", "wheel,video,audio,render",
                                "-s", "/bin/bash", username,
                            ]),
                            check=True,
                        )

                        shadow_path = f"{etc}/shadow"
                        cat_r = subprocess.run(
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
                        subprocess.run(
                            _as_root(["tee", shadow_path]),
                            input="".join(new_lines), text=True,
                            stdout=subprocess.DEVNULL, check=True,
                        )

                        uid, gid = "1000", "1000"
                        cat_r = subprocess.run(
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
                        subprocess.run(_as_root(["mkdir", "-p", str(var_home)]), check=True)
                        subprocess.run(_as_root(["chown", f"{uid}:{gid}", str(var_home)]), check=True)
                        subprocess.run(_as_root(["chmod", "700", str(var_home)]), check=True)

                        skel = Path(deploy_root) / "etc/skel"
                        if skel.exists():
                            subprocess.run(
                                _as_root(["cp", "-rT", str(skel), str(var_home)]),
                                check=True,
                            )
                            subprocess.run(
                                _as_root(["chown", "-R", f"{uid}:{gid}", str(var_home)]),
                                check=True,
                            )

                        subprocess.run(
                            _as_root(["restorecon", "-RF", str(var_home)]),
                            check=False,
                        )
                        log(f"User '{username}' created (uid={uid})")
                        ensure_system_accounts(deploy_root, log)
                        progress(97)
                    except Exception as ue:
                        log(f"Warning: user creation failed: {ue}")
                        log("You can create a user after first boot with: sudo useradd -m -G wheel USERNAME")
            else:
                log("Warning: deploy/etc not found — skipping post-install configuration")
        finally:
            subprocess.run(_as_root(["sync"]), check=False)
            progress(99)
            if alongside_mount:
                target_home = Path(alongside_mount) / "ostree/deploy/default/var/home"
                subprocess.run(_as_root(["umount", "-Rl", str(target_home)]), check=False, capture_output=True)
                subprocess.run(_as_root(["umount", "-Rl", alongside_mount]), check=False, capture_output=True)
            else:
                subprocess.run(_as_root(["umount", config_root]), check=False)

        log("── Phase 3: Staging Secure Boot enrollment ───────────────────────")
        mok_state = _try_stage_mok_enrollment(log, kernel, _state["mok_password"])

        progress(100)
        _push({"type": "done", "mok_state": mok_state})

    except Exception as exc:
        try:
            with LOG_FILE.open("a") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        _push({"type": "error", "message": str(exc)})
    finally:
        _state["password_hash"] = ""
        _state["mok_password"] = ""
        # Guard against orphaned mounts when Phase 1 fails before the inner
        # try/finally (which holds the normal umount) is ever entered.
        if alongside_mount:
            subprocess.run(_as_root(["umount", "-Rl", alongside_mount]), check=False, capture_output=True)
        _install_lock.release()

