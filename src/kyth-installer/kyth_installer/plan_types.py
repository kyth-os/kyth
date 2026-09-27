"""Plan types — extracted from plan.py monolith (880→ types)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .context import InstallRequest

@dataclass(frozen=True)
class PlanReport:
    """Dry-run / validate-only report — no disk mutation, safe for UI preview.

    Produced by :func:`validate_plan_state` before any destructive partitioning.
    The install route can return this to the webui so the user sees exactly
    what *would* happen and why it would be rejected, mirroring the checks that
    the commit path will re-run.
    """

    valid: bool
    mode: str
    disk: str = ""
    target_partition: str = ""
    efi_partition: str = ""
    will_create_partition: bool = False
    will_shrink_filesystem: bool = False
    required_bytes: int = 0
    available_bytes: int = 0
    is_gpt: bool = False
    needs_bios_boot: bool = False
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()



@dataclass(frozen=True)
class InstallPlan:
    mode: str
    disk: Optional[str] = None
    target_partition: Optional[str] = None



@dataclass(frozen=True)
class ResolvedInstallPlan:
    """Complete immutable input consumed by destructive install phases."""

    request: InstallRequest
    storage: InstallPlan
    source_ref: str
    target_ref: str
    source_digest: str = ""
    source_kind: str = "network"
    source_verified: bool = False

    @property
    def mode(self) -> str:
        return self.storage.mode

    @property
    def disk(self) -> str:
        if not self.storage.disk:
            raise RuntimeError("Resolved install plan has no target disk")
        return self.storage.disk

    @property
    def target_partition(self) -> str:
        return self.storage.target_partition or ""

    @property
    def efi_partition(self) -> str:
        return self.request.efi_partition

    @property
    def kernel(self) -> str:
        return self.request.kernel



