"""Fstab writing and additional filesystem mount configuration."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .compat import phase_dependency


def fsck_pass_for(fstype: str) -> int:
    """Return the non-root fstab fsck pass for ``fstype``."""
    return 0 if fstype in ("linux-swap", "btrfs") else 2


def append_fstab_line(
    etc, fstab_line: str, log, description: str, *, format_error,
) -> bool:
    """Append one target fstab line without making optional mounts fatal."""
    run_command = phase_dependency("run_command")
    as_root = phase_dependency("_as_root")
    fstab_path = Path(etc, "fstab")
    try:
        run_command(
            as_root(["/usr/bin/tee", "-a", str(fstab_path)]),
            input=fstab_line, text=True, stdout=subprocess.DEVNULL, check=True,
        )
    except OSError as exc:
        log(f"Warning: failed to update fstab for {description}: {format_error(exc, path=fstab_path)}")
        return False
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
        log(f"Warning: failed to update fstab for {description}: {exc}")
        return False
    log(f"Fstab updated for {description}: {fstab_line.strip()}")
    return True


def configure_alongside_fstab(
    config_root, target_part, etc, log, *, uuid_lookup, append_line,
) -> None:
    """Mount and persist the alongside target's ``@home`` subvolume."""
    run_command = phase_dependency("run_command")
    as_root = phase_dependency("_as_root")
    safe_umount = phase_dependency("_safe_umount")
    target_home = Path(config_root) / "ostree/deploy/default/var/home"
    run_command(as_root(["mkdir", "-p", str(target_home)]), check=True)
    safe_umount(run_command, str(target_home))
    run_command(
        as_root(["mount", "-o", "subvol=@home", target_part, str(target_home)]),
        check=True,
    )
    uuid_out = uuid_lookup(target_part, log)
    if uuid_out is None:
        return
    line = f"UUID={uuid_out} /var/home btrfs subvol=@home,compress=zstd:1 0 0\n"
    append_line(etc, line, log, "@home subvolume")


def configure_manual_mounts(
    config_root, etc, log, context, *, uuid_lookup, append_line,
) -> None:
    """Mount manually configured filesystems and persist their fstab rows."""
    run_command = phase_dependency("run_command")
    as_root = phase_dependency("_as_root")
    safe_umount = phase_dependency("_safe_umount")
    get_manual_mounts = phase_dependency("_get_manual_mounts")
    for mount in get_manual_mounts(context):
        part = mount["partition"]
        mountpoint = mount["mountpoint"]
        fstype = mount["fstype"]
        try:
            uuid_out = uuid_lookup(part, log)
            if uuid_out is None:
                log(f"Warning: skipping fstab entry for {mountpoint} ({part}) — no UUID")
                continue
            fstab_mountpoint = "/var/home" if mountpoint == "/home" else mountpoint
            target_path = Path(config_root) / fstab_mountpoint.lstrip("/")
            if fstype == "linux-swap":
                line = f"UUID={uuid_out} none swap defaults 0 {fsck_pass_for(fstype)}\n"
            else:
                options = "defaults,compress=zstd:1" if fstype == "btrfs" else "defaults"
                line = f"UUID={uuid_out} {fstab_mountpoint} {fstype} {options} 0 {fsck_pass_for(fstype)}\n"
                run_command(as_root(["mkdir", "-p", str(target_path)]), check=False)
                safe_umount(run_command, str(target_path))
            if not append_line(etc, line, log, f"{part} at {mountpoint}"):
                continue
            if fstype != "linux-swap":
                run_command(as_root(["mount", part, str(target_path)]), check=False)
            log(f"Manual mount: {part} at {mountpoint} ({fstype})")
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
            log(f"Warning: failed to configure manual mount {part} at {mountpoint}: {exc}")
