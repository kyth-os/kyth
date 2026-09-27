"""Interactive blank-partition installer backed by the installer service layer."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Callable, Sequence

from . import disk, install, system
from .context import InstallLifecycle, InstallerContext
from .execution import start_installation
from .validation import InstallRequestError, validate_partition_install_request

CONFIRMATION = "install kythos"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kyth-partition-install",
        description=(
            "Install KythOS into an existing blank partition without resizing "
            "or deleting neighboring partitions."
        ),
    )
    parser.add_argument("target_partition", help="blank partition to format and install to")
    parser.add_argument(
        "efi_partition",
        nargs="?",
        default="",
        help="EFI System Partition to reuse (auto-detected when omitted)",
    )
    return parser


def _prompt_identity(
    *,
    input_fn: Callable[[str], str],
    password_fn: Callable[[str], str],
) -> tuple[str, str, str, str]:
    default_hostname = os.environ.get("KYTH_HOSTNAME", "kyth")
    default_timezone = os.environ.get("KYTH_TIMEZONE", "UTC")
    hostname = input_fn(f"Hostname [{default_hostname}]: ").strip() or default_hostname
    timezone = input_fn(f"Timezone [{default_timezone}]: ").strip() or default_timezone
    username = input_fn("Create admin username (blank to skip): ").strip()
    password = ""
    if username:
        password = password_fn(f"Password for {username}: ")
        if password != password_fn("Confirm password: "):
            raise InstallRequestError("Passwords do not match.")
    return hostname, timezone, username, password


def _describe_target(target: str, efi: str) -> tuple[str, str, str]:
    normalized_target = disk._normal_device_path(target)
    if not normalized_target:
        raise InstallRequestError(f"Invalid target partition: {target}")
    parent = disk._parent_disk(normalized_target)
    if not parent:
        raise InstallRequestError(
            f"Could not determine parent disk for {normalized_target}."
        )
    normalized_efi = disk._normal_device_path(efi) if efi else ""
    if efi and not normalized_efi:
        raise InstallRequestError(f"Invalid EFI partition: {efi}")
    return normalized_target, parent, normalized_efi or ""


def _print_plan(target: str, parent: str, efi: str) -> None:
    size = next(
        (
            part.get("size") or part.get("size_human") or "unknown size"
            for part in disk.list_partitions(parent)
            if part.get("name") == target
        ),
        "unknown size",
    )
    print("\n=== KythOS Blank-Partition Installer ===\n")
    print(f"  Target partition : {target} ({size})")
    print(f"  Parent disk      : {parent}")
    print(f"  EFI partition    : {efi or 'auto-detect'}")
    print("\nThis will FORMAT ONLY the target partition as Btrfs and install KythOS there.")
    print("Existing neighboring partitions will not be resized or deleted.")
    print("\nBack up important data before continuing. Bootloader changes may affect")
    print("the EFI System Partition when one is reused.\n")


def _render_events(context: InstallerContext) -> int:
    cursor = 0
    while True:
        with context.events.condition:
            context.events.condition.wait_for(
                lambda: len(context.events.events) > cursor
                or context.lifecycle in (InstallLifecycle.DONE, InstallLifecycle.FAILED)
            )
            events = context.events.events[cursor:]
            cursor = len(context.events.events)
        for event in events:
            if event.get("type") == "log":
                print(event.get("text", ""))
            elif event.get("type") == "error":
                print(f"ERROR: {event.get('message', 'Installation failed.')}", file=sys.stderr)
        if context.lifecycle == InstallLifecycle.DONE:
            print("\nInstallation complete.")
            print("Reboot and choose KythOS from your firmware or GRUB boot menu.\n")
            return 0
        if context.lifecycle == InstallLifecycle.FAILED:
            return 1


def run(
    argv: Sequence[str] | None = None,
    *,
    input_fn: Callable[[str], str] = input,
    password_fn: Callable[[str], str] = getpass.getpass,
) -> int:
    args = _parser().parse_args(argv)
    try:
        system.require_root()
        target, parent, requested_efi = _describe_target(
            args.target_partition, args.efi_partition
        )
        _print_plan(target, parent, requested_efi)
        if input_fn(f"Type '{CONFIRMATION}' to continue: ").strip() != CONFIRMATION:
            print("Aborted.")
            return 0

        hostname, timezone, username, password = _prompt_identity(
            input_fn=input_fn,
            password_fn=password_fn,
        )
        context = InstallerContext()
        state = validate_partition_install_request(
            target_partition=target,
            efi_partition=requested_efi,
            hostname=hostname,
            timezone=timezone,
            username=username,
            password=password,
            context=context,
        )
        if not start_installation(context, state, install._run_install):
            raise RuntimeError("An installation is already running.")
        return _render_events(context)
    except InstallRequestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    raise SystemExit(run())
