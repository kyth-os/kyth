"""Versioned release qualification reports and regression evaluation."""
from __future__ import annotations

import argparse
import json
import math
import platform
import re
import statistics
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .performance import get_cpu_topology
from .smoke_check import SmokeCheck
from .telemetry import recent_sessions

SCHEMA_VERSION = 1
_STATUSES = {"pass", "warning", "fail"}
_DIRECTIONS = {"higher", "lower", "neutral"}
_ACCEPTANCE_LINE = re.compile(r"^KYTH_ACCEPTANCE:([A-Z_]+):(.*)$")
_BASE_ACCEPTANCE_PHASES = (
    "LIVE_READY", "LIVE_SMOKE_OK", "INSTALL_COMPLETE", "INSTALLED_READY",
    "INSTALLED_SMOKE_OK", "COMPLETE",
)
_UPDATE_ACCEPTANCE_PHASES = (
    "UPDATE_STAGED", "UPDATE_BOOTED", "UPDATE_SMOKE_OK", "ROLLBACK_STAGED",
    "ROLLBACK_BOOTED", "ROLLBACK_SMOKE_OK",
)


@dataclass(frozen=True)
class QualificationCheck:
    name: str
    status: str
    evidence: str
    category: str = "system"
    required: bool = True

    def __post_init__(self) -> None:
        if self.status not in _STATUSES:
            raise ValueError(f"unsupported check status: {self.status}")


@dataclass(frozen=True)
class QualificationMetric:
    name: str
    value: float
    unit: str
    direction: str
    workload: str = ""
    source: str = ""

    def __post_init__(self) -> None:
        if self.direction not in _DIRECTIONS:
            raise ValueError(f"unsupported metric direction: {self.direction}")
        if not math.isfinite(self.value):
            raise ValueError("metric value must be finite")

    @property
    def key(self) -> tuple[str, str, str]:
        return self.name, self.workload, self.unit


@dataclass(frozen=True)
class RegressionBudget:
    metric: str
    max_regression_percent: float
    workload: str = "*"
    required: bool = True

    def __post_init__(self) -> None:
        if not math.isfinite(self.max_regression_percent) or self.max_regression_percent < 0:
            raise ValueError("regression budget must be a non-negative finite number")

    def applies_to(self, candidate: QualificationMetric) -> bool:
        return self.metric == candidate.name and self.workload in {"*", candidate.workload}


@dataclass(frozen=True)
class RegressionResult:
    metric: str
    workload: str
    baseline: float
    candidate: float
    regression_percent: float
    budget_percent: float
    status: str


@dataclass(frozen=True)
class QualificationReport:
    generated_at: str
    source: str
    identity: Mapping[str, str]
    checks: tuple[QualificationCheck, ...]
    metrics: tuple[QualificationMetric, ...] = ()
    regressions: tuple[RegressionResult, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        source: str,
        identity: Mapping[str, str],
        checks: Iterable[QualificationCheck],
        metrics: Iterable[QualificationMetric] = (),
    ) -> "QualificationReport":
        return cls(
            datetime.now().astimezone().isoformat(), source, dict(identity),
            tuple(checks), tuple(metrics),
        )

    @property
    def overall(self) -> str:
        if any(check.required and check.status == "fail" for check in self.checks):
            return "fail"
        if any(result.status == "fail" for result in self.regressions):
            return "fail"
        if any(check.status in {"warning", "fail"} for check in self.checks):
            return "warning"
        return "pass"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": self.generated_at,
            "source": self.source,
            "overall": self.overall,
            "identity": dict(sorted(self.identity.items())),
            "summary": {
                status: sum(check.status == status for check in self.checks)
                for status in ("pass", "warning", "fail")
            },
            "checks": [asdict(check) for check in self.checks],
            "metrics": [asdict(metric) for metric in self.metrics],
            "regressions": [asdict(result) for result in self.regressions],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    def to_markdown(self) -> str:
        lines = [f"# KythOS qualification: {self.overall.upper()}", ""]
        lines.extend(f"- **{key}:** {value}" for key, value in sorted(self.identity.items()))
        lines.extend(("", "## Checks", "", "| Status | Category | Check | Evidence |", "| --- | --- | --- | --- |"))
        for check in self.checks:
            evidence = check.evidence.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {check.status} | {check.category} | {check.name} | {evidence} |")
        if self.metrics:
            lines.extend(("", "## Metrics", "", "| Metric | Workload | Value | Source |", "| --- | --- | ---: | --- |"))
            for metric in self.metrics:
                lines.append(
                    f"| {metric.name} | {metric.workload or 'system'} | "
                    f"{metric.value:g} {metric.unit} | {metric.source} |"
                )
        if self.regressions:
            lines.extend(("", "## Regression gate", "", "| Status | Metric | Workload | Change | Budget |", "| --- | --- | --- | ---: | ---: |"))
            for result in self.regressions:
                lines.append(
                    f"| {result.status} | {result.metric} | {result.workload or 'system'} | "
                    f"{result.regression_percent:+.2f}% | {result.budget_percent:g}% |"
                )
        return "\n".join(lines) + "\n"

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "QualificationReport":
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported qualification schema version")
        identity = value.get("identity", {})
        if not isinstance(identity, dict):
            raise ValueError("identity must be an object")
        return cls(
            generated_at=str(value.get("generated_at", "")),
            source=str(value.get("source", "unknown")),
            identity={str(key): str(item) for key, item in identity.items()},
            checks=tuple(QualificationCheck(**item) for item in value.get("checks", [])),  # type: ignore[arg-type]
            metrics=tuple(QualificationMetric(**item) for item in value.get("metrics", [])),  # type: ignore[arg-type]
            regressions=tuple(RegressionResult(**item) for item in value.get("regressions", [])),  # type: ignore[arg-type]
        )

    @classmethod
    def read(cls, path: Path) -> "QualificationReport":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def evaluate_regressions(
    candidate: QualificationReport,
    baseline: QualificationReport,
    budgets: Iterable[RegressionBudget],
) -> QualificationReport:
    budgets = tuple(budgets)
    baseline_metrics = {metric.key: metric for metric in baseline.metrics}
    results: list[RegressionResult] = []
    gate_checks: list[QualificationCheck] = []
    for identity_key in ("cpu", "gpu", "machine"):
        current_identity = candidate.identity.get(identity_key)
        baseline_identity = baseline.identity.get(identity_key)
        if current_identity and baseline_identity and current_identity != baseline_identity:
            gate_checks.append(
                QualificationCheck(
                    f"matching {identity_key}",
                    "fail",
                    f"candidate {current_identity!r} != baseline {baseline_identity!r}",
                    "regression",
                )
            )
    for metric in candidate.metrics:
        prior = baseline_metrics.get(metric.key)
        budget = next((item for item in budgets if item.applies_to(metric)), None)
        if not prior or not budget or metric.direction == "neutral":
            continue
        denominator = abs(prior.value)
        if denominator == 0:
            if metric.value == prior.value:
                regression = 0.0
            elif metric.direction == "higher":
                regression = -100.0 if metric.value > prior.value else 100.0
            else:
                regression = 100.0 if metric.value > prior.value else -100.0
        elif metric.direction == "higher":
            regression = (prior.value - metric.value) / denominator * 100
        else:
            regression = (metric.value - prior.value) / denominator * 100
        results.append(
            RegressionResult(
                metric=metric.name,
                workload=metric.workload,
                baseline=prior.value,
                candidate=metric.value,
                regression_percent=round(regression, 4),
                budget_percent=budget.max_regression_percent,
                status="fail" if regression > budget.max_regression_percent else "pass",
            )
        )
    candidate_keys = {metric.key for metric in candidate.metrics}
    for prior in baseline.metrics:
        budget = next((item for item in budgets if item.applies_to(prior)), None)
        if budget and budget.required and prior.key not in candidate_keys:
            gate_checks.append(
                QualificationCheck(
                    f"required metric {prior.name}",
                    "fail",
                    f"candidate is missing workload {prior.workload or 'system'} ({prior.unit})",
                    "regression",
                )
            )
    return replace(
        candidate,
        checks=(*candidate.checks, *gate_checks),
        regressions=tuple(results),
    )


def load_budgets(path: Path) -> tuple[RegressionBudget, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported regression budget schema version")
    return tuple(RegressionBudget(**item) for item in data.get("budgets", []))


def acceptance_report(log: str, *, update_required: bool = False) -> QualificationReport:
    events: dict[str, str] = {}
    for line in log.splitlines():
        match = _ACCEPTANCE_LINE.match(line.strip())
        if match:
            events[match.group(1)] = match.group(2)
    expected = _BASE_ACCEPTANCE_PHASES + (_UPDATE_ACCEPTANCE_PHASES if update_required else ())
    checks = [
        QualificationCheck(
            name=phase.lower().replace("_", " "),
            status="pass" if phase in events else "fail",
            evidence=events.get(phase, "acceptance sentinel missing"),
            category="vm-acceptance",
        )
        for phase in expected
    ]
    if "FAILED" in events:
        checks.append(QualificationCheck("guest failure", "fail", events["FAILED"], "vm-acceptance"))
    identity = {"environment": "qemu"}
    if "INSTALL_COMPLETE" in events:
        identity["installed_image"] = events["INSTALL_COMPLETE"]
    if "UPDATE_BOOTED" in events:
        identity["updated_digest"] = events["UPDATE_BOOTED"]
    return QualificationReport.create(
        source="vm-acceptance",
        identity=identity,
        checks=checks,
    )


def local_report(*, include_gaming: bool = False) -> QualificationReport:
    smoke = SmokeCheck(quiet=True)
    smoke.execute()
    checks = tuple(
        QualificationCheck(
            name=result.name,
            status={"PASS": "pass", "WARN": "warning", "FAIL": "fail"}.get(result.level, "warning"),
            evidence=result.detail,
            category=result.section or "system",
        )
        for result in smoke.results
    )
    vendor, cpu = get_cpu_topology()
    identity = {
        "cpu": cpu,
        "cpu_vendor": vendor,
        "kernel": platform.release(),
        "machine": platform.machine(),
    }
    for result in smoke.results:
        if result.name == "GPU detected" and result.level == "PASS":
            identity["gpu"] = result.detail
        elif result.name == "Booted image" and result.level == "PASS":
            identity["image"] = result.detail
    metrics: list[QualificationMetric] = []
    if include_gaming:
        grouped: dict[str, list[object]] = {}
        for session in recent_sessions(limit=100):
            grouped.setdefault(session.game_name, []).append(session)
        for workload, sessions in sorted(grouped.items()):
            avg = [session.avg_fps for session in sessions if session.avg_fps is not None]
            lows = [session.p1_low_fps for session in sessions if session.p1_low_fps is not None]
            durations = sum(session.duration_s or 0 for session in sessions)
            stutters = sum(session.stutter_count for session in sessions)
            if avg:
                metrics.append(QualificationMetric("gaming.avg_fps", statistics.median(avg), "fps", "higher", workload, "MangoHud"))
            if lows:
                metrics.append(QualificationMetric("gaming.p1_low_fps", statistics.median(lows), "fps", "higher", workload, "MangoHud"))
            if durations > 0:
                metrics.append(QualificationMetric("gaming.stutters_per_minute", stutters / durations * 60, "count/min", "lower", workload, "MangoHud"))
    return QualificationReport.create(source="local-hardware", identity=identity, checks=checks, metrics=metrics)


def _write_report(report: QualificationReport, output: Path, markdown: Path | None) -> None:
    import os
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".tmp")
    tmp.write_text(report.to_json(), encoding="utf-8")
    try:
        with open(tmp, "rb") as fh:
            os.fsync(fh.fileno())
    except OSError:
        pass
    tmp.replace(output)
    try:
        dfd = os.open(str(output.parent), os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass
    if markdown:
        markdown.parent.mkdir(parents=True, exist_ok=True)
        tmp = markdown.with_suffix(".tmp")
        tmp.write_text(report.to_markdown(), encoding="utf-8")
        try:
            with open(tmp, "rb") as fh:
                os.fsync(fh.fileno())
        except OSError:
            pass
        tmp.replace(markdown)
        try:
            dfd = os.open(str(markdown.parent), os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kyth-qualify", description="Create and gate KythOS release qualification evidence.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("collect", "acceptance"):
        child = subparsers.add_parser(command)
        child.add_argument("--output", type=Path, required=True)
        child.add_argument("--markdown", type=Path)
    subparsers.choices["collect"].add_argument("--include-gaming", action="store_true", help="include local game names and aggregated MangoHud metrics")
    acceptance = subparsers.choices["acceptance"]
    acceptance.add_argument("--log", type=Path, required=True)
    acceptance.add_argument("--update-required", action="store_true")
    gate = subparsers.add_parser("gate")
    gate.add_argument("--candidate", type=Path, required=True)
    gate.add_argument("--baseline", type=Path, required=True)
    gate.add_argument("--budgets", type=Path, required=True)
    gate.add_argument("--output", type=Path)
    gate.add_argument("--markdown", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "collect":
        report = local_report(include_gaming=args.include_gaming)
    elif args.command == "acceptance":
        report = acceptance_report(args.log.read_text(encoding="utf-8", errors="replace"), update_required=args.update_required)
    else:
        report = evaluate_regressions(
            QualificationReport.read(args.candidate),
            QualificationReport.read(args.baseline),
            load_budgets(args.budgets),
        )
    output = args.output or args.candidate
    _write_report(report, output, args.markdown)
    return 1 if report.overall == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
