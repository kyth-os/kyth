"""Validation and normalization of installer start requests."""
from __future__ import annotations

import re
import subprocess
from typing import TYPE_CHECKING

from . import config, disk, partition_ops, plan, system
from .context import InstallationState

if TYPE_CHECKING:
    from .context import InstallerContext


INSTALL_MODES = frozenset({"wipe", "alongside", "resize_ntfs", "free_space", "manual"})
USERNAME_PATTERN = re.compile(r"[a-z_][a-z0-9_-]{0,30}")
HOSTNAME_PATTERN = re.compile(r"[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?")


class InstallRequestError(ValueError):
    """A user-correctable error in an installation request."""


def _storage_state(body: dict, context: InstallerContext) -> tuple[dict, dict]:
    target_disk = body.get("disk", "")
    disks = {item["name"]: item for item in disk.list_disks()}
    if target_disk not in disks:
        raise InstallRequestError("Invalid disk.")

    mode = body.get("install_mode", "wipe")
    if mode not in INSTALL_MODES:
        mode = "wipe"
    target_partition = resize_partition = efi_partition = ""
    resize_gib = free_region_start = free_region_end = 0

    if mode == "alongside":
        target_partition = body.get("target_partition", "")
        if target_partition not in {part.get("name") for part in disk.list_partitions(target_disk)}:
            raise InstallRequestError("Invalid target partition.")
        efi_partition = body.get("efi_partition", "") or disk.find_efi_partition(target_disk)
    elif mode == "resize_ntfs":
        resize_partition = body.get("resize_partition") or body.get("target_partition", "")
        resize_gib = disk._safe_int(body.get("resize_gib") or body.get("shrink_gib") or 0)
        if resize_partition not in {part.get("name") for part in disk.list_partitions(target_disk)} or resize_gib < 32:
            raise InstallRequestError("Invalid NTFS resize target.")
        efi_partition = body.get("efi_partition", "") or disk.find_efi_partition(target_disk)
    elif mode == "free_space":
        free_region_start = disk._safe_int(body.get("free_region_start"), -1)
        free_region_end = disk._safe_int(body.get("free_region_end"), -1)
        valid_region = any(
            region["start_bytes"] <= free_region_start
            and region["end_bytes"] >= free_region_end
            for region in disk.list_free_space(target_disk)
        )
        if free_region_start < 0 or free_region_end <= free_region_start or not valid_region:
            raise InstallRequestError("Invalid free space region.")
        efi_partition = body.get("efi_partition", "") or disk.find_efi_partition(target_disk)
    elif mode == "manual":
        journal = partition_ops.get_journal(context)
        if not journal or not journal.committed:
            raise InstallRequestError("Partition changes must be committed before starting the install.")
        target_partition = journal.root_partition or ""
        if not target_partition:
            raise InstallRequestError("No root partition (/) configured in the manual partition layout.")
        efi_partition = body.get("efi_partition", "") or disk.find_efi_partition(target_disk)
    elif disks[target_disk].get("current") and not config._IS_LIVE_SESSION:
        raise InstallRequestError(
            "This is the disk running the current KythOS session.\n\n"
            "The running root filesystem cannot be unmounted, so reinstalling to this disk "
            "is only supported from the live ISO."
        )

    state = {
        "disk": target_disk,
        "install_mode": mode,
        "target_partition": target_partition,
        "resize_partition": resize_partition,
        "resize_gib": resize_gib,
        "free_region_start": free_region_start,
        "free_region_end": free_region_end,
        "efi_partition": efi_partition,
    }
    try:
        plan._validate_storage_intent(state, context)
    except RuntimeError as exc:
        raise InstallRequestError(str(exc)) from exc
    return state, disks[target_disk]


def validate_install_request(body: dict, context: InstallerContext) -> InstallationState:
    """Validate a start request and return the normalized installation state."""
    state, disk_info = _storage_state(body, context)
    current_ok = (
        state["install_mode"] == "alongside"
        or not disk_info.get("current")
        or bool(body.get("confirm_current"))
    )
    if not (body.get("confirm_backup") and body.get("confirm_erase") and current_ok):
        raise InstallRequestError("Please confirm the on-screen acknowledgements before starting the install.")

    try:
        password_hash = system._hash_password(body.get("password", ""))
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        raise InstallRequestError(f"Could not hash password: {exc}") from exc

    timezone = body.get("timezone", "UTC") or "UTC"
    if timezone not in set(system.list_timezones()):
        timezone = "UTC"
    username = body.get("username", "")
    if not USERNAME_PATTERN.fullmatch(username):
        raise InstallRequestError("Invalid username.")
    hostname = body.get("hostname", "kyth")
    if not HOSTNAME_PATTERN.fullmatch(hostname):
        raise InstallRequestError("Invalid hostname.")

    return {
        **state,
        "hostname": hostname,
        "timezone": timezone,
        "username": username,
        "password_hash": password_hash,
        "kernel": body.get("kernel", "fedora") or "fedora",
        "mok_password": body.get("mok_password", "") or "",
    }
