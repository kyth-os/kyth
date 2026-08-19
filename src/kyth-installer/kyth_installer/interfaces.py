"""Protocols for disk/partition services to break circular imports.

partition_ops previously imported services.disk_service.DiskService
directly, while services.installer_service imported install → plan →
partition_ops, creating a cycle that forced a lazy import workaround.

Protocols let partition_ops depend on an abstract DiskServiceProtocol
and let InstallerContext hold a DiskService via typing without importing
the concrete class at module load time.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DiskServiceProtocol(Protocol):
    dry_run: bool
    journal: list[list[str]]

    def execute(self, cmd: list[str], **kwargs): ...

    def settle(self) -> None: ...

    def backup_table(self, disk: str, backup_path: str) -> None: ...

    def restore_table(self, disk: str, backup_path: str) -> None: ...

    def create_label(self, disk: str, table_type: str) -> None: ...

    def create_partition(self, disk: str, start: int, size: int, fs: str, label: str) -> None: ...

    def create_unformatted_partition(self, disk: str, start: int, size: int, label: str) -> None: ...

    def delete_partition(self, disk: str, part_num: int) -> None: ...

    def set_partition_flag(self, disk: str, part_num: int, flag: str, enabled: bool = True) -> None: ...

    def resize_partition(self, disk: str, part_num: int, start: int, new_size: int) -> None: ...

    def format_filesystem(self, device: str, fs: str, label: str) -> None: ...


@runtime_checkable
class JournalProtocol(Protocol):
    disk: str
    ops: list[dict]
    committed: bool
    root_partition: str | None

    def add_op(self, kind: str, params: dict) -> dict: ...

    def remove_op(self, index: int) -> bool: ...

    def pending(self) -> list[dict]: ...

    def validate(self) -> list[str]: ...

    def commit(self, log) -> str | None: ...

    def rollback(self, log) -> None: ...
