"""Shared helpers for install pipeline phases."""
from __future__ import annotations

from ..context import InstallerContext


def _push(event: dict, context: InstallerContext) -> None:
    context.events.publish(event)
