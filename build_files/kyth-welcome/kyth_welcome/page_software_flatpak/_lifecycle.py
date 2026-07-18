import shlex

# __KYTH_GENERATED_IMPORTS__
from ..services.launch import flatpak_run
from ..services.software import Worker, _finish_worker
from ..qt import QMessageBox, QPushButton
from ..widgets import _set_log_panel


class _LifecycleMixin:
    def _open_fp_app(self, app_id: str) -> None:
        flatpak_run(app_id)

    def _fp_install(self, app_id: str, name: str, btn: QPushButton, open_btn: QPushButton | None = None):
        if self._fp_install_worker and self._fp_install_worker.isRunning():
            return
        self._fp_installing = app_id
        btn.setText("Installing\u2026")
        btn.setEnabled(False)
        self._fp_install_log.clear()
        self._fp_install_log.append(f"\u2192 flatpak install flathub {app_id}\n")
        self._fp_install_log_toggle.show()
        _set_log_panel(self._fp_install_log_toggle, self._fp_install_log, False)
        self._fp_progress.show()
        self._set_fp_task_state(f"Installing {name or app_id}\u2026", "running")
        cmd = [
            "bash", "-c",
            "flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
            f" && flatpak install -y flathub {shlex.quote(app_id)}",
        ]
        self._fp_install_worker = Worker(cmd)
        self._fp_install_worker.line.connect(self._on_fp_install_line)
        self._fp_install_worker.done.connect(
            lambda code, aid=app_id, n=name, b=btn, ob=open_btn: self._on_fp_install_done(code, aid, n, b, ob)
        )
        self._fp_install_worker.start()

    def _on_fp_install_line(self, ln: str):
        self._fp_install_log.append(ln)
        self._fp_install_log.ensureCursorVisible()

    def _on_fp_install_done(self, code: int, app_id: str, name: str, btn: QPushButton, open_btn: QPushButton | None = None):
        self._fp_progress.hide()
        _finish_worker(self, attr="_fp_install_worker")
        self._fp_installing = None
        if code == 0:
            self._set_fp_task_state(f"{name or app_id} installed.", "success")
            self._fp_install_log.append("\nDone.")
            self._configure_fp_lifecycle_buttons(app_id, name, btn, open_btn, installed=True)
        else:
            self._set_fp_task_state(f"Install failed (exit {code}).", "error")
            _set_log_panel(self._fp_install_log_toggle, self._fp_install_log, True)
            self._configure_fp_lifecycle_buttons(app_id, name, btn, open_btn, installed=False)

    def _fp_store_uninstall(self, app_id: str, name: str, btn: QPushButton, open_btn: QPushButton | None = None):
        if (self._fp_install_worker and self._fp_install_worker.isRunning()) or \
                (self._fp_uninstall_worker and self._fp_uninstall_worker.isRunning()):
            return
        reply = QMessageBox.question(
            self,
            f"Uninstall {name or app_id}",
            f"Remove {name or app_id}?\n\n{app_id}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        btn.setText("Uninstalling\u2026")
        btn.setEnabled(False)
        self._fp_install_log.clear()
        self._fp_install_log.append(f"\u2192 flatpak uninstall -y {app_id}\n")
        self._fp_install_log_toggle.show()
        _set_log_panel(self._fp_install_log_toggle, self._fp_install_log, False)
        self._fp_progress.show()
        self._set_fp_task_state(f"Uninstalling {name or app_id}\u2026", "running")
        self._fp_uninstall_worker = Worker(["flatpak", "uninstall", "-y", app_id])
        self._fp_uninstall_worker.line.connect(self._on_fp_uninstall_line)
        self._fp_uninstall_worker.done.connect(
            lambda code, aid=app_id, n=name, b=btn, ob=open_btn: self._on_fp_store_uninstall_done(code, aid, n, b, ob)
        )
        self._fp_uninstall_worker.start()

    def _on_fp_uninstall_line(self, ln: str):
        self._fp_install_log.append(ln)
        self._fp_install_log.ensureCursorVisible()

    def _on_fp_store_uninstall_done(self, code: int, app_id: str, name: str, btn: QPushButton, open_btn: QPushButton | None = None):
        self._fp_progress.hide()
        _finish_worker(self, attr="_fp_uninstall_worker")
        if code == 0:
            self._set_fp_task_state(f"{name or app_id} uninstalled.", "success")
            self._fp_install_log.append("\nDone.")
            self._configure_fp_lifecycle_buttons(app_id, name, btn, open_btn, installed=False)
        else:
            self._set_fp_task_state(f"Uninstall failed (exit {code}).", "error")
            _set_log_panel(self._fp_install_log_toggle, self._fp_install_log, True)
            self._configure_fp_lifecycle_buttons(app_id, name, btn, open_btn, installed=True)
