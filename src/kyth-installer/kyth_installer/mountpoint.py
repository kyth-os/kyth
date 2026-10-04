"""Validation for user-selected manual filesystem mount points."""

from __future__ import annotations


def normalize_manual_mountpoint(value: object) -> str:
    """Return a safe fstab mount point or reject paths outside the target root."""
    if not isinstance(value, str):
        raise ValueError("Mount point must be text.")
    mountpoint = value.strip()
    if mountpoint == "":
        return mountpoint
    if mountpoint == "swap":
        return mountpoint
    if (
        not mountpoint
        or not mountpoint.startswith("/")
        or ".." in mountpoint
        or "//" in mountpoint
        or any(component == "." for component in mountpoint.split("/"))
        or not mountpoint.isascii()
        or not all(
            char.isalnum() or char in "/._+:-"
            for char in mountpoint
        )
    ):
        raise ValueError("Mount point must be an absolute path without traversal or unsupported characters.")
    if len(mountpoint) > 1:
        mountpoint = mountpoint.rstrip("/")
    return mountpoint
