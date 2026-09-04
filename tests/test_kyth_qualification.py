"""Contracts for unified VM, hardware, and performance qualification."""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_files" / "kyth_shared"))

from kyth_shared.qualification import (  # noqa: E402
    QualificationCheck,
    QualificationMetric,
    QualificationReport,
    RegressionBudget,
    acceptance_report,
    evaluate_regressions,
    main,
)


def report_with_metric(value: float, direction: str = "higher") -> QualificationReport:
    return QualificationReport.create(
        source="test",
        identity={"hardware": "fixture"},
        checks=[QualificationCheck("boot", "pass", "ready")],
        metrics=[
            QualificationMetric(
                "gaming.avg_fps", value, "fps", direction, "Game A", "fixture"
            )
        ],
    )


class QualificationSchemaTests(unittest.TestCase):
    def test_report_round_trip_and_markdown(self):
        report = report_with_metric(120.0)

        restored = QualificationReport.from_dict(json.loads(report.to_json()))

        self.assertEqual(restored.metrics, report.metrics)
        self.assertEqual(restored.overall, "pass")
        self.assertIn("# KythOS qualification: PASS", restored.to_markdown())
        self.assertIn("120 fps", restored.to_markdown())

    def test_required_failure_controls_overall_status(self):
        report = QualificationReport.create(
            source="test",
            identity={},
            checks=[QualificationCheck("required", "fail", "broken")],
        )
        advisory = QualificationReport.create(
            source="test",
            identity={},
            checks=[QualificationCheck("optional", "fail", "missing", required=False)],
        )

        self.assertEqual(report.overall, "fail")
        self.assertEqual(advisory.overall, "warning")

    def test_unknown_schema_and_status_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "schema version"):
            QualificationReport.from_dict({"schema_version": 99})
        with self.assertRaisesRegex(ValueError, "check status"):
            QualificationCheck("bad", "unknown", "bad")


class RegressionGateTests(unittest.TestCase):
    def test_higher_is_better_metric_fails_outside_budget(self):
        gated = evaluate_regressions(
            report_with_metric(90),
            report_with_metric(100),
            [RegressionBudget("gaming.avg_fps", 5)],
        )

        self.assertEqual(gated.overall, "fail")
        self.assertEqual(gated.regressions[0].regression_percent, 10)

    def test_lower_is_better_metric_passes_when_candidate_improves(self):
        gated = evaluate_regressions(
            report_with_metric(8, "lower"),
            report_with_metric(10, "lower"),
            [RegressionBudget("gaming.avg_fps", 5)],
        )

        self.assertEqual(gated.overall, "pass")
        self.assertEqual(gated.regressions[0].regression_percent, -20)

    def test_different_workloads_are_not_compared(self):
        candidate = report_with_metric(90)
        baseline = QualificationReport.create(
            source="test",
            identity={},
            checks=[],
            metrics=[
                QualificationMetric(
                    "gaming.avg_fps", 100, "fps", "higher", "Game B"
                )
            ],
        )

        gated = evaluate_regressions(
            candidate, baseline, [RegressionBudget("gaming.avg_fps", 0)]
        )

        self.assertEqual(gated.regressions, ())
        self.assertEqual(gated.overall, "fail")
        self.assertIn("required metric", gated.checks[-1].name)

    def test_different_hardware_is_rejected(self):
        candidate = report_with_metric(100)
        baseline = report_with_metric(100)
        candidate = QualificationReport.create(
            source=candidate.source,
            identity={"cpu": "CPU A"},
            checks=candidate.checks,
            metrics=candidate.metrics,
        )
        baseline = QualificationReport.create(
            source=baseline.source,
            identity={"cpu": "CPU B"},
            checks=baseline.checks,
            metrics=baseline.metrics,
        )

        gated = evaluate_regressions(
            candidate, baseline, [RegressionBudget("gaming.avg_fps", 5)]
        )

        self.assertEqual(gated.overall, "fail")
        self.assertIn("matching cpu", gated.checks[-1].name)


class AcceptanceReportTests(unittest.TestCase):
    def test_install_only_log_becomes_passing_report(self):
        log = "\n".join(
            f"KYTH_ACCEPTANCE:{phase}:ok"
            for phase in (
                "LIVE_READY", "LIVE_SMOKE_OK", "INSTALL_COMPLETE",
                "INSTALLED_READY", "INSTALLED_SMOKE_OK", "COMPLETE",
                "HUB_BINARY_OK", "HUB_DEEP_LINKS_OK", "HUB_SECOND_LAUNCH_OK",
                "HUB_DASHBOARD_DEGRADED_OK", "HUB_UPDATES_OK", "HUB_PRIVILEGED_FAILURE_OK",
            )
        )

        report = acceptance_report(log)

        self.assertEqual(report.overall, "pass")
        self.assertEqual(len(report.checks), 12)
        self.assertEqual(report.identity["installed_image"], "ok")

    def test_update_gate_requires_update_and_rollback_phases(self):
        report = acceptance_report(
            "KYTH_ACCEPTANCE:LIVE_READY:ok\nKYTH_ACCEPTANCE:FAILED:update failed",
            update_required=True,
        )

        self.assertEqual(report.overall, "fail")
        self.assertTrue(any(check.name == "rollback booted" for check in report.checks))
        self.assertTrue(any(check.name == "guest failure" for check in report.checks))

    def test_gate_cli_writes_evaluated_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            candidate = directory / "candidate.json"
            baseline = directory / "baseline.json"
            budgets = directory / "budgets.json"
            output = directory / "gated.json"
            candidate.write_text(report_with_metric(90).to_json(), encoding="utf-8")
            baseline.write_text(report_with_metric(100).to_json(), encoding="utf-8")
            budgets.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "budgets": [
                            {
                                "metric": "gaming.avg_fps",
                                "max_regression_percent": 5,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = main(
                [
                    "gate", "--candidate", str(candidate), "--baseline", str(baseline),
                    "--budgets", str(budgets), "--output", str(output),
                ]
            )

            self.assertEqual(result, 1)
            self.assertEqual(QualificationReport.read(output).overall, "fail")


class QualificationPackagingTests(unittest.TestCase):
    def test_vm_acceptance_emits_unified_artifacts(self):
        host = (ROOT / "build_files/scripts/vm-acceptance.sh").read_text(encoding="utf-8")
        project = (ROOT / "build_files/kyth_shared/pyproject.toml").read_text(encoding="utf-8")
        installer = (
            ROOT / "build_files/scripts/branding/35-diagnostic-script-installs.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('qualification.json', host)
        self.assertIn('qualification.md', host)
        self.assertIn('kyth-qualify = "kyth_shared.qualification:main"', project)
        self.assertIn("qualification-budgets.json", installer)


if __name__ == "__main__":
    unittest.main()
