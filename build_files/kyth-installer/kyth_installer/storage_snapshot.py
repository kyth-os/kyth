"""Immutable storage discovery results used by installer planning.

Keep live device probing at the edge so plan validation can be exercised with
plain data and cannot accidentally re-scan a device halfway through a decision.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StorageSnapshot:
    disks: tuple[dict, ...]
    partitions: tuple[dict, ...]
    free_regions: tuple[dict, ...]
    efi_partition: str | None
    is_gpt: bool

    @property
    def disks_by_name(self) -> dict[str, dict]:
        return {str(item.get("name")): item for item in self.disks if item.get("name")}

    @property
    def partitions_by_name(self) -> dict[str, dict]:
        return {str(item.get("name")): item for item in self.partitions if item.get("name")}

    def has_bios_boot_partition(self, bios_boot_guid: str) -> bool:
        return any(
            str(part.get("parttype") or "").lower() == bios_boot_guid.lower()
            for part in self.partitions
        )

    def contains_free_region(self, start: int, end: int) -> bool:
        return any(
            region.get("start_bytes") == start and region.get("end_bytes") == end
            for region in self.free_regions
        )
