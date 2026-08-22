"""Typed, support-safe health reporting shared by CLI and System Hub."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True)
class HealthResult:
    component: str
    severity: str
    evidence: str
    remediation: str = ""
    section: str = ""


@dataclass(frozen=True)
class HealthReport:
    generated_at: str
    results: tuple[HealthResult, ...]

    @classmethod
    def create(cls, results: Iterable[HealthResult]) -> "HealthReport":
        return cls(datetime.now().astimezone().isoformat(), tuple(results))

    @property
    def overall(self) -> str:
        severities = {result.severity for result in self.results}
        if "error" in severities:
            return "error"
        if "warning" in severities:
            return "warning"
        return "healthy"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "generated_at": self.generated_at,
            "overall": self.overall,
            "summary": {
                severity: sum(
                    result.severity == severity for result in self.results
                )
                for severity in ("healthy", "warning", "error")
            },
            "results": [asdict(result) for result in self.results],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    def to_text(self) -> str:
        lines = [f"KythOS health: {self.overall}"]
        section = None
        for result in self.results:
            if result.section != section:
                section = result.section
                if section:
                    lines.extend(("", f"== {section} =="))
            lines.append(
                f"{result.severity.upper():<7} {result.component}: {result.evidence}"
            )
            if result.remediation:
                lines.append(f"        Fix: {result.remediation}")
        return "\n".join(lines) + "\n"


_REMEDIATIONS = {
    "bootc": "Open Pulse > This PC > Repair and verify the bootc deployment.",
    "firmware": "Open Pulse > This PC > Updates and run the firmware check.",
    "flatpak": "Open Pulse > This PC > Repair and retry the default app setup.",
    "secure boot": "Review Secure Boot status in Pulse > This PC > Hardware.",
    "vulkan": "Open Pulse > This PC > Hardware and review the graphics driver.",
    "pipewire": "Open Pulse > This PC > Repair and restart audio.",
    "wireplumber": "Open Pulse > This PC > Repair and restart audio.",
}


def remediation_for(component: str) -> str:
    lowered = component.lower()
    return next(
        (message for needle, message in _REMEDIATIONS.items() if needle in lowered),
        "Review this check in Pulse or include the JSON report with support.",
    )


def from_smoke_results(results: Iterable[object]) -> HealthReport:
    """Convert smoke-check Result-like objects without coupling modules."""
    converted = []
    levels = {"PASS": "healthy", "WARN": "warning", "FAIL": "error"}
    for result in results:
        severity = levels.get(str(getattr(result, "level", "")).upper(), "warning")
        component = str(getattr(result, "name", "Unknown"))
        converted.append(
            HealthResult(
                component=component,
                severity=severity,
                evidence=str(getattr(result, "detail", "")),
                remediation="" if severity == "healthy" else remediation_for(component),
                section=str(getattr(result, "section", "")),
            )
        )
    return HealthReport.create(converted)
