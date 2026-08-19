"""Central compatibility boundary for phase dependencies.

The historical ``install`` module re-exports helpers that tests and external
callers patch.  Phase modules resolve through that surface when available,
then fall back to the canonical implementation.  Keeping the policy here
avoids repeating large import ladders in every phase function.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def phase_dependency(name: str) -> Any:
    """Resolve one phase helper through the compatibility facade."""
    try:
        from .. import install

        return getattr(install, name)
    except (ImportError, AttributeError):
        return _canonical_dependency(name)


def _canonical_dependency(name: str) -> Callable[..., Any]:
    from .. import disk, plan, runner, system
    from . import bootc_cmd

    providers = (runner, system, disk, plan, bootc_cmd)
    for provider in providers:
        dependency = getattr(provider, name, None)
        if dependency is not None:
            return dependency
    raise AttributeError(f"Unknown installer phase dependency: {name}")
