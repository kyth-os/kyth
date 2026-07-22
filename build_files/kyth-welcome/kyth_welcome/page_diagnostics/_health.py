import os
import re
from datetime import datetime

# __KYTH_GENERATED_IMPORTS__
from ..core_base import _restyle
from ..services.diagnostics import (
    _diagnostics_report,
    _health_command_report,
    _health_recommendations,
)
from ..services.gaming import DataWorker
from ..services.hardware import HardwareProbeWorker
from ..services.launch import popen
from ..services.runtime import _finish_worker
from ..qt import QApplication, QFileDialog
from ..widgets import HardwareCard


class _HealthMixin:
    def _set_status(self, state: str, text: str) -> None:
        self._status_lbl.set_state(state, text)

    def _build_summary_banner(self, probes: list) -> None:
        errs  = [p for p in probes if p.status == "err"]
        warns = [p for p in probes if p.status == "warn"]
        oks   = [p for p in probes if p.status == "ok"]
        if errs:
            self._banner_card.setObjectName("card-accent-err")
            self._banner_title.setText(
                f"{len(errs)} issue{'s' if len(errs) != 1 else ''} found"
            )
            self._banner_body.setText(
                "Some hardware or system checks need attention. "
                "Review the items below and follow the suggested fixes."
            )
        elif warns:
            self._banner_card.setObjectName("card-accent-warn")
            self._banner_title.setText(
                f"{len(warns)} warning{'s' if len(warns) != 1 else ''}"
            )
            self._banner_body.setText(
                "Everything is mostly working but some things could be improved. "
                "Check the items below for details."
            )
        else:
            self._banner_card.setObjectName("card-accent-ok")
            self._banner_title.setText(f"All {len(oks)} checks passed")
            self._banner_body.setText("Your hardware and system stack look healthy.")
        _restyle(self._banner_card)
        self._banner_card.show()

    def _clear_cards(self):
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._probe_cards = {}

    def refresh(self):
        self._refresh_btn.setEnabled(False)
        self._copy_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._issue_btn.setEnabled(False)
        self._set_status("running", "Gathering system information\u2026")
        self._progress.show()
        self._base_report = ""
        self._health_report = ""
        self._banner_card.hide()
        self._empty_state.hide()
        self._raw_toggle.hide()
        self._report.hide()
        self._report.setPlainText("")
        self._clear_cards()

        self._worker = HardwareProbeWorker()
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_done(self, probes: list):
        self._progress.hide()
        self._refresh_btn.setEnabled(True)
        _finish_worker(self)
        self._last_probes = probes
        self._base_report = _diagnostics_report(probes)

        self._build_summary_banner(probes)
        self._clear_cards()
        if probes:
            self._empty_state.hide()
            for probe in probes:
                card = HardwareCard(probe)
                self._probe_cards[probe.title] = card
                self._cards_layout.addWidget(card)
        else:
            self._empty_state.show()

        levels = {p.status for p in probes}
        if "err" in levels:
            self._set_status("err", "Issues found \u2014 running extended checks\u2026")
        elif "warn" in levels:
            self._set_status("warn", "Warnings found \u2014 running extended checks\u2026")
        else:
            self._set_status("ok", "Hardware checks passed \u2014 running extended checks\u2026")

        self._health_worker = DataWorker("health", _health_command_report)
        self._health_worker.result.connect(self._on_health_done)
        self._health_worker.failed.connect(self._on_health_failed)
        self._health_worker.start()

    def _on_health_done(self, _key: str, report: str):
        _finish_worker(self, "_health_worker")
        self._health_report = str(report)
        recs = _health_recommendations(self._base_report + self._health_report)
        self._report.setPlainText(self._base_report + recs + self._health_report)
        self._copy_btn.setEnabled(True)
        self._save_btn.setEnabled(True)
        self._issue_btn.setEnabled(True)
        self._raw_toggle.show()

        has_failures = (
            re.search(r"^FAIL\s+", self._health_report, re.MULTILINE)
            or re.search(r"^FAIL:\s*[1-9]", self._health_report, re.MULTILINE)
            or "Result: not daily-driver ready" in self._health_report
        )
        has_warnings = (
            re.search(r"^WARN\s+", self._health_report, re.MULTILINE)
            or re.search(r"^WARN:\s*[1-9]", self._health_report, re.MULTILINE)
            or "Result: controller readiness has warnings" in self._health_report
            or "Result: resume readiness has warnings" in self._health_report
        )
        if has_failures:
            self._set_status("err", "Issues found \u2014 check the details above.")
        elif has_warnings:
            self._set_status("warn", "Warnings found \u2014 review the items above.")
        else:
            self._set_status("ok", "All checks completed successfully.")

    def _on_health_failed(self, _key: str, message: str):
        _finish_worker(self, "_health_worker")
        self._health_report = f"\nKythOS Health Command Output\n==========================\n\nfailed: {message}\n"
        self._report.setPlainText(self._base_report + self._health_report)
        self._copy_btn.setEnabled(True)
        self._save_btn.setEnabled(True)
        self._issue_btn.setEnabled(True)
        self._raw_toggle.show()
        self._set_status("err", f"Extended checks failed: {message}")

    def _on_failed(self, message: str):
        self._progress.hide()
        self._refresh_btn.setEnabled(True)
        _finish_worker(self)
        self._set_status("err", f"Failed: {message}")

    def _toggle_raw(self, checked: bool):
        self._raw_toggle.setText(
            "Hide technical details" if checked else "Show technical details"
        )
        self._report.setVisible(checked)

    def _copy_report(self):
        QApplication.clipboard().setText(self._report.toPlainText())
        self._set_status("ok", "Report copied to clipboard.")

    def _save_report(self):
        default = os.path.expanduser(f"~/Documents/kyth-health-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt")
        path, _ = QFileDialog.getSaveFileName(self, "Save Health Report", default, "Text Files (*.txt);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._report.toPlainText())
            self._set_status("ok", f"Saved to {path}.")
        except OSError as exc:
            self._set_status("err", f"Could not save: {exc}")

    def _report_issue(self):
        report = self._report.toPlainText().strip()
        if not report:
            self._set_status("warn", "Run a health report first.")
            return
        report_dir = os.path.expanduser("~/.local/state/kyth")
        body_path = os.path.join(report_dir, f"health-report-issue-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md")
        body = (
            "## What happened\n\n"
            "Describe what you were doing and what went wrong.\n\n"
            "## KythOS health report\n\n"
            "```text\n"
            f"{report}\n"
            "```\n"
        )
        try:
            os.makedirs(report_dir, exist_ok=True)
            with open(body_path, "w", encoding="utf-8") as fh:
                fh.write(body)
            popen([
                "/usr/bin/kyth-report-issue",
                "--title", "KythOS health report issue",
                "--body-file", body_path,
                "--label", "bug",
            ])
            self._set_status("ok", "Opening a prefilled GitHub issue.")
        except OSError as exc:
            self._set_status("err", f"Could not prepare issue: {exc}")
