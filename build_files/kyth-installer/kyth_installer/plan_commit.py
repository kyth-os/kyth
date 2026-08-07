"""Plan commit — destructive helpers that back up, partition, and mkfs.

Extracted from plan.py 678 monolith (step 3). These mutate the disk;
validate_plan_state is the gate before entering.
"""
from __future__ import annotations

# Re-export for compat — canonical implementations still live in plan.py
# until the next hunk-level split moves them here.
from .plan import (  # noqa: F401
    _commit_new_kythos_partition,
    _ensure_bios_boot_partition,
    _prepare_explicit_install_plan,
    _prepare_free_space_install_plan,
    _prepare_free_space_target,
    _prepare_install_plan,
    _prepare_ntfs_install_plan,
    _prepare_ntfs_resize_target,
)

__all__ = [
    "_commit_new_kythos_partition",
    "_ensure_bios_boot_partition",
    "_prepare_explicit_install_plan",
    "_prepare_free_space_install_plan",
    "_prepare_free_space_target",
    "_prepare_install_plan",
    "_prepare_ntfs_install_plan",
    "_prepare_ntfs_resize_target",
]
