"""Partition operations — facade after journal split.

Journal lives in partition_ops_journal.py; this module re-exports it and
hosts the remaining operation helpers (_mkfs_cmd, get/init/reset_journal).
"""
from __future__ import annotations

from typing import Optional

from .partition_ops_journal import Journal, _require_mkfs  # pylint: disable=unused-import

# Re-exported for server.py and tests that import from partition_ops
from .config import FILESYSTEM_OPTIONS, _FILESYSTEM  # pylint: disable=unused-import
# Disk helpers re-exported so mock.patch.object(partition_ops, "list_disks") works
from .disk import (  # noqa: F401  # pylint: disable=unused-import
    _human_size,  # pylint: disable=unused-import
    _latest_partition_on_disk,  # pylint: disable=unused-import
    _normal_device_path,  # pylint: disable=unused-import
    _parent_disk,  # pylint: disable=unused-import
    _partition_number,  # pylint: disable=unused-import
    _partition_size_bytes,  # pylint: disable=unused-import
    _partition_start_bytes,  # pylint: disable=unused-import
    _safe_int,  # pylint: disable=unused-import
    list_disks,  # pylint: disable=unused-import
    list_free_space,  # pylint: disable=unused-import
    list_partitions,  # pylint: disable=unused-import
)
from .fsresize import shrink_filesystem  # pylint: disable=unused-import

def _mkfs_cmd(fstype: str, device: str, label: str = "") -> list[str]:
    info = _FILESYSTEM.get(fstype)
    if not info:
        return []
    cmd = [info["binary"]] + list(info["args"])
    if label:
        if fstype == "fat32":
            cmd.extend(["-n", label])
        else:
            cmd.extend(["-L", label])
    cmd.append(device)
    return cmd


def get_journal(context) -> Optional[Journal]:
    with context.state_lock:
        return context.journal


def init_journal(disk: str, context) -> Journal:
    with context.state_lock:
        reset_journal(context)
        context.journal = Journal(disk)
        return context.journal


def reset_journal(context) -> None:
    with context.state_lock:
        journal = context.journal
        if journal:
            journal.ops.clear()
            journal._committed = False
            journal._root_partition = None
            journal._discard_snapshot()
        context.journal = None

