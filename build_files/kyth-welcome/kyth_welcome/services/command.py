"""Synchronous command adapter for System Hub services.

Long-running and streamed processes deliberately remain on ``Popen`` in their
own workers. Ordinary bounded commands pass through the shared Kyth runner so
normalization and execution failure policy stay consistent.
"""
from __future__ import annotations

from typing import Any

from kyth_shared.commands import Command, run


def run_sync(command: Command, **kwargs: Any):
    """Run one bounded command with caller-selected output/error semantics."""
    return run(command, **kwargs)
