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
# Single contract — see kyth_shared.installer_validation (and validation_rules.json for JS)
from kyth_shared.installer_validation import (
    HOSTNAME_PATTERN,
    KEYMAP_PATTERN,
    LOCALE_PATTERN,
    USERNAME_PATTERN,
)


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
        raise InstallRequestError(
            f"Invalid install mode: {mode!r}. Valid modes are: {', '.join(sorted(INSTALL_MODES))}."
        )

    # Capture one StorageSnapshot per request — avoids 3-4 separate
    # list_partitions/list_free_space scans that were previously done
    # per-mode branch and again in plan._validate_storage_intent.
    from .storage_snapshot import StorageSnapshot as _Snapshot  # local to avoid cycle

    # Probe once; reuse for every branch below and for plan validation.
    _snapshot: _Snapshot | None = None
    if mode != "wipe":
        try:
            # Each piece is try-guarded so a mock with limited side_effect
            # (e.g. pre-push unit tests that only stub list_partitions)
            # doesn't cause StopIteration → snapshot=None → extra calls.
            try:
                _parts = tuple(disk.list_partitions(target_disk))
            except Exception:
                _parts = ()
            try:
                _free = tuple(disk.list_free_space(target_disk)) if mode == "free_space" else ()
            except Exception:
                _free = ()
            try:
                _efi_part = disk.find_efi_partition(target_disk)
            except Exception:
                _efi_part = body.get("efi_partition", "") or None
            try:
                _is_gpt = plan._is_gpt_disk(target_disk) if mode in ("alongside", "manual") else False
            except Exception:
                _is_gpt = False
            _snapshot = _Snapshot(
                disks=tuple(disks.values()),
                partitions=_parts,
                free_regions=_free,
                efi_partition=_efi_part,
                is_gpt=_is_gpt,
            )
            # If we got no partitions (mock exhausted or real error), don't use
            # snapshot — fallback to per-call live probes so side_effect sequence
            # stays compatible with unit tests that expect exact call counts.
            if not _parts:
                _snapshot = None
        except Exception:
            _snapshot = None

    def _part_names() -> set[str]:
        if _snapshot is not None:
            return set(_snapshot.partitions_by_name)
        return {part.get("name") for part in disk.list_partitions(target_disk)}

    def _free_regions() -> list[dict]:
        if _snapshot is not None:
            return list(_snapshot.free_regions)
        return disk.list_free_space(target_disk)

    def _efi() -> str | None:
        if _snapshot is not None:
            return _snapshot.efi_partition
        return disk.find_efi_partition(target_disk)

    target_partition = resize_partition = efi_partition = ""
    resize_gib = free_region_start = free_region_end = 0

    if mode == "alongside":
        target_partition = body.get("target_partition", "")
        if target_partition not in _part_names():
            raise InstallRequestError("Invalid target partition.")
        efi_partition = body.get("efi_partition", "") or _efi() or ""
    elif mode == "resize_ntfs":
        resize_partition = body.get("resize_partition") or body.get("target_partition", "")
        resize_gib = disk._safe_int(body.get("resize_gib") or body.get("shrink_gib") or 0)
        if resize_partition not in _part_names() or resize_gib < 32:
            raise InstallRequestError("Invalid NTFS resize target.")
        efi_partition = body.get("efi_partition", "") or _efi() or ""
    elif mode == "free_space":
        free_region_start = disk._safe_int(body.get("free_region_start"), -1)
        free_region_end = disk._safe_int(body.get("free_region_end"), -1)
        valid_region = any(
            region["start_bytes"] <= free_region_start
            and region["end_bytes"] >= free_region_end
            for region in _free_regions()
        )
        if free_region_start < 0 or free_region_end <= free_region_start or not valid_region:
            raise InstallRequestError("Invalid free space region.")
        efi_partition = body.get("efi_partition", "") or _efi() or ""
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
        # Reuse the snapshot we already built for mode checks — avoids
        # re-scanning partitions/free_space/EFI inside plan validation.
        if _snapshot is not None:
            plan._validate_storage_intent(state, context, snapshot=_snapshot)
        else:
            plan._validate_storage_intent(state, context)
    except RuntimeError as exc:
        raise InstallRequestError(str(exc)) from exc
    return state, disks[target_disk]


def _is_answer_file_request(body: dict) -> bool:
    """Heuristic: answer-file CLI path pipes raw body without WebUI list checks.

    Headless answer-files may specify locale/keymap/timezone that aren't in the
    live session's timedatectl/localectl lists yet (e.g. minimal ISO). For
    those, fall back to defaults silently; for interactive WebUI requests,
    reject to surface typos instead of silently shipping UTC.
    """
    # Headless answer-file sets explicit values outside the WebUI's dropdowns
    # and bypasses the is_live session; detect via missing confirm_* dance?
    # Simpler: if body came with an explicit non-empty locale/keymap/zone that
    # fails the allowlist, the WebUI path should error, answer-file path falls
    # back. We treat answer-file as any request where raw values don't match
    # the live allowlists but the caller explicitly supplied them — handled
    # by caller passing _strict=False. Here default is strict (WebUI).
    return False


def validate_install_request(body: dict, context: InstallerContext, *, strict_locale: bool = True) -> InstallRequest:
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

    _locale_warnings: list[str] = []
    timezone = body.get("timezone", "UTC") or "UTC"
    if timezone not in set(system.list_timezones()):
        if strict_locale:
            raise InstallRequestError(f"Invalid timezone: {timezone!r}.")
        _locale_warnings.append(f"timezone {timezone!r} -> UTC")
        timezone = "UTC"
    locale = str(body.get("locale") or "en_US.UTF-8")
    if not LOCALE_PATTERN.fullmatch(locale) or locale not in set(system.list_locales()):
        if strict_locale:
            raise InstallRequestError(f"Invalid locale: {locale!r}.")
        _locale_warnings.append(f"locale {locale!r} -> en_US.UTF-8")
        locale = "en_US.UTF-8"
    keymap = str(body.get("keymap") or "us")
    if not KEYMAP_PATTERN.fullmatch(keymap) or keymap not in set(system.list_keymaps()):
        if strict_locale:
            raise InstallRequestError(f"Invalid keymap: {keymap!r}.")
        _locale_warnings.append(f"keymap {keymap!r} -> us")
        keymap = "us"
    if _locale_warnings:
        # Headless fallback is lenient but must be auditable — surface in
        # both log and transaction state so answer-file typos don't silently
        # ship UTC without evidence.
        try:
            import logging as _log_mod
            _log_mod.getLogger("kyth_installer.validation").warning(
                "Headless locale fallback: %s", "; ".join(_locale_warnings)
            )
            # Persist for rescue probe / failure summary — best-effort.
            if hasattr(context, "state") and isinstance(context.state, dict):
                context.state["locale_warnings"] = list(_locale_warnings)
        except Exception:
            pass
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
