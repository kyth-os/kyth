"""Repair page — rollback and destructive OS reset."""
from __future__ import annotations

from .services.launch import reboot

from .core_base import restyle, run_worker, set_session_inhibit
from .services.bootc import has_rollback_deployment
from .services.repair import rollback_command, reset_command
from .services.runtime import finish_worker
from .qt import single_shot


class _ResetMixin:
    def _on_confirm_text(self, text: str):
        self._reset_btn.setEnabled(text.strip() == "RESET")

    def _run_rollback(self):
        if self._worker and self._worker.isRunning():
            return
        self._confirm_edit.setEnabled(False)
        self._reset_btn.setEnabled(False)
        self._rollback_repair_btn.setEnabled(False)
        self._log_panel.reset("→ bootc rollback\n")
        self._progress.show()
        self._status_lbl.setText("Staging previous system image…")
        self._status_lbl.setObjectName("subheading")
        self._status_lbl.show()
        restyle(self._status_lbl)

        run_worker(
            self,
            rollback_command(),
            session_inhibit_reason="KythOS is staging a rollback",
            on_line=self._on_line,
            on_done=self._on_rollback_done,
        )

    def _on_rollback_done(self, code: int):
        self._progress.hide()
        finish_worker(self)
        set_session_inhibit(self, None)
        self._confirm_edit.setEnabled(True)
        self._on_confirm_text(self._confirm_edit.text())
        if code == 0:
            try:
                from kyth_shared.system.probe import invalidate_bootc
                invalidate_bootc()
            except Exception:
                pass
            self._status_lbl.setText("Rollback staged — rebooting into the previous system image…")
            self._status_lbl.setObjectName("status-ok")
            self._log_panel.append("\nDone. Rebooting now.")
            single_shot(self, 2000, reboot)
        else:
            self._status_lbl.setText(f"Rollback failed (exit code {code}).")
            self._status_lbl.setObjectName("status-err")
            self._rollback_repair_btn.setEnabled(has_rollback_deployment())
        restyle(self._status_lbl)

    def _run_reset(self):
        self._confirm_edit.setEnabled(False)
        self._reset_btn.setEnabled(False)
        self._log_panel.reset("→ bootc reset\n")
        self._progress.show()
        self._status_lbl.setText("Resetting system…")
        self._status_lbl.setObjectName("subheading")
        self._status_lbl.show()
        restyle(self._status_lbl)

        run_worker(
            self,
            reset_command(),
            session_inhibit_reason="KythOS is resetting the system image",
            on_line=self._on_line,
            on_done=self._on_done,
        )

    def _on_line(self, text: str):
        self._log_panel.append(text)

    def _on_done(self, code: int):
        self._progress.hide()
        finish_worker(self)
        set_session_inhibit(self, None)

        if code == 0:
            self._status_lbl.setText("Reset staged — rebooting…")
            self._status_lbl.setObjectName("status-ok")
            self._log_panel.append("\nDone. Rebooting now.")
            restyle(self._status_lbl)
            single_shot(self, 2000, reboot)
        else:
            self._status_lbl.setText(f"Reset failed (exit code {code}).")
            self._status_lbl.setObjectName("status-err")
            restyle(self._status_lbl)
            self._confirm_edit.setEnabled(True)
            self._confirm_edit.clear()

