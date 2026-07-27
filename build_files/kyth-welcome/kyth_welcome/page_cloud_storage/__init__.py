import os
import shutil

from ..core_base import restyle, run_worker
from .dropbox import _DropboxMixin
from .gdrive import _GoogleDriveMixin
from .onedrive import _OneDriveMixin
from .wizard import RcloneSetupWizard
from ..services.cloud_sync import RcloneSyncWorker
from ..services.launch import popen
from ..services.network import (
    _load_sync_config, _rclone_available, _rclone_list_remotes, _save_sync_config,
)
from ..services.flatpak import _is_flatpak_installed
from ..services.runtime import finish_worker
from ..services.privileged import helper_action
from ..qt import (
    QDesktopServices, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit, QUrl,
)
from ..widgets import Page


class CloudStoragePage(Page, _GoogleDriveMixin, _OneDriveMixin, _DropboxMixin):
    def __init__(self):
        super().__init__()
        self._worker = None
        self._gd_sync_worker: RcloneSyncWorker | None = None
        self._od_sync_worker: RcloneSyncWorker | None = None
        self._sync_config: dict = _load_sync_config()

        self._page_header(
            "Network & Internet",
            "Cloud Storage",
            "Connect Google Drive, OneDrive, or Dropbox to keep your files automatically in sync.",
        )

        self._build_gd_card()
        self._build_od_card()
        self._build_db_card()

        self._divider()

        refresh_row = QHBoxLayout()
        refresh_row.setSpacing(10)
        refresh_btn = QPushButton("Refresh Status")
        refresh_btn.clicked.connect(self._refresh_status)
        refresh_row.addWidget(refresh_btn)
        refresh_row.addStretch()
        self._add_layout(refresh_row)

        # ── Install progress area ────────────────────────────────────────
        self._op_status = QLabel()
        self._op_status.setObjectName("subheading")
        self._op_status.hide()
        self._add(self._op_status)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        self._add(self._progress)
        self._log = QTextEdit()
        self._log.document().setMaximumBlockCount(5000)
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(150)
        self._log.hide()
        self._add(self._log)

        self._stretch()
        self._refresh_status()

    # ── Status ────────────────────────────────────────────────────────────

    def _refresh_status(self):
        rclone = _rclone_available()
        remotes = _rclone_list_remotes() if rclone else []
        gd_remotes = [n for n, t in remotes if t == "drive"]
        od_remotes = [n for n, t in remotes if t == "onedrive"]
        db_installed = _is_flatpak_installed("com.dropbox.Client") or bool(shutil.which("dropbox"))

        # Google Drive
        if not rclone:
            self._gd_status.setText("rclone is not installed. Install it to use Google Drive.")
            self._gd_status.setObjectName("status-warn")
            self._gd_install_btn.show()
            self._gd_install_btn.setEnabled(True)
            self._gd_wizard_btn.hide()
        elif gd_remotes:
            names = ", ".join(gd_remotes)
            self._gd_status.setText(f"Configured: {names}")
            self._gd_status.setObjectName("status-ok")
            self._gd_install_btn.hide()
            self._gd_wizard_btn.setText("Add / Reconfigure…")
            self._gd_wizard_btn.show()
        else:
            self._gd_status.setText("No Google Drive remote configured yet.")
            self._gd_status.setObjectName("status-warn")
            self._gd_install_btn.hide()
            self._gd_wizard_btn.setText("Setup Wizard…")
            self._gd_wizard_btn.show()
        restyle(self._gd_status)

        # Google Drive sync status — show for any configured remote; backfill sync_config if needed
        for n in gd_remotes:
            if n not in self._sync_config:
                self._sync_config[n] = {
                    "folder": os.path.expanduser("~/GoogleDrive"),
                    "service": "drive",
                }
                _save_sync_config(self._sync_config)
        if gd_remotes:
            self._gd_sync_status.show()
            self._gd_sync_btn.show()
            self._gd_open_btn.show()
            self._gd_log_btn.show()
            self._gd_interval_lbl.show()
            self._gd_interval_combo.show()
            if not (self._gd_sync_worker and self._gd_sync_worker.isRunning()):
                self._update_gd_sync_label()
        else:
            self._gd_sync_status.hide()
            self._gd_sync_btn.hide()
            self._gd_open_btn.hide()
            self._gd_log_btn.hide()
            self._gd_sync_log.hide()
            self._gd_interval_lbl.hide()
            self._gd_interval_combo.hide()

        # OneDrive
        if not rclone:
            self._od_status.setText("rclone is not installed. Install it to use OneDrive.")
            self._od_status.setObjectName("status-warn")
            self._od_install_btn.show()
            self._od_install_btn.setEnabled(True)
            self._od_wizard_btn.hide()
        elif od_remotes:
            names = ", ".join(od_remotes)
            self._od_status.setText(f"Configured: {names}")
            self._od_status.setObjectName("status-ok")
            self._od_install_btn.hide()
            self._od_wizard_btn.setText("Add / Reconfigure…")
            self._od_wizard_btn.show()
        else:
            self._od_status.setText("No OneDrive remote configured yet.")
            self._od_status.setObjectName("status-warn")
            self._od_install_btn.hide()
            self._od_wizard_btn.setText("Setup Wizard…")
            self._od_wizard_btn.show()
        restyle(self._od_status)

        # OneDrive sync controls — backfill config entries as needed
        for n in od_remotes:
            if n not in self._sync_config:
                self._sync_config[n] = {
                    "folder": os.path.expanduser("~/OneDrive"),
                    "service": "onedrive",
                }
                _save_sync_config(self._sync_config)
        if od_remotes:
            self._od_sync_status.show()
            self._od_sync_btn.show()
            self._od_open_btn.show()
            self._od_log_btn.show()
            self._od_interval_lbl.show()
            self._od_interval_combo.show()
            if not (self._od_sync_worker and self._od_sync_worker.isRunning()):
                self._update_od_sync_label()
        else:
            self._od_sync_status.hide()
            self._od_sync_btn.hide()
            self._od_open_btn.hide()
            self._od_log_btn.hide()
            self._od_sync_log.hide()
            self._od_interval_lbl.hide()
            self._od_interval_combo.hide()

        # Dropbox
        if db_installed:
            self._db_status.setText("Dropbox is installed.")
            self._db_status.setObjectName("status-ok")
            self._db_install_btn.hide()
            self._db_launch_btn.show()
            self._db_open_btn.show()
        else:
            self._db_status.setText("Dropbox is not installed.")
            self._db_status.setObjectName("status-warn")
            self._db_install_btn.show()
            self._db_install_btn.setEnabled(True)
            self._db_launch_btn.hide()
            self._db_open_btn.hide()
        restyle(self._db_status)

    # ── Wizard launcher ───────────────────────────────────────────────────

    def _open_wizard(self, preselect: str):
        wizard = RcloneSetupWizard(self, preselect=preselect)

        def _on_wizard_done(name: str, svc: str, folder: str):
            self._sync_config[name] = {"folder": folder, "service": svc}
            _save_sync_config(self._sync_config)
            self._refresh_status()
            if svc == "drive":
                self._start_gd_sync(name, folder)
            elif svc == "onedrive":
                self._start_od_sync(name, folder)

        wizard.finished_ok.connect(_on_wizard_done)
        wizard.exec()

    # ── Open local folders (shared) ───────────────────────────────────────

    def _open_folder_in_dolphin(self, folder: str):
        os.makedirs(folder, exist_ok=True)
        try:
            popen(["dolphin", folder])
        except Exception:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # ── rclone install ────────────────────────────────────────────────────

    def _install_rclone(self):
        self._gd_install_btn.setEnabled(False)
        self._log.clear()
        self._log.append("→ Running /usr/bin/kyth-rclone-update (pinned + verified)…\n")
        self._log.show()
        self._progress.show()
        self._op_status.setText("Installing rclone…")
        self._op_status.setObjectName("subheading")
        self._op_status.show()
        restyle(self._op_status)
        run_worker(
            self,
            helper_action("rclone-update").command(),
            on_line=self._on_line,
            on_done=self._on_rclone_install_done,
        )

    def _on_rclone_install_done(self, code: int):
        self._progress.hide()
        finish_worker(self)
        if code == 0:
            self._op_status.setText(
                "rclone installed to /usr/local/bin/rclone. "
                "Use the Setup Wizard to connect your cloud accounts."
            )
            self._op_status.setObjectName("status-ok")
            self._log.append("\nDone. No reboot required.")
        else:
            self._op_status.setText(f"Installation failed (exit code {code}).")
            self._op_status.setObjectName("status-err")
            self._gd_install_btn.setEnabled(True)
        restyle(self._op_status)
        self._refresh_status()

    def _on_line(self, text: str):
        self._log.append(text)
        self._log.ensureCursorVisible()
