"""Destructive partition commits used by guided installer planning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import BIOS_BOOT_BYTES


@dataclass(frozen=True, slots=True)
class CommitDependencies:
    """Patchable mutation boundary for partition commits."""

    is_gpt: Callable[[str], bool]
    has_bios_boot: Callable[[str], bool]
    list_partitions: Callable[[str], list[dict]]
    block_size: Callable[[str], int]
    latest_partition: Callable[[str, set[str]], str | None]
    partition_number: Callable[[str], int]
    human_size: Callable[[int], str]
    run_command: Callable
    as_root: Callable[[list[str]], list[str]]
    settle: Callable[[], None]
    disk_hold: Callable
    guard_factory: Callable
    disk_service_factory: Callable


def ensure_bios_boot_partition(
    disk: str, gap_start: int, log, *, dependencies: CommitDependencies,
) -> int:
    """Create a missing GPT BIOS helper and return the next usable byte offset."""
    if not dependencies.is_gpt(disk) or dependencies.has_bios_boot(disk):
        return gap_start
    before = {
        part["name"] for part in dependencies.list_partitions(disk) if part.get("name")
    }
    sector = dependencies.block_size(disk)
    bios_end = gap_start + BIOS_BOOT_BYTES - sector
    log("Creating BIOS boot partition for GRUB...")
    dependencies.run_command(
        dependencies.as_root([
            "parted", "-s", disk, "unit", "B", "mkpart", "biosboot",
            f"{gap_start}B", f"{bios_end}B",
        ]),
        check=True, timeout=120,
    )
    created = dependencies.latest_partition(disk, before)
    if not created:
        dependencies.settle()
        created = dependencies.latest_partition(disk, before)
    if not created:
        raise RuntimeError(
            "The installer could not find the new BIOS boot partition after partitioning."
        )
    dependencies.run_command(
        dependencies.as_root([
            "parted", "-s", disk, "set", str(dependencies.partition_number(created)),
            "bios_grub", "on",
        ]),
        check=True, timeout=120,
    )
    dependencies.settle()
    return bios_end + sector


def commit_new_kythos_partition(
    disk: str,
    gap_start: int,
    gap_end: int,
    log,
    *,
    dependencies: CommitDependencies,
    before_partition: Callable[[], None] | None = None,
    failure_message: str = "A step failed — restoring the original partition table...",
    restored_message: str = "Partition table restored to its state before this attempt.",
) -> str:
    """Create and format a target partition inside a guarded table transaction."""
    del restored_message  # guard owns restore logging; retained for compatibility
    disk_service = dependencies.disk_service_factory()
    with dependencies.disk_hold(disk, log):
        with dependencies.guard_factory(disk, log, disk_service=disk_service):
            if before_partition is not None:
                try:
                    before_partition()
                except Exception as exc:
                    log(f"{failure_message}: {exc}")
                    raise
            btrfs_start = ensure_bios_boot_partition(
                disk, gap_start, log, dependencies=dependencies,
            )
            sector = dependencies.block_size(disk)
            partition_end = gap_end - sector
            before = {
                part["name"] for part in dependencies.list_partitions(disk)
                if part.get("name")
            }
            log(
                "Creating KythOS Btrfs partition in "
                f"{dependencies.human_size(gap_end - btrfs_start)} of free space..."
            )
            dependencies.run_command(
                dependencies.as_root([
                    "parted", "-s", disk, "unit", "B", "mkpart", "KythOS", "btrfs",
                    f"{btrfs_start}B", f"{partition_end}B",
                ]),
                check=True, timeout=120,
            )
            for command in (
                dependencies.as_root(["blockdev", "--rereadpt", disk]),
                dependencies.as_root(["partprobe", disk]),
            ):
                try:
                    dependencies.run_command(command, check=False, timeout=15)
                except Exception:
                    pass
            dependencies.settle()
            created = dependencies.latest_partition(disk, before)
            if not created:
                raise RuntimeError(
                    "The installer could not find the new KythOS partition after partitioning."
                )
            dependencies.run_command(
                dependencies.as_root(["mkfs.btrfs", "-f", "-L", "KythOS", created]),
                check=True, timeout=300,
            )
            dependencies.settle()
            try:
                visible = {
                    part["name"] for part in dependencies.list_partitions(disk)
                    if part.get("name")
                }
                if created not in visible:
                    log(
                        f"Warning: kernel did not yet expose {created} after rereadpt — "
                        "proceeding, udev may still settle."
                    )
            except Exception as exc:
                log(f"Warning: could not verify new partition {created}: {exc}")
            log(f"Created target partition {created}")
            return created


__all__ = ["CommitDependencies", "commit_new_kythos_partition", "ensure_bios_boot_partition"]


def shrink_ntfs_filesystem_guarded(
    partition: str, new_size: int, shrink_bytes: int, log, *, shrink_filesystem,
    human_size, marker_root: Path = Path("/run/kyth-installer"),
) -> None:
    """Shrink NTFS before table mutation and record the non-atomic boundary."""
    log(f"NTFS resize requested: shrink {partition} by {human_size(shrink_bytes)}")
    try:
        shrink_filesystem(partition, "ntfs", new_size, log)
    except Exception:
        log(
            "NTFS filesystem shrink failed — no partition table change was made. "
            "The NTFS volume is unchanged and the installer made no destructive write."
        )
        raise
    log(
        "NTFS filesystem shrink complete. If the next partition step fails, "
        "the partition table will be restored but this filesystem will remain "
        "at its new smaller size. Windows will see unallocated space after it; "
        "use Windows Disk Management to extend the volume back if you want to undo."
    )
    try:
        marker_root.mkdir(parents=True, exist_ok=True)
        marker = marker_root / f"ntfs-shrunk-{partition.replace('/', '_')}"
        marker.write_text(f"{new_size}\n")
    except Exception:
        pass


def prepare_free_space_target(
    config: dict, log, *, validate_target, required_tools, which,
    unmount_target_disk, commit_partition,
) -> tuple[str, str]:
    """Revalidate and commit a guided install into an existing free region."""
    disk, start, end = validate_target(config)
    missing = [command for command in required_tools if which(command) is None]
    if missing:
        raise RuntimeError(
            "Required partitioning tools are missing from the live environment: "
            + ", ".join(missing)
        )
    unmount_target_disk(disk, log)
    disk, start, end = validate_target(config)
    return disk, commit_partition(disk, start, end, log)


__all__ += ["prepare_free_space_target", "shrink_ntfs_filesystem_guarded"]
