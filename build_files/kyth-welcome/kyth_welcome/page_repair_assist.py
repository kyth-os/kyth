"""Repair page — remote assist, setup transfer, session snapshot."""
from __future__ import annotations

import os
import shutil

from .services.launch import flatpak_run, popen

from .services.repair import (
    session_snapshot_command,
    setup_export_command,
    setup_restore_command,
    setup_summary_command,
    setup_transfer_helper,
)
from .actions import _install_flatpak_inline
from .services.flatpak import _is_flatpak_installed
from .services.runtime import Worker, finish_worker
from .qt import QFileDialog, QMessageBox


class _AssistMixin:
    def _refresh_rustdesk_btn(self):
        installed = _is_flatpak_installed("com.rustdesk.RustDesk")
        self._rustdesk_btn.setText("Open RustDesk — Get Help" if installed else "Install RustDesk — Get Help")

    def _open_or_install_rustdesk(self):
        app_id = "com.rustdesk.RustDesk"
        if _is_flatpak_installed(app_id):
            try:
                flatpak_run(app_id)
                self._assist_status.setText(
                    "Share only the temporary ID and one-time password with someone you trust. "
                    "Close RustDesk when the support session is finished."
                )
            except OSError as exc:
                self._assist_status.setText(f"Could not open RustDesk: {exc}")
            return

        def _installed(code: int):
            if code == 0:
                self._rustdesk_btn.setEnabled(True)
                self._refresh_rustdesk_btn()
                self._assist_status.setText("RustDesk installed. Open it when your helper is ready.")

        _install_flatpak_inline(
            self, self._rustdesk_btn, app_id, "RustDesk", done_cb=_installed,
        )

    def _open_krdc(self):
        if shutil.which("krdc"):
            try:
                popen(["krdc"])
                self._assist_status.setText("KRDC opened — enter an rdp:// or vnc:// address to help another PC.")
            except OSError as exc:
                self._assist_status.setText(f"Could not open KRDC: {exc}")
        else:
            self._assist_status.setText(
                "KRDC will be available after applying the latest KythOS update and restarting."
            )

    def _create_assist_snapshot(self):
        if self._assist_worker is not None and self._assist_worker.isRunning():
            return
        self._assist_status.setText("Creating a support snapshot…")
        worker = Worker(session_snapshot_command())
        worker.line.connect(lambda line: self._assist_status.setText(line.strip() or "Snapshot created."))
        worker.done.connect(self._on_assist_snapshot_done)
        self._assist_worker = worker
        worker.start()

    def _on_assist_snapshot_done(self, code: int):
        finish_worker(self, attr="_assist_worker")
        if code != 0:
            self._assist_status.setText(f"Support snapshot failed (exit {code}).")

    @staticmethod
    def _setup_transfer_helper() -> str:
        return setup_transfer_helper()

    def _set_setup_busy(self, busy: bool):
        self._setup_export_btn.setEnabled(not busy)
        self._setup_restore_btn.setEnabled(not busy)

    def _export_setup(self):
        if self._setup_worker is not None and self._setup_worker.isRunning():
            return
        destination = QFileDialog.getExistingDirectory(
            self, "Choose where to save your KythOS setup", os.path.expanduser("~/Documents")
        )
        if not destination:
            return
        helper = self._setup_transfer_helper()
        if not os.path.exists(helper):
            self._setup_status.setText("Setup transfer is available after the next KythOS update and restart.")
            return
        self._setup_operation = "export"
        self._set_setup_busy(True)
        self._setup_status.setText("Collecting apps and preferences…")
        worker = Worker(setup_export_command(destination))
        worker.line.connect(lambda line: self._setup_status.setText(line.strip() or "Exporting setup…"))
        worker.done.connect(self._on_setup_transfer_done)
        self._setup_worker = worker
        worker.start()

    def _restore_setup(self):
        if self._setup_worker is not None and self._setup_worker.isRunning():
            return
        archive, _ = QFileDialog.getOpenFileName(
            self, "Choose a KythOS setup archive", os.path.expanduser("~"),
            "KythOS setup archives (kyth-setup-*.tar.gz);;Tar archives (*.tar.gz)",
        )
        if not archive:
            return
        helper = self._setup_transfer_helper()
        if not os.path.exists(helper):
            self._setup_status.setText("Setup transfer is available after the next KythOS update and restart.")
            return
        from .services.process import run_command
        result = run_command(setup_summary_command(archive), timeout=15)
        if result is None:
            QMessageBox.warning(self, "Could not inspect archive", "command failed to start")
            return
        if result.returncode != 0:
            QMessageBox.warning(
                self, "Invalid setup archive", (result.stderr or result.stdout).strip()
            )
            return
        answer = QMessageBox.question(
            self, "Restore this PC setup?",
            result.stdout.strip()
            + "\n\nExisting preferences with the same names will be replaced. Continue?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._setup_operation = "restore"
        self._set_setup_busy(True)
        self._setup_status.setText("Restoring preferences and applications…")
        worker = Worker(setup_restore_command(archive))
        worker.line.connect(lambda line: self._setup_status.setText(line.strip() or "Restoring setup…"))
        worker.done.connect(self._on_setup_transfer_done)
        self._setup_worker = worker
        worker.start()

    def _on_setup_transfer_done(self, code: int):
        operation = self._setup_operation
        finish_worker(self, attr="_setup_worker")
        self._set_setup_busy(False)
        if code == 0 and operation == "restore":
            self._setup_status.setText(
                "Setup restored. Reconnect cloud accounts, re-enter network-share passwords, "
                "then sign out and back in to apply desktop shortcuts and preferences."
            )
        elif code != 0:
            self._setup_status.setText(f"Setup {operation or 'transfer'} failed (exit {code}).")

    def _run_session_snapshot(self):
        if self._snapshot_worker and self._snapshot_worker.isRunning():
            return
        self._snapshot_btn.setEnabled(False)
        self._snapshot_status.setText("Creating snapshot…")
        self._snapshot_worker = Worker(session_snapshot_command())
        self._snapshot_worker.line.connect(lambda ln: self._snapshot_status.setText(ln.strip() or "Snapshot created."))
        self._snapshot_worker.done.connect(self._on_snapshot_done)
        self._snapshot_worker.start()

    def _on_snapshot_done(self, code: int):
        finish_worker(self, attr="_snapshot_worker")
        self._snapshot_btn.setEnabled(True)
        if code != 0:
            self._snapshot_status.setText(f"Snapshot failed (exit {code}).")

