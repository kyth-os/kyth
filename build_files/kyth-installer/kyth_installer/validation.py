"""Validation and normalization of installer start requests."""
from __future__ import annotations

import re
import subprocess
from typing import TYPE_CHECKING

from . import config, disk, partition_ops, plan, system
from .context import InstallRequest

if TYPE_CHECKING:
    from .context import InstallerContext


INSTALL_MODES = frozenset({"wipe", "alongside", "resize_ntfs", "free_space", "manual"})
USERNAME_PATTERN = re.compile(r"[a-z_][a-z0-9_-]{0,30}")
HOSTNAME_PATTERN = re.compile(r"[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?")
LOCALE_PATTERN = re.compile(r"[A-Za-z0-9_.@-]{1,64}")
KEYMAP_PATTERN = re.compile(r"[A-Za-z0-9_.+@/-]{1,64}")


class InstallRequestError(ValueError):
    """A user-correctable error in an installation request."""


def _hash_password_for_request(password: str, *, allow_blank: bool = False) -> str:
    """Hash `password`, wrapping hashing failures as InstallRequestError.

    If allow_blank, a blank password hashes to "" instead of being passed
    through to system._hash_password (which rejects empty input) — used by
    the CLI path, where a blank password means "don't create an admin user"."""
    if allow_blank and not password:
        return ""
    try:
        return system._hash_password(password)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        raise InstallRequestError(f"Could not hash password: {exc}") from exc


def _require_valid_hostname(hostname: str) -> None:
    if not HOSTNAME_PATTERN.fullmatch(hostname):
        raise InstallRequestError("Invalid hostname.")


def _require_valid_username(username: str, *, required: bool = True) -> None:
    if not required and not username:
        return
    if not USERNAME_PATTERN.fullmatch(username):
        raise InstallRequestError("Invalid username.")


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


def validate_install_request(body: dict, context: InstallerContext) -> InstallRequest:
    """Validate a start request and return an immutable normalized request."""
    state, disk_info = _storage_state(body, context)
    current_ok = (
        state["install_mode"] == "alongside"
        or not disk_info.get("current")
        or bool(body.get("confirm_current"))
    )
    if not (body.get("confirm_backup") and body.get("confirm_erase") and current_ok):
        raise InstallRequestError("Please confirm the on-screen acknowledgements before starting the install.")

    password_hash = _hash_password_for_request(body.get("password", ""))

    timezone = body.get("timezone", "UTC") or "UTC"
    if timezone not in set(system.list_timezones()):
        timezone = "UTC"
    locale = str(body.get("locale") or "en_US.UTF-8")
    if not LOCALE_PATTERN.fullmatch(locale) or locale not in set(system.list_locales()):
        locale = "en_US.UTF-8"
    keymap = str(body.get("keymap") or "us")
    if not KEYMAP_PATTERN.fullmatch(keymap) or keymap not in set(system.list_keymaps()):
        keymap = "us"
    username = body.get("username", "")
    _require_valid_username(username)
    hostname = body.get("hostname", "kyth")
    _require_valid_hostname(hostname)

    return InstallRequest.from_state({
        **state,
        "hostname": hostname,
        "timezone": timezone,
        "locale": locale,
        "keymap": keymap,
        "username": username,
        "password_hash": password_hash,
        "kernel": body.get("kernel", "fedora") or "fedora",
        "mok_password": body.get("mok_password", "") or "",
    })


def validate_partition_install_request(
    *,
    target_partition: str,
    efi_partition: str,
    hostname: str,
    timezone: str,
    username: str,
    password: str,
    context: InstallerContext,
) -> InstallRequest:
    """Normalize the blank-partition CLI request through installer policy."""
    target = disk._normal_device_path(target_partition)
    if not target:
        raise InstallRequestError("Invalid target partition.")
    target_disk = disk._parent_disk(target)
    if not target_disk:
        raise InstallRequestError(
            f"Could not determine parent disk for {target_partition}."
        )
    if efi_partition:
        normalized_efi = disk._normal_device_path(efi_partition)
        if not normalized_efi:
            raise InstallRequestError("Invalid EFI partition.")
        if normalized_efi == target:
            raise InstallRequestError(
                "EFI partition and target partition must be different."
            )
        efi_disk = disk._parent_disk(normalized_efi)
        efi_info = next(
            (
                part
                for part in disk.list_partitions(efi_disk)
                if part.get("name") == normalized_efi
            ),
            None,
        )
        if not efi_info or not efi_info.get("efi"):
            raise InstallRequestError(
                "The selected EFI partition is not an EFI System Partition."
            )
        efi_partition = normalized_efi

    state, _disk_info = _storage_state(
        {
            "disk": target_disk,
            "install_mode": "alongside",
            "target_partition": target,
            "efi_partition": efi_partition,
        },
        context,
    )
    _require_valid_hostname(hostname)
    if timezone not in set(system.list_timezones()):
        raise InstallRequestError(f"Invalid timezone: {timezone}")
    _require_valid_username(username, required=False)
    if bool(username) != bool(password):
        raise InstallRequestError(
            "An admin username and password must either both be supplied or both be blank."
        )
    password_hash = _hash_password_for_request(password, allow_blank=True)

    return InstallRequest.from_state({
        **state,
        "hostname": hostname,
        "timezone": timezone,
        "locale": "en_US.UTF-8",
        "keymap": "us",
        "username": username,
        "password_hash": password_hash,
        "kernel": "fedora",
        "mok_password": "",
    })
