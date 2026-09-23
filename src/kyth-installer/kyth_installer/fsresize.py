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

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .runner import run_command
from .streaming import StreamingCommandRunner
from .system import _as_root

NTFS_GUIDANCE = (
    "Windows left this NTFS volume in an unsafe state. For a smooth switch, "
    "boot Windows → Settings → Power → disable Fast Startup and hibernation, "
    "run chkdsk /f, then return to KythOS to retry."
)

_runner = StreamingCommandRunner(rx_bytes=lambda: 0, publish=lambda _event: None)
_DISK_HELPER = ["kyth-installer-exec", "--operation", "disk"]
_STREAM_HELPER = ["kyth-installer-exec", "--operation", "stream"]


def _stream(argv, log, *, stdin_data=None, timeout=1800, error_factory=None, cancel_event=None):
    """Run argv as root with output streamed live to log().

    ntfsresize/resize2fs/btrfs print live percentage progress as they work;
    without streaming that output sits fully buffered until the (potentially
    many-minutes-long) command exits, leaving the install log silent.

    cancel_event (a threading.Event, usually context.cancel_requested) is
    polled by the runner: Cancel during a shrink stops at the next poll
    instead of running up to 30 minutes to completion.
    """
    _runner.run(
        _as_root(argv), 0, 0, log, lambda _pct: None,
        stall_timeout=timeout, absolute_timeout=timeout,
        error_factory=error_factory, stdin_data=stdin_data,
        cancel_event=cancel_event,
    )


def _stream_typed(payload, log, *, timeout=1800, error_factory=None, cancel_event=None):
    """Stream one validated filesystem operation through the Rust helper."""
    _stream(
        _STREAM_HELPER,
        log,
        stdin_data=json.dumps(
            {"kind": "disk", "request": payload},
            separators=(",", ":"),
        ),
        timeout=timeout,
        error_factory=error_factory,
        cancel_event=cancel_event,
    )


def _check_cancelled(cancel_event, stage: str) -> None:
    """Raise between shrink stages so Cancel lands before the next
    destructive step (never mid-ntfsresize) with a distinct message."""
    if cancel_event is not None and cancel_event.is_set():
        from .execution import InstallCancelled
        raise InstallCancelled(
            f"Installation cancelled by user {stage}."
        )


def _run_typed(payload, *, timeout, **kwargs):
    """Run one validated filesystem operation through the Rust helper."""
    return run_command(
        _as_root(_DISK_HELPER),
        input=json.dumps(payload, separators=(",", ":")),
        text=True,
        timeout=timeout,
        **kwargs,
    )


def ntfs_filesystem_size_bytes(partition: str, *, timeout: int = 120) -> int | None:
    """Return the live NTFS filesystem size on `partition`.

    Parses `ntfsresize --info` ("Current volume size: N bytes") through the
    validated disk helper. Returns None only when the probe could not be
    attempted at all (helper missing/broken) or its output is unparsable —
    in both cases the caller falls back to the in-session `/run` marker.
    But a nonzero exit means ntfsresize REFUSED to read the volume (dirty,
    hibernated, damaged) and that raises: those are exactly the volumes
    that must not be shrunk, and swallowing the signal would let a retry
    double-shrink with no marker and no probe.
    """
    import re as _re

    try:
        proc = _run_typed(
            {"operation": "filesystem_resize", "device": partition, "fs": "ntfs",
             "new_size_bytes": 1, "stage": "info"},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
        )
    except (OSError, ValueError, RuntimeError):
        return None
    if proc.returncode != 0:
        raise RuntimeError(
            f"ntfsresize --info refused to read {partition} (exit {proc.returncode}): "
            f"the volume is likely dirty, hibernated, or damaged. "
            f"Output: {(proc.stdout or '')[:500]}"
        )
    match = _re.search(r"Current volume size:\s*(\d+)\s*bytes", proc.stdout or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _require_tools(*tools: str) -> None:
    missing = [tool for tool in tools if shutil.which(tool) is None]
    if missing:
        raise RuntimeError(
            f"Required resize tools are missing from the live environment: {', '.join(missing)}"
        )


def _shrink_ntfs(partition: str, new_size_bytes: int, log, *, cancel_event=None) -> None:
    _require_tools("ntfsresize")

    log("Checking NTFS resize safety...")
    _stream_typed(
        {"operation": "filesystem_resize", "device": partition, "fs": "ntfs",
         "new_size_bytes": new_size_bytes, "stage": "check"},
        log, timeout=240,
        error_factory=lambda *_: RuntimeError(NTFS_GUIDANCE),
        cancel_event=cancel_event,
    )
    _stream_typed(
        {"operation": "filesystem_resize", "device": partition, "fs": "ntfs",
         "new_size_bytes": new_size_bytes, "stage": "info"},
        log, timeout=120,
        error_factory=lambda *_: RuntimeError(NTFS_GUIDANCE),
        cancel_event=cancel_event,
    )

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

    _stream_typed(
        {"operation": "filesystem_resize", "device": partition, "fs": "ntfs",
         "new_size_bytes": new_size_bytes, "stage": "dry_run"},
        log,
        timeout=240, error_factory=_dry_run_error,
        cancel_event=cancel_event,
    )

    _check_cancelled(cancel_event, "before the NTFS filesystem resize started")
    log("Shrinking NTFS filesystem...")
    _stream_typed(
        {"operation": "filesystem_resize", "device": partition, "fs": "ntfs",
         "new_size_bytes": new_size_bytes, "stage": "resize"},
        log, timeout=1800,
        error_factory=lambda _rc, recent_output, _argv: RuntimeError(
            "NTFS filesystem resize failed before the partition boundary was "
            "changed. Output:\n" + "\n".join(recent_output)
        ),
        cancel_event=cancel_event,
    )


def _shrink_ext(partition: str, new_size_bytes: int, log, *, cancel_event=None) -> None:
    _require_tools("e2fsck", "resize2fs")

    log("Checking ext filesystem before resize...")
    # e2fsck's exit-code convention: 0 = clean, 1 = errors corrected, 2 =
    # errors corrected + reboot needed (never applies here — the target
    # partition is unmounted), 4+ = uncorrected errors or a hard failure.
    # Only >=4 means "unsafe to proceed"; run via plain run_command (not
    # streamed) since e2fsck's own output is a short summary, not a
    # long-running progress stream like resize2fs below.
    check = _run_typed(
        {"operation": "filesystem_check", "device": partition},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600,
    )
    if check.returncode >= 4:
        raise RuntimeError(
            "This ext filesystem has uncorrectable errors. Boot into Linux "
            "and run 'fsck -f' on it manually, then try again.\n"
            f"Output:\n{check.stdout}"
        )

    _check_cancelled(cancel_event, "before the ext filesystem resize started")
    log("Shrinking ext filesystem...")
    _stream_typed(
        {"operation": "filesystem_resize", "device": partition, "fs": "ext4",
         "new_size_bytes": new_size_bytes, "stage": "resize"},
        log, timeout=1800,
        error_factory=lambda _rc, recent_output, _argv: RuntimeError(
            "ext filesystem resize failed before the partition boundary was "
            "changed. Output:\n" + "\n".join(recent_output)
        ),
        cancel_event=cancel_event,
    )


def _shrink_btrfs(partition: str, new_size_bytes: int, log, *, cancel_event=None, register_mount=None, release_mount=None) -> None:
    """Shrink a Btrfs filesystem via a tracked temp mount.

    register_mount/release_mount (usually context.register_mount /
    context.release_mount) make the temp mount visible to the global
    cleanup and cancel paths: without them a failed resize + failed
    unmount (or a mid-resize death) leaves an invisible mount that later
    steps trip over as "device busy" while retries leak more mounts.
    """
    _require_tools("btrfs", "mount", "umount")
    mount_point = tempfile.mkdtemp(prefix="kyth-btrfs-resize-")
    registered = False
    try:
        log(f"Mounting {partition} to shrink its Btrfs filesystem...")
        _run_typed(
            {"operation": "mount_filesystem", "device": partition, "mountpoint": mount_point},
            check=True, timeout=30,
        )
        if register_mount is not None:
            register_mount(mount_point)
            registered = True
        _check_cancelled(cancel_event, "before the Btrfs filesystem resize started")
        try:
            log("Shrinking Btrfs filesystem...")
            _stream_typed(
                {"operation": "filesystem_resize", "device": mount_point, "fs": "btrfs",
                 "new_size_bytes": new_size_bytes, "stage": "resize"},
                log,
                timeout=1800,
                error_factory=lambda _rc, recent_output, _argv: RuntimeError(
                    "Btrfs filesystem resize failed before the partition boundary "
                    "was changed. Output:\n" + "\n".join(recent_output)
                ),
                cancel_event=cancel_event,
            )
        finally:
            unmounted = _run_typed(
                {"operation": "unmount_filesystem", "mountpoint": mount_point},
                check=False, timeout=30,
            )
            if getattr(unmounted, "returncode", 0) != 0:
                # Busy mount: lazy-detach so the mountpoint goes away now
                # and the kernel releases it when the last user exits,
                # instead of leaking a busy mount for later steps to trip on.
                _run_typed(
                    {"operation": "unmount_filesystem", "mountpoint": mount_point,
                     "lazy": True},
                    check=False, timeout=30,
                )
            if release_mount is not None and registered:
                release_mount(mount_point)
                registered = False
    finally:
        if release_mount is not None and registered:
            release_mount(mount_point)
        try:
            Path(mount_point).rmdir()
        except OSError as exc:
            log(f"Warning: could not remove temp mount dir {mount_point}: {exc}")


def validate_shrink_request(partition: str, fstype: str) -> None:
    """Run last-moment power, encryption, and filesystem safety guards."""
    from .assurance import _battery_check, _encryption_check

    # Power probe is advisory: a broken probe (VMs, exotic ACPI) must not
    # brick installs. Encryption is the opposite — unknown state blocks.
    try:
        _battery_check()
    except (OSError, ValueError, AttributeError, KeyError) as exc:
        import logging as _lg

        _lg.getLogger(__name__).debug("fsresize battery probe failed: %s", exc, exc_info=True)
    from .disk import _parent_disk

    try:
        parent = _parent_disk(partition) or partition
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):
        parent = partition
    # Fail closed: if the encryption probe itself breaks (lsblk/blkid
    # unavailable), the volume's BitLocker/LUKS state is UNKNOWN — and the
    # explicit bitlocker gate below can only fire when detection worked.
    # Shrinking a locked volume corrupts it, so an unverifiable probe is a
    # blocker, not a debug log line.
    try:
        enc = _encryption_check(disk=parent)
    except (OSError, ValueError, AttributeError, KeyError) as exc:
        raise RuntimeError(
            f"Could not verify the encryption state of {parent}; "
            f"refusing to shrink blind ({exc})."
        )
    if enc is not None and enc.status == "warn":
        raise RuntimeError(enc.detail)
    fstype = (fstype or "").lower()
    if fstype == "bitlocker":
        raise RuntimeError(
            "This partition is BitLocker-encrypted and cannot be resized "
            "while locked. In Windows, suspend or disable BitLocker "
            "protection (Control Panel > BitLocker Drive Encryption, or "
            "'manage-bde -off C:'), wait for decryption to finish, then try again."
        )


def shrink_filesystem(partition: str, fstype: str, new_size_bytes: int, log, *, cancel_event=None, register_mount=None, release_mount=None) -> None:
    """Shrink the filesystem on `partition` to `new_size_bytes` in place.

    Must run before any partition-table boundary change (parted resizepart)
    — parted only moves the table entry, it never touches filesystem
    metadata, so calling it first on a still-larger filesystem corrupts it.
    Raises for any filesystem type without a safe, supported shrink path
    (fail closed rather than silently truncating an unsupported filesystem).
    """
    _check_cancelled(cancel_event, "before the filesystem shrink started")
    validate_shrink_request(partition, fstype)
    fstype = (fstype or "").lower()
    if fstype in ("ntfs", "ntfs3"):
        _shrink_ntfs(partition, new_size_bytes, log, cancel_event=cancel_event)
    elif fstype in ("ext2", "ext3", "ext4"):
        _shrink_ext(partition, new_size_bytes, log, cancel_event=cancel_event)
    elif fstype == "btrfs":
        _shrink_btrfs(partition, new_size_bytes, log, cancel_event=cancel_event, register_mount=register_mount, release_mount=release_mount)
    else:
        raise RuntimeError(
            f"Shrinking {fstype or 'this'} filesystems is not supported by "
            "this installer. Back up the partition, delete it, and recreate "
            "it at the smaller size instead."
        )
