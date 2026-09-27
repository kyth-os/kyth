"""Shared configuration loading utilities for KythOS daemons/services."""
from __future__ import annotations
import logging

import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)


def load_toml_config(
    filename: str,
    *,
    default_config: dict,
    section_name: str | None = None,
    extra_candidates: list[Path] | None = None,
) -> dict:
    """Load config from ~/.config/kyth/ or /etc/kyth/ and merge with defaults."""
    candidates = []
    if extra_candidates:
        candidates.extend(extra_candidates)
    candidates.extend(
        [
            Path.home() / ".config" / "kyth" / filename,
            Path("/etc/kyth") / filename,
        ]
    )

    for p in candidates:
        if p.is_file():
            try:
                with open(p, "rb") as f:
                    data = tomllib.load(f)
                config_data = data
                if section_name and isinstance(data, dict):
                    config_data = data.get(section_name, data)
                res = default_config.copy()
                if isinstance(config_data, dict):
                    res.update(config_data)
                return res
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                logger.debug("handled expected exception", exc_info=True)
                pass
    return default_config.copy()
