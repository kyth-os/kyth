from .services.launch import reboot
"""Repair page — rollback and destructive OS reset."""
from __future__ import annotations


from .core_base import (
    _has_rollback_deployment, _restyle, _set_session_inhibit,
)
from .services.repair import rollback_command, reset_command
from .services.software import Worker, _finish_worker
from .qt import QTimer
from .widgets import _set_log_panel


class _ResetMixin:
    def _on_confirm_text(self, text: str):
        self._reset_btn.setEnabled(text.strip() == "RESET")

    def _run_rollback(self):
        if self._worker and self._worker.isRunning():
            return
        self._confirm_edit.setEnabled(False)
        self._reset_btn.setEnabled(False)
        self._rollback_repair_btn.setEnabled(False)
        self._log.clear()
        self._log.append("→ bootc rollback\n")
        self._log_toggle.show()
        _set_log_panel(self._log_toggle, self._log, False)
        self._progress.show()
        self._status_lbl.setText("Staging previous system image…")
        self._status_lbl.setObjectName("subheading")
        self._status_lbl.show()
        _restyle(self._status_lbl)

        self._worker = Worker(rollback_command())
        _set_session_inhibit(self, "KythOS is staging a rollback")
        self._worker.line.connect(self._on_line)
        self._worker.done.connect(self._on_rollback_done)
        self._worker.start()

    def _on_rollback_done(self, code: int):
        self._progress.hide()
        _finish_worker(self)
        _set_session_inhibit(self, None)
        self._confirm_edit.setEnabled(True)
        self._on_confirm_text(self._confirm_edit.text())
        if code == 0:
            self._status_lbl.setText("Rollback staged — rebooting into the previous system image…")
            self._status_lbl.setObjectName("status-ok")
            self._log.append("\nDone. Rebooting now.")
            QTimer.singleShot(2000, lambda: reboot())
        else:
            self._status_lbl.setText(f"Rollback failed (exit code {code}).")
            self._status_lbl.setObjectName("status-err")
            self._rollback_repair_btn.setEnabled(_has_rollback_deployment())
        _restyle(self._status_lbl)

    def _run_reset(self):
        self._confirm_edit.setEnabled(False)
        self._reset_btn.setEnabled(False)
        self._log.clear()
        self._log.append("→ bootc reset\n")
        self._log_toggle.show()
        _set_log_panel(self._log_toggle, self._log, False)
        self._progress.show()
        self._status_lbl.setText("Resetting system…")
        self._status_lbl.setObjectName("subheading")
        self._status_lbl.show()
        _restyle(self._status_lbl)

        self._worker = Worker(reset_command())
        _set_session_inhibit(self, "KythOS is resetting the system image")
        self._worker.line.connect(self._on_line)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_line(self, text: str):
        self._log.append(text)
        self._log.ensureCursorVisible()

    def _on_done(self, code: int):
        self._progress.hide()
        _finish_worker(self)
        _set_session_inhibit(self, None)

        if code == 0:
            self._status_lbl.setText("Reset staged — rebooting…")
            self._status_lbl.setObjectName("status-ok")
            self._log.append("\nDone. Rebooting now.")
            _restyle(self._status_lbl)
            QTimer.singleShot(2000, lambda: reboot())
        else:
            self._status_lbl.setText(f"Reset failed (exit code {code}).")
            self._status_lbl.setObjectName("status-err")
            _restyle(self._status_lbl)
            self._confirm_edit.setEnabled(True)
            self._confirm_edit.clear()

