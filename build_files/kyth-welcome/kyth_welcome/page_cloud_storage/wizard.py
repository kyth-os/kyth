import os
import re
from typing import ClassVar

from ..core_base import restyle
from ..services.cloud_sync import (
    RcloneAuthorizeWorker,
    rclone_create_remote,
    rclone_usage_hints,
    rclone_verify_remote,
)
from ..services.runtime import DataWorker
from ..qt import (
    QDesktopServices, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QStackedWidget, QTextEdit, QUrl, QVBoxLayout, QWidget, Qt, Signal,
)
from ..widgets import _make_card


def _apply_rclone_config(name: str, svc: str, token: str, folder: str, extra_params: list[str]):
    """Run off the GUI thread by RcloneSetupWizard's DataWorker. Raises on
    a hard failure (remote could not be created at all — the wizard stays
    on the auth page for that); a failed connection *test* is a soft
    failure the wizard still advances past, so it's returned, not raised."""
    ok, err = rclone_create_remote(name, svc, token, extra_params=extra_params or None)
    if not ok:
        raise RuntimeError(err)
    conn_ok, err_hint = rclone_verify_remote(name)
    return name, svc, folder, conn_ok, err_hint


class RcloneSetupWizard(QDialog):
    """Four-step wizard: choose service → name/folder → browser OAuth → done."""

    finished_ok = Signal(str, str, str)  # (remote_name, remote_type, local_folder)

    _SERVICES: ClassVar[dict[str, dict]] = {
        "drive": {
            "label": "Google Drive",
            "description": "Google Drive via Google OAuth. Includes Shared Drives.",
            "default_name": "gdrive",
            "default_folder": os.path.expanduser("~/GoogleDrive"),
            "docs_url": "https://rclone.org/drive/",
        },
        "onedrive": {
            "label": "OneDrive",
            "description": "Microsoft OneDrive via Microsoft OAuth. Works with personal accounts. Business / SharePoint accounts can be added via rclone config after setup.",
            "default_name": "onedrive",
            "default_folder": os.path.expanduser("~/OneDrive"),
            "docs_url": "https://rclone.org/onedrive/",
        },
    }

    def __init__(self, parent=None, preselect: str = "drive"):
        super().__init__(parent)
        self.setWindowTitle("Cloud Storage Setup — KythOS")
        self.setMinimumSize(600, 500)
        self.resize(640, 540)
        self.setModal(True)
        self.setObjectName("cloud-wizard")

        self._auth_worker: RcloneAuthorizeWorker | None = None
        self._apply_worker: DataWorker | None = None
        self._token = ""
        self._selected_service = preselect if preselect in self._SERVICES else "drive"
        self._local_folder_for_open = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──────────────────────────────────────────────────────
        header = QWidget()
        header.setObjectName("cloud-wizard-header")
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(28, 16, 28, 16)
        title_lbl = QLabel("Cloud Storage Setup")
        title_lbl.setObjectName("cloud-wizard-title")
        hdr_layout.addWidget(title_lbl)
        hdr_layout.addStretch()
        self._step_label = QLabel()
        self._step_label.setObjectName("cloud-step-label")
        hdr_layout.addWidget(self._step_label)
        root.addWidget(header)

        # ── Page stack ──────────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_service_page())   # 0
        self._stack.addWidget(self._build_remote_page())    # 1
        self._stack.addWidget(self._build_auth_page())      # 2
        self._stack.addWidget(self._build_done_page())      # 3
        root.addWidget(self._stack, 1)

        # ── Footer ──────────────────────────────────────────────────────
        footer = QWidget()
        footer.setObjectName("cloud-wizard-footer")
        ftr_layout = QHBoxLayout(footer)
        ftr_layout.setContentsMargins(28, 14, 28, 14)
        ftr_layout.setSpacing(10)
        self._back_btn = QPushButton("← Back")
        self._back_btn.clicked.connect(self._go_back)
        ftr_layout.addWidget(self._back_btn)
        ftr_layout.addStretch()
        self._next_btn = QPushButton("Next →")
        self._next_btn.setObjectName("primary")
        self._next_btn.clicked.connect(self._go_next)
        ftr_layout.addWidget(self._next_btn)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        ftr_layout.addWidget(self._cancel_btn)
        root.addWidget(footer)

        self._update_nav()

    # ── Page builders ───────────────────────────────────────────────────

    @staticmethod
    def _page_container() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(18)
        return page, layout

    def _build_service_page(self) -> QWidget:
        page, layout = self._page_container()

        heading = QLabel("Choose your cloud storage service")
        heading.setObjectName("cloud-page-heading")
        layout.addWidget(heading)

        sub = QLabel(
            "Select the service you want to connect. "
            "You can run the wizard again to add more services later."
        )
        sub.setObjectName("card-copy")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        self._service_btns: dict[str, QPushButton] = {}
        for svc_id, info in self._SERVICES.items():
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setMinimumHeight(96)
            btn.setObjectName("cloud-service")
            inner = QVBoxLayout(btn)
            inner.setContentsMargins(16, 14, 16, 14)
            inner.setSpacing(6)
            name_lbl = QLabel(info["label"])
            name_lbl.setObjectName("cloud-service-name")
            inner.addWidget(name_lbl)
            desc_lbl = QLabel(info["description"])
            desc_lbl.setWordWrap(True)
            desc_lbl.setObjectName("cloud-service-copy")
            inner.addWidget(desc_lbl)
            btn.clicked.connect(lambda _checked, s=svc_id: self._select_service(s))
            self._service_btns[svc_id] = btn
            cards_row.addWidget(btn)

        layout.addLayout(cards_row)
        layout.addStretch()
        self._select_service(self._selected_service)
        return page

    def _build_remote_page(self) -> QWidget:
        page, layout = self._page_container()

        heading = QLabel("Name and local folder")
        heading.setObjectName("cloud-page-heading")
        layout.addWidget(heading)

        sub = QLabel(
            "The remote name is used in rclone commands (e.g. rclone sync myname: ~/Folder). "
            "The local folder is where your files will appear on this machine."
        )
        sub.setObjectName("card-copy")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        form_card, form_layout = _make_card()
        form_layout.setSpacing(10)

        name_lbl = QLabel("Remote name")
        name_lbl.setObjectName("cloud-field-label")
        form_layout.addWidget(name_lbl)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. gdrive")
        form_layout.addWidget(self._name_edit)
        form_layout.addWidget(
            _hint_label("Letters, digits, hyphens and underscores only. No spaces.")
        )

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("cloud-divider")
        form_layout.addWidget(sep)

        folder_lbl = QLabel("Local sync folder")
        folder_lbl.setObjectName("cloud-field-label")
        form_layout.addWidget(folder_lbl)
        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("e.g. /home/user/GoogleDrive")
        folder_row.addWidget(self._folder_edit, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse_btn)
        form_layout.addLayout(folder_row)
        form_layout.addWidget(
            _hint_label("Folder will be created automatically if it does not exist.")
        )

        layout.addWidget(form_card)
        layout.addStretch()
        return page

    def _build_auth_page(self) -> QWidget:
        page, layout = self._page_container()

        self._auth_heading = QLabel("Authorize access")
        self._auth_heading.setObjectName("cloud-page-heading")
        layout.addWidget(self._auth_heading)

        self._auth_sub = QLabel(
            "Click the button below to open your browser and sign in. "
            "This window will update automatically once authorization is complete — "
            "you don't need to do anything else here while the browser is open."
        )
        self._auth_sub.setObjectName("card-copy")
        self._auth_sub.setWordWrap(True)
        layout.addWidget(self._auth_sub)

        auth_card, auth_card_layout = _make_card()
        auth_card_layout.setSpacing(14)

        self._auth_status_lbl = QLabel("Ready — click the button below to begin.")
        self._auth_status_lbl.setWordWrap(True)
        auth_card_layout.addWidget(self._auth_status_lbl)

        self._auth_progress = QProgressBar()
        self._auth_progress.setRange(0, 0)
        self._auth_progress.hide()
        auth_card_layout.addWidget(self._auth_progress)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._auth_start_btn = QPushButton("Open Browser & Authorize")
        self._auth_start_btn.setObjectName("primary")
        self._auth_start_btn.clicked.connect(self._start_auth)
        btn_row.addWidget(self._auth_start_btn)
        self._auth_cancel_btn = QPushButton("Cancel")
        self._auth_cancel_btn.hide()
        self._auth_cancel_btn.clicked.connect(self._cancel_auth)
        btn_row.addWidget(self._auth_cancel_btn)
        btn_row.addStretch()
        auth_card_layout.addLayout(btn_row)

        layout.addWidget(auth_card)
        layout.addStretch()
        return page

    def _build_done_page(self) -> QWidget:
        page, layout = self._page_container()

        done_heading = QLabel("All set!")
        done_heading.setObjectName("cloud-done-heading")
        layout.addWidget(done_heading)

        self._done_sub = QLabel("")
        self._done_sub.setObjectName("card-copy")
        self._done_sub.setWordWrap(True)
        layout.addWidget(self._done_sub)

        done_card, done_card_layout = _make_card()
        done_card_layout.setSpacing(12)

        self._done_summary = QLabel("")
        self._done_summary.setWordWrap(True)
        self._done_summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        done_card_layout.addWidget(self._done_summary)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("cloud-divider")
        done_card_layout.addWidget(sep)

        cmds_lbl = QLabel("Useful commands:")
        cmds_lbl.setObjectName("cloud-command-label")
        done_card_layout.addWidget(cmds_lbl)

        self._done_cmds = QTextEdit()
        self._done_cmds.document().setMaximumBlockCount(5000)
        self._done_cmds.setReadOnly(True)
        self._done_cmds.setMaximumHeight(110)
        done_card_layout.addWidget(self._done_cmds)

        open_row = QHBoxLayout()
        self._open_folder_btn = QPushButton("Open Folder in Files")
        self._open_folder_btn.clicked.connect(self._open_local_folder)
        open_row.addWidget(self._open_folder_btn)
        open_row.addStretch()
        done_card_layout.addLayout(open_row)

        layout.addWidget(done_card)
        layout.addStretch()
        return page

    # ── Navigation ──────────────────────────────────────────────────────

    def _go_next(self):
        step = self._stack.currentIndex()
        if step == 0:
            info = self._SERVICES[self._selected_service]
            self._name_edit.setText(info["default_name"])
            self._folder_edit.setText(info["default_folder"])
            self._auth_heading.setText(f"Authorize {info['label']}")
            self._stack.setCurrentIndex(1)
        elif step == 1:
            if not self._validate_remote_page():
                return
            self._stack.setCurrentIndex(2)
        elif step == 2:
            if not self._token:
                QMessageBox.warning(
                    self, "Authorization Required",
                    "Please complete browser authorization before continuing."
                )
                return
            self._start_apply_config()
            return
        elif step == 3:
            self.accept()
        self._update_nav()

    def _go_back(self):
        step = self._stack.currentIndex()
        if step == 2:
            self._cancel_auth()
        if step > 0:
            self._stack.setCurrentIndex(step - 1)
            self._update_nav()

    def _update_nav(self):
        step = self._stack.currentIndex()
        self._step_label.setText(f"Step {step + 1} of 4")
        self._back_btn.setVisible(0 < step < 3)
        self._cancel_btn.setVisible(step < 3)
        if step == 2:
            self._next_btn.setVisible(bool(self._token))
            self._next_btn.setText("Next →")
        elif step == 3:
            self._next_btn.setVisible(True)
            self._next_btn.setText("Close")
        else:
            self._next_btn.setVisible(True)
            self._next_btn.setText("Next →")

    # ── Service selection ─────────────────────────────────────────────────

    def _select_service(self, svc_id: str):
        self._selected_service = svc_id
        for sid, btn in self._service_btns.items():
            btn.setChecked(sid == svc_id)

    # ── Remote page ───────────────────────────────────────────────────────

    def _validate_remote_page(self) -> bool:
        name = self._name_edit.text().strip()
        if not name or not re.match(r'^[A-Za-z0-9_-]+$', name):
            QMessageBox.warning(
                self, "Invalid Name",
                "Remote name must contain only letters, digits, hyphens, and underscores."
            )
            return False
        folder = self._folder_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, "No Folder", "Please enter a local sync folder path.")
            return False
        return True

    def _browse_folder(self):
        current = self._folder_edit.text().strip() or os.path.expanduser("~")
        chosen = QFileDialog.getExistingDirectory(self, "Select Sync Folder", current)
        if chosen:
            self._folder_edit.setText(chosen)

    # ── Authorization flow ─────────────────────────────────────────────────

    def _start_auth(self):
        self._auth_start_btn.setEnabled(False)
        self._auth_cancel_btn.show()
        self._auth_progress.show()
        self._auth_status_lbl.setText(
            "Browser opened — please sign in and grant access, then return here."
        )
        self._auth_status_lbl.setObjectName("subheading")
        restyle(self._auth_status_lbl)

        self._auth_worker = RcloneAuthorizeWorker(self._selected_service)
        self._auth_worker.token_ready.connect(self._on_auth_success)
        self._auth_worker.failed.connect(self._on_auth_failed)
        self._auth_worker.start()

    def _cancel_auth(self):
        if self._auth_worker and self._auth_worker.isRunning():
            self._auth_worker.cancel()
            self._auth_worker.wait(2000)
        self._token = ""
        self._auth_start_btn.setEnabled(True)
        self._auth_start_btn.show()
        self._auth_cancel_btn.hide()
        self._auth_progress.hide()
        self._auth_status_lbl.setText("Ready — click the button below to begin.")
        self._auth_status_lbl.setObjectName("")
        restyle(self._auth_status_lbl)

    def _on_auth_success(self, token: str):
        self._token = token
        self._auth_progress.hide()
        self._auth_cancel_btn.hide()
        self._auth_start_btn.hide()
        self._auth_status_lbl.setText(
            "Authorization successful!  Click Next → to save and test the connection."
        )
        self._auth_status_lbl.setObjectName("status-ok")
        restyle(self._auth_status_lbl)
        self._update_nav()  # reveals Next button

    def _on_auth_failed(self, error: str):
        self._auth_start_btn.setEnabled(True)
        self._auth_cancel_btn.hide()
        self._auth_progress.hide()
        self._auth_status_lbl.setText(f"Authorization failed — {error[:200]}")
        self._auth_status_lbl.setObjectName("status-err")
        restyle(self._auth_status_lbl)

    # ── Config creation + done page ─────────────────────────────────────────

    def _set_apply_controls_enabled(self, enabled: bool) -> None:
        self._next_btn.setEnabled(enabled)
        self._back_btn.setEnabled(enabled)
        self._cancel_btn.setEnabled(enabled)

    def _start_apply_config(self):
        # rclone_create_remote/rclone_verify_remote are plain subprocess
        # calls with up to a 30s + 20s timeout — not process-group-managed
        # like Worker, so there's no safe way to cancel them mid-flight.
        # Disable navigation (see reject() override below for Escape/close)
        # instead of offering a cancel button we can't honor.
        if self._apply_worker is not None:
            return
        name = self._name_edit.text().strip()
        svc = self._selected_service
        folder = self._folder_edit.text().strip()

        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Folder Error", f"Could not create folder:\n{exc}")
            return

        # OneDrive needs drive_type so rclone can auto-select the root drive
        # without an interactive prompt.  Personal accounts work automatically;
        # business / SharePoint users can run `rclone config` manually afterward.
        extra_params: list[str] = []
        if svc == "onedrive":
            extra_params = ["drive_type", "personal"]

        self._set_apply_controls_enabled(False)
        self._auth_progress.show()
        self._auth_status_lbl.setText("Saving configuration and testing the connection…")
        self._auth_status_lbl.setObjectName("subheading")
        restyle(self._auth_status_lbl)

        self._apply_worker = DataWorker(
            "rclone-apply-config",
            lambda: _apply_rclone_config(name, svc, self._token, folder, extra_params),
        )
        self._apply_worker.result.connect(self._on_apply_config_ready)
        self._apply_worker.failed.connect(self._on_apply_config_failed)
        self._apply_worker.finished.connect(lambda: setattr(self, "_apply_worker", None))
        self._apply_worker.start()

    def _on_apply_config_ready(self, _key: str, data: object):
        name, svc, folder, conn_ok, err_hint = data
        self._set_apply_controls_enabled(True)
        self._auth_progress.hide()

        info = self._SERVICES[svc]
        if conn_ok:
            self._done_sub.setText(
                f"Your {info['label']} is configured and the connection was verified."
            )
        else:
            self._done_sub.setText(
                f"Your {info['label']} was configured, but the connection test failed.\n\n"
                f"You may need to re-run the wizard or check your account permissions.\n"
                f"Error: {err_hint}"
            )
        self._done_summary.setText(
            f"Remote name:   {name}\n"
            f"Service:            {info['label']}\n"
            f"Local folder:    {folder}"
        )
        self._done_cmds.setPlainText(rclone_usage_hints(name, folder))
        self._local_folder_for_open = folder
        self._stack.setCurrentIndex(3)
        self._update_nav()
        # Always emit so the cloud page registers the folder and shows sync controls,
        # even if the connection test failed (config is on disk regardless)
        self.finished_ok.emit(name, svc, folder)

    def _on_apply_config_failed(self, _key: str, message: str):
        self._set_apply_controls_enabled(True)
        self._auth_progress.hide()
        self._auth_status_lbl.setText(
            "Authorization successful!  Click Next → to save and test the connection."
        )
        self._auth_status_lbl.setObjectName("status-ok")
        restyle(self._auth_status_lbl)
        title = "rclone Not Found" if "not installed" in message.lower() else "Config Error"
        QMessageBox.critical(self, title, f"Failed to write rclone config:\n{message}")

    def reject(self):
        if self._apply_worker is not None:
            # Ignore Escape/window-close while the background config apply
            # is running — its underlying subprocess calls aren't
            # cancellable, so closing here would leave a worker running
            # against a dialog about to be destroyed.
            return
        super().reject()

    def _open_local_folder(self):
        if self._local_folder_for_open and os.path.isdir(self._local_folder_for_open):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._local_folder_for_open))


def _hint_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("card-copy")
    lbl.setWordWrap(True)
    return lbl
