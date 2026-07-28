"""Filesystem-aware partition shrinking.

parted (and services.disk_service.DiskService.resize_partition) only move a
partition table boundary — they never touch the filesystem living inside it.
Calling resizepart on a partition that still has a filesystem larger than
the new boundary corrupts it immediately. Every code path that shrinks an
already-formatted partition (the guided "Shrink NTFS & Install" flow in
plan.py, and the manual partition editor's "Resize" operation in
partition_ops.py) must shrink the filesystem first through this module, then
move the partition boundary after.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from .runner import run_command
from .streaming import StreamingCommandRunner
from .system import _as_root

_runner = StreamingCommandRunner(rx_bytes=lambda: 0, publish=lambda _event: None)


def _stream(argv, log, *, input=None, timeout=1800, error_factory=None):
    """Run argv as root with output streamed live to log().

    ntfsresize/resize2fs/btrfs print live percentage progress as they work;
    without streaming that output sits fully buffered until the (potentially
    many-minutes-long) command exits, leaving the install log silent.
    """
    _runner.run(
        _as_root(argv), 0, 0, log, lambda _pct: None,
        stall_timeout=timeout, absolute_timeout=timeout,
        error_factory=error_factory, input=input,
    )


def _require_tools(*tools: str) -> None:
    missing = [tool for tool in tools if shutil.which(tool) is None]
    if missing:
        raise RuntimeError(
            f"Required resize tools are missing from the live environment: {', '.join(missing)}"
        )


def _shrink_ntfs(partition: str, new_size_bytes: int, log) -> None:
    _require_tools("ntfsresize")

    log("Checking NTFS resize safety...")
    _stream(
        ["ntfsresize", "--check", partition], log, timeout=240,
        error_factory=lambda *_: RuntimeError(
            "Windows left this NTFS volume in an unsafe state. Disable Fast "
            "Startup and hibernation, run chkdsk in Windows, then try again."
        ),
    )
    _stream(
        ["ntfsresize", "--info", partition], log, timeout=120,
        error_factory=lambda *_: RuntimeError(
            "NTFS partition is not clean enough to resize. Boot Windows, "
            "disable Fast Startup/hibernation, run chkdsk, and try again."
        ),
    )

    size_arg = str(new_size_bytes)

    def _dry_run_error(_returncode, recent_output, _argv):
        out = "\n".join(recent_output).lower()
        if "too small" in out or "not enough space" in out:
            return RuntimeError(
                "NTFS shrink failed: Not enough free space on the NTFS "
                "partition to shrink it by the requested amount."
            )
        if "immovable" in out:
            return RuntimeError(
                "NTFS shrink failed: Immovable files prevent shrinking this "
                "partition further. Boot Windows, defragment the drive, and try again."
            )
        return RuntimeError(
            "NTFS resize dry-run failed. Boot Windows, shrink the volume "
            "there, then return to the installer.\nOutput:\n" + "\n".join(recent_output)
        )

    _stream(
        ["ntfsresize", "--no-action", "--size", size_arg, partition], log,
        timeout=240, error_factory=_dry_run_error,
    )

    log("Shrinking NTFS filesystem...")
    _stream(
        ["ntfsresize", "--size", size_arg, partition], log,
        input="y\n", timeout=1800,
        error_factory=lambda _rc, recent_output, _argv: RuntimeError(
            "NTFS filesystem resize failed before the partition boundary was "
            "changed. Output:\n" + "\n".join(recent_output)
        ),
    )


def _shrink_ext(partition: str, new_size_bytes: int, log) -> None:
    _require_tools("e2fsck", "resize2fs")

    log("Checking ext filesystem before resize...")
    # e2fsck's exit-code convention: 0 = clean, 1 = errors corrected, 2 =
    # errors corrected + reboot needed (never applies here — the target
    # partition is unmounted), 4+ = uncorrected errors or a hard failure.
    # Only >=4 means "unsafe to proceed"; run via plain run_command (not
    # streamed) since e2fsck's own output is a short summary, not a
    # long-running progress stream like resize2fs below.
    check = run_command(
        _as_root(["e2fsck", "-f", "-y", partition]),
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600,
    )
    if check.returncode >= 4:
        raise RuntimeError(
            "This ext filesystem has uncorrectable errors. Boot into Linux "
            "and run 'fsck -f' on it manually, then try again.\n"
            f"Output:\n{check.stdout}"
        )

    log("Shrinking ext filesystem...")
    size_kib = max(1, new_size_bytes // 1024)
    _stream(
        ["resize2fs", partition, f"{size_kib}K"], log, timeout=1800,
        error_factory=lambda _rc, recent_output, _argv: RuntimeError(
            "ext filesystem resize failed before the partition boundary was "
            "changed. Output:\n" + "\n".join(recent_output)
        ),
    )


def _shrink_btrfs(partition: str, new_size_bytes: int, log) -> None:
    _require_tools("btrfs", "mount", "umount")
    mount_point = tempfile.mkdtemp(prefix="kyth-btrfs-resize-")
    try:
        log(f"Mounting {partition} to shrink its Btrfs filesystem...")
        run_command(_as_root(["mount", partition, mount_point]), check=True, timeout=30)
        try:
            log("Shrinking Btrfs filesystem...")
            _stream(
                ["btrfs", "filesystem", "resize", str(new_size_bytes), mount_point], log,
                timeout=1800,
                error_factory=lambda _rc, recent_output, _argv: RuntimeError(
                    "Btrfs filesystem resize failed before the partition boundary "
                    "was changed. Output:\n" + "\n".join(recent_output)
                ),
            )
        finally:
            run_command(_as_root(["umount", mount_point]), check=False, timeout=30)
    finally:
        try:
            Path(mount_point).rmdir()
        except OSError:
            pass


def shrink_filesystem(partition: str, fstype: str, new_size_bytes: int, log) -> None:
    """Shrink the filesystem on `partition` to `new_size_bytes` in place.

    Must run before any partition-table boundary change (parted resizepart)
    — parted only moves the table entry, it never touches filesystem
    metadata, so calling it first on a still-larger filesystem corrupts it.
    Raises for any filesystem type without a safe, supported shrink path
    (fail closed rather than silently truncating an unsupported filesystem).
    """
    fstype = (fstype or "").lower()
    if fstype == "bitlocker":
        raise RuntimeError(
            "This partition is BitLocker-encrypted and cannot be resized "
            "while locked. In Windows, suspend or disable BitLocker "
            "protection (Control Panel > BitLocker Drive Encryption, or "
            "'manage-bde -off C:'), wait for decryption to finish, then try again."
        )
    if fstype in ("ntfs", "ntfs3"):
        _shrink_ntfs(partition, new_size_bytes, log)
    elif fstype in ("ext2", "ext3", "ext4"):
        _shrink_ext(partition, new_size_bytes, log)
    elif fstype == "btrfs":
        _shrink_btrfs(partition, new_size_bytes, log)
    else:
        raise RuntimeError(
            f"Shrinking {fstype or 'this'} filesystems is not supported by "
            "this installer. Back up the partition, delete it, and recreate "
            "it at the smaller size instead."
        )
