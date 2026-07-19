"""Shared hardware probe types."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HardwareProbe:
    title: str
    status: str
    summary: str
    details: str
    action: str | None = None
    action_page_key: str | None = None
    action_cmd: list[str] | None = None


def _status_palette(status: str) -> tuple[str, str, str]:
    if status == "ok":
        return ("#121e2d", "#4fc1ff", "OK")
    if status == "warn":
        return ("#152030", "#e0af68", "Warning")
    if status == "err":
        return ("#2b1520", "#f7768e", "Issue")
    return ("#1e1e2e", "#45475a", "Info")
