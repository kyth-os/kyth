import os
import re
import shutil
import subprocess
import time
from datetime import datetime

# __KYTH_GENERATED_IMPORTS__
from .core import (  # noqa: E501
    Worker, _finish_worker, _is_flatpak_installed, _load_sync_config, _rclone_available, _rclone_list_remotes, _restyle, _save_sync_config,
)
from .qt import (  # noqa: E501
    QApplication, QComboBox, QDesktopServices, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QStackedWidget, QTextEdit, QThread, QTimer, QUrl, QVBoxLayout, QWidget, Qt, Signal,
)
from .widgets import (  # noqa: E501
    Page, _make_card,
)

class SteamCopyWorker(QThread):
    """Copies a steamapps directory using rsync, streaming output line-by-line."""
    line = Signal(str)
    done = Signal(int)

    def __init__(self, src: str, dst: str):
        super().__init__()
        self._src = src
        self._dst = dst
        self._proc = None

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def run(self):
        try:
            os.makedirs(self._dst, exist_ok=True)
        except OSError as exc:
            self.line.emit(f"Error creating destination: {exc}")
            self.done.emit(1)
            return
        cmd = [
            "rsync", "-a", "--info=name1,progress2", "--no-inc-recursive",
            self._src.rstrip("/") + "/",
            self._dst.rstrip("/") + "/",
        ]
        self.line.emit(f"→ {' '.join(cmd)}\n")
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for ln in self._proc.stdout:
                self.line.emit(ln.rstrip())
            self._proc.wait()
            self.done.emit(self._proc.returncode)
        except Exception as exc:
            self.line.emit(f"Error: {exc}")
            self.done.emit(1)


def _launch_opt_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size: 12px; color: #888888; min-width: 130px;")
    return lbl


def _launch_opt_value(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lbl.setStyleSheet(
        "font-family: 'Noto Mono', 'Cascadia Code', monospace; "
        "font-size: 12px; color: #c0c0c0; "
        "background: #060606; border: 1px solid #1e1e1e; "
        "border-radius: 4px; padding: 3px 8px;"
    )
    return lbl


def _copy_text(text: str):
    QApplication.clipboard().setText(text)


# ── rclone OAuth authorization worker ────────────────────────────────────────
class RcloneAuthorizeWorker(QThread):
    """Runs `rclone authorize <type>` in the background; emits the token JSON on success."""
    token_ready = Signal(str)
    failed = Signal(str)

    def __init__(self, remote_type: str):
        super().__init__()
        self._remote_type = remote_type
        self._proc = None

    def run(self):
        try:
            self._proc = subprocess.Popen(
                ["rclone", "authorize", self._remote_type],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,  # prevent rclone blocking on interactive prompts
                text=True,
            )
            stdout, stderr = self._proc.communicate(timeout=300)
            if self._proc.returncode != 0 and not stdout.strip():
                self.failed.emit(
                    f"rclone authorize exited with code {self._proc.returncode}.\n\n"
                    f"{stderr.strip()[:400]}"
                )
                return
            token = self._extract_token(stdout) or self._extract_token(stderr)
            if token:
                self.token_ready.emit(token)
            else:
                combined = (stdout + stderr).strip()
                self.failed.emit(
                    "Authorization completed but could not parse the token.\n\n"
                    f"Output:\n{combined[:600]}"
                )
        except subprocess.TimeoutExpired:
            if self._proc:
                self._proc.kill()
            self.failed.emit("Authorization timed out after 5 minutes.")
        except Exception as exc:
            self.failed.emit(str(exc))

    @staticmethod
    def _extract_token(text: str) -> str | None:
        start_marker = "Paste the following into your remote machine --->"
        end_marker = "<---End paste"
        if start_marker in text and end_marker in text:
            start = text.index(start_marker) + len(start_marker)
            end = text.index(end_marker, start)
            candidate = text[start:end].strip()
            if candidate.startswith("{"):
                return candidate
        m = re.search(r'\{"access_token"[^<>]*\}', text, re.DOTALL)
        if m:
            return m.group(0)
        return None

    def cancel(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


# ── rclone background sync worker ─────────────────────────────────────────────
class RcloneSyncWorker(QThread):
    """Runs `rclone sync remote: folder --progress` and streams output lines."""
    line = Signal(str)
    done = Signal(int)

    def __init__(self, remote: str, folder: str):
        super().__init__()
        self._remote = remote
        self._folder = folder

    def run(self):
        try:
            proc = subprocess.Popen(
                ["rclone", "sync", f"{self._remote}:", self._folder,
                 "--progress", "--stats-one-line", "--stats=2s"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for ln in proc.stdout:
                self.line.emit(ln.rstrip())
            proc.wait()
            self.done.emit(proc.returncode)
        except Exception as exc:
            self.line.emit(f"Error: {exc}")
            self.done.emit(1)


# ── rclone setup wizard dialog ────────────────────────────────────────────────
class RcloneSetupWizard(QDialog):
    """Four-step wizard: choose service → name/folder → browser OAuth → done."""

    finished_ok = Signal(str, str, str)  # (remote_name, remote_type, local_folder)

    _SERVICES: dict[str, dict] = {
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
        self.setStyleSheet("background: #1e1e1e;")

        self._auth_worker: RcloneAuthorizeWorker | None = None
        self._token = ""
        self._selected_service = preselect if preselect in self._SERVICES else "drive"
        self._local_folder_for_open = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ─────────────────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet(
            "QWidget { background: #1b1b1c; border-bottom: 1px solid #2e2e2e; }"
        )
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(28, 16, 28, 16)
        title_lbl = QLabel("Cloud Storage Setup")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
        hdr_layout.addWidget(title_lbl)
        hdr_layout.addStretch()
        self._step_label = QLabel()
        self._step_label.setStyleSheet("font-size: 12px; color: #858585;")
        hdr_layout.addWidget(self._step_label)
        root.addWidget(header)

        # ── Page stack ─────────────────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_service_page())   # 0
        self._stack.addWidget(self._build_remote_page())    # 1
        self._stack.addWidget(self._build_auth_page())      # 2
        self._stack.addWidget(self._build_done_page())      # 3
        root.addWidget(self._stack, 1)

        # ── Footer ─────────────────────────────────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet(
            "QWidget { background: #181818; border-top: 1px solid #2b2b2b; }"
        )
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

    # ── Page builders ──────────────────────────────────────────────────────────

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
        heading.setStyleSheet("font-size: 17px; font-weight: 700; color: #ffffff;")
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
            btn.setStyleSheet("QPushButton { text-align: left; border-radius: 8px; }")
            inner = QVBoxLayout(btn)
            inner.setContentsMargins(16, 14, 16, 14)
            inner.setSpacing(6)
            name_lbl = QLabel(info["label"])
            name_lbl.setStyleSheet(
                "font-size: 14px; font-weight: 700; background: transparent; border: none;"
            )
            inner.addWidget(name_lbl)
            desc_lbl = QLabel(info["description"])
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(
                "font-size: 12px; color: #a6a6a6; background: transparent; border: none;"
            )
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
        heading.setStyleSheet("font-size: 17px; font-weight: 700; color: #ffffff;")
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
        name_lbl.setStyleSheet("font-weight: 600; color: #cccccc;")
        form_layout.addWidget(name_lbl)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. gdrive")
        form_layout.addWidget(self._name_edit)
        form_layout.addWidget(
            _hint_label("Letters, digits, hyphens and underscores only. No spaces.")
        )

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #26293a; max-height: 1px; border: none;")
        form_layout.addWidget(sep)

        folder_lbl = QLabel("Local sync folder")
        folder_lbl.setStyleSheet("font-weight: 600; color: #cccccc;")
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
        self._auth_heading.setStyleSheet(
            "font-size: 17px; font-weight: 700; color: #ffffff;"
        )
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
        done_heading.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #4dbb6f;"
        )
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
        sep.setStyleSheet("background: #26293a; max-height: 1px; border: none;")
        done_card_layout.addWidget(sep)

        cmds_lbl = QLabel("Useful commands:")
        cmds_lbl.setStyleSheet("font-weight: 600; color: #cccccc; font-size: 13px;")
        done_card_layout.addWidget(cmds_lbl)

        self._done_cmds = QTextEdit()
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

    # ── Navigation ─────────────────────────────────────────────────────────────

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
            self._apply_config()
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

    # ── Service selection ──────────────────────────────────────────────────────

    def _select_service(self, svc_id: str):
        self._selected_service = svc_id
        for sid, btn in self._service_btns.items():
            if sid == svc_id:
                btn.setChecked(True)
                btn.setStyleSheet(
                    "QPushButton { background: rgba(79, 140, 255, 0.18); "
                    "border: 2px solid #4f8cff; "
                    "border-radius: 6px; text-align: left; }"
                )
            else:
                btn.setChecked(False)
                btn.setStyleSheet(
                    "QPushButton { background: #151722; border: 1px solid #26293a; "
                    "border-radius: 8px; text-align: left; }"
                )

    # ── Remote page ────────────────────────────────────────────────────────────

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

    # ── Authorization flow ─────────────────────────────────────────────────────

    def _start_auth(self):
        self._auth_start_btn.setEnabled(False)
        self._auth_cancel_btn.show()
        self._auth_progress.show()
        self._auth_status_lbl.setText(
            "Browser opened — please sign in and grant access, then return here."
        )
        self._auth_status_lbl.setObjectName("subheading")
        _restyle(self._auth_status_lbl)

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
        _restyle(self._auth_status_lbl)

    def _on_auth_success(self, token: str):
        self._token = token
        self._auth_progress.hide()
        self._auth_cancel_btn.hide()
        self._auth_start_btn.hide()
        self._auth_status_lbl.setText(
            "Authorization successful!  Click Next → to save and test the connection."
        )
        self._auth_status_lbl.setObjectName("status-ok")
        _restyle(self._auth_status_lbl)
        self._update_nav()  # reveals Next button

    def _on_auth_failed(self, error: str):
        self._auth_start_btn.setEnabled(True)
        self._auth_cancel_btn.hide()
        self._auth_progress.hide()
        self._auth_status_lbl.setText(f"Authorization failed — {error[:200]}")
        self._auth_status_lbl.setObjectName("status-err")
        _restyle(self._auth_status_lbl)

    # ── Config creation + done page ────────────────────────────────────────────

    def _apply_config(self):
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

        try:
            result = subprocess.run(
                ["rclone", "config", "create", name, svc,
                 "token", self._token, *extra_params, "--non-interactive"],
                capture_output=True, text=True, timeout=30,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            QMessageBox.critical(self, "rclone Not Found",
                                 "rclone is not installed or not on PATH.")
            return
        except subprocess.TimeoutExpired:
            QMessageBox.critical(self, "Config Timeout",
                                 "rclone config create timed out. "
                                 "Check that rclone is working correctly.")
            return
        except Exception as exc:
            QMessageBox.critical(self, "Config Error",
                                 f"Unexpected error running rclone:\n{exc}")
            return
        if result.returncode != 0:
            QMessageBox.critical(
                self, "Config Error",
                f"Failed to write rclone config:\n{result.stderr.strip()[:300]}"
            )
            return

        # Verify the remote actually works by listing the root
        verify = subprocess.run(
            ["rclone", "lsd", f"{name}:", "--max-depth", "0"],
            capture_output=True, text=True, timeout=20,
            stdin=subprocess.DEVNULL,
        )
        conn_ok = verify.returncode == 0

        info = self._SERVICES[svc]
        if conn_ok:
            self._done_sub.setText(
                f"Your {info['label']} is configured and the connection was verified."
            )
        else:
            err_hint = verify.stderr.strip()[:200]
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
        self._done_cmds.setPlainText(
            f"# Sync cloud → local (one-shot):\n"
            f"rclone sync {name}: {folder} --progress\n\n"
            f"# Mount as a virtual drive (stays open until unmounted):\n"
            f"rclone mount {name}: {folder} --daemon --vfs-cache-mode full"
        )
        self._local_folder_for_open = folder
        self._stack.setCurrentIndex(3)
        self._update_nav()
        # Always emit so the cloud page registers the folder and shows sync controls,
        # even if the connection test failed (config is on disk regardless)
        self.finished_ok.emit(name, svc, folder)

    def _open_local_folder(self):
        if self._local_folder_for_open and os.path.isdir(self._local_folder_for_open):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._local_folder_for_open))


def _hint_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("card-copy")
    lbl.setWordWrap(True)
    return lbl


# ── Page: Cloud Storage ───────────────────────────────────────────────────────
class CloudStoragePage(Page):
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

        # ── Google Drive card ─────────────────────────────────────────────────
        gd_card, gd_layout = _make_card()
        gd_title = QLabel("Google Drive")
        gd_title.setObjectName("card-title")
        gd_layout.addWidget(gd_title)
        gd_desc = QLabel(
            "Sync or mount your Google Drive via rclone. "
            "The setup wizard handles browser OAuth — no terminal required."
        )
        gd_desc.setObjectName("card-copy")
        gd_desc.setWordWrap(True)
        gd_layout.addWidget(gd_desc)
        self._gd_status = QLabel()
        self._gd_status.setWordWrap(True)
        gd_layout.addWidget(self._gd_status)
        gd_btns = QHBoxLayout()
        gd_btns.setSpacing(10)
        self._gd_install_btn = QPushButton("Install rclone first")
        self._gd_install_btn.setObjectName("primary")
        self._gd_install_btn.hide()
        self._gd_install_btn.clicked.connect(self._install_rclone)
        gd_btns.addWidget(self._gd_install_btn)
        self._gd_wizard_btn = QPushButton("Setup Wizard…")
        self._gd_wizard_btn.setObjectName("primary")
        self._gd_wizard_btn.clicked.connect(lambda: self._open_wizard("drive"))
        gd_btns.addWidget(self._gd_wizard_btn)
        gd_btns.addStretch()
        gd_layout.addLayout(gd_btns)

        # Sync status row
        self._gd_sync_status = QLabel()
        self._gd_sync_status.setWordWrap(True)
        self._gd_sync_status.setObjectName("card-copy")
        self._gd_sync_status.hide()
        gd_layout.addWidget(self._gd_sync_status)
        gd_sync_btns = QHBoxLayout()
        gd_sync_btns.setSpacing(10)
        self._gd_sync_btn = QPushButton("Sync Now")
        self._gd_sync_btn.clicked.connect(lambda: self._start_gd_sync())
        self._gd_sync_btn.hide()
        gd_sync_btns.addWidget(self._gd_sync_btn)
        self._gd_open_btn = QPushButton("Open Local Folder")
        self._gd_open_btn.clicked.connect(self._open_gd_folder)
        self._gd_open_btn.hide()
        gd_sync_btns.addWidget(self._gd_open_btn)
        self._gd_log_btn = QPushButton("Sync Log")
        self._gd_log_btn.hide()
        self._gd_log_btn.clicked.connect(self._toggle_gd_sync_log)
        gd_sync_btns.addWidget(self._gd_log_btn)
        gd_sync_btns.addStretch()
        gd_layout.addLayout(gd_sync_btns)

        # Sync interval row
        gd_interval_row = QHBoxLayout()
        gd_interval_row.setSpacing(8)
        self._gd_interval_lbl = QLabel("Auto-sync interval:")
        self._gd_interval_lbl.setObjectName("card-copy")
        self._gd_interval_lbl.hide()
        gd_interval_row.addWidget(self._gd_interval_lbl)
        self._gd_interval_combo = QComboBox()
        for label, mins in (
            ("Every 5 minutes",  5),
            ("Every 10 minutes", 10),
            ("Every 15 minutes", 15),
            ("Every 30 minutes", 30),
            ("Every hour",       60),
            ("Manual only",      0),
        ):
            self._gd_interval_combo.addItem(label, mins)
        saved_mins = self._sync_config.get("_sync_interval_min", 5)
        for i in range(self._gd_interval_combo.count()):
            if self._gd_interval_combo.itemData(i) == saved_mins:
                self._gd_interval_combo.setCurrentIndex(i)
                break
        self._gd_interval_combo.currentIndexChanged.connect(self._on_interval_changed)
        self._gd_interval_combo.hide()
        gd_interval_row.addWidget(self._gd_interval_combo)
        gd_interval_row.addStretch()
        gd_layout.addLayout(gd_interval_row)

        self._gd_sync_log = QTextEdit()
        self._gd_sync_log.setReadOnly(True)
        self._gd_sync_log.setMaximumHeight(100)
        self._gd_sync_log.setObjectName("card-copy")
        self._gd_sync_log.setPlaceholderText("Sync output will appear here…")
        self._gd_sync_log.hide()
        gd_layout.addWidget(self._gd_sync_log)
        self._gd_sync_log_visible = False
        self._gd_last_sync_lines: list[str] = []

        self._add(gd_card)

        # Periodic GD sync timer — interval loaded from config (default 5 min)
        _startup_mins = self._sync_config.get("_sync_interval_min", 5)
        self._gd_sync_timer = QTimer(self)
        self._gd_sync_timer.timeout.connect(lambda: self._start_gd_sync())
        if _startup_mins > 0:
            self._gd_sync_timer.setInterval(_startup_mins * 60 * 1000)
            self._gd_sync_timer.start()

        # ── OneDrive card ─────────────────────────────────────────────────────
        od_card, od_layout = _make_card()
        od_title = QLabel("OneDrive")
        od_title.setObjectName("card-title")
        od_layout.addWidget(od_title)
        od_desc = QLabel(
            "Sync your Microsoft OneDrive via rclone. "
            "The setup wizard handles Microsoft OAuth in your browser — no terminal required. "
            "Works with personal accounts; business / SharePoint accounts can be configured "
            "manually with rclone config after the initial setup."
        )
        od_desc.setObjectName("card-copy")
        od_desc.setWordWrap(True)
        od_layout.addWidget(od_desc)
        self._od_status = QLabel()
        self._od_status.setWordWrap(True)
        od_layout.addWidget(self._od_status)
        od_btns = QHBoxLayout()
        od_btns.setSpacing(10)
        self._od_install_btn = QPushButton("Install rclone first")
        self._od_install_btn.setObjectName("primary")
        self._od_install_btn.hide()
        self._od_install_btn.clicked.connect(self._install_rclone)
        od_btns.addWidget(self._od_install_btn)
        self._od_wizard_btn = QPushButton("Setup Wizard…")
        self._od_wizard_btn.setObjectName("primary")
        self._od_wizard_btn.clicked.connect(lambda: self._open_wizard("onedrive"))
        od_btns.addWidget(self._od_wizard_btn)
        od_btns.addStretch()
        od_layout.addLayout(od_btns)

        # OneDrive sync status + controls
        self._od_sync_status = QLabel()
        self._od_sync_status.setWordWrap(True)
        self._od_sync_status.setObjectName("card-copy")
        self._od_sync_status.hide()
        od_layout.addWidget(self._od_sync_status)
        od_sync_btns = QHBoxLayout()
        od_sync_btns.setSpacing(10)
        self._od_sync_btn = QPushButton("Sync Now")
        self._od_sync_btn.clicked.connect(lambda: self._start_od_sync())
        self._od_sync_btn.hide()
        od_sync_btns.addWidget(self._od_sync_btn)
        self._od_open_btn = QPushButton("Open Local Folder")
        self._od_open_btn.clicked.connect(self._open_od_folder)
        self._od_open_btn.hide()
        od_sync_btns.addWidget(self._od_open_btn)
        self._od_log_btn = QPushButton("Sync Log")
        self._od_log_btn.hide()
        self._od_log_btn.clicked.connect(self._toggle_od_sync_log)
        od_sync_btns.addWidget(self._od_log_btn)
        od_sync_btns.addStretch()
        od_layout.addLayout(od_sync_btns)

        # OneDrive interval row
        od_interval_row = QHBoxLayout()
        od_interval_row.setSpacing(8)
        self._od_interval_lbl = QLabel("Auto-sync interval:")
        self._od_interval_lbl.setObjectName("card-copy")
        self._od_interval_lbl.hide()
        od_interval_row.addWidget(self._od_interval_lbl)
        self._od_interval_combo = QComboBox()
        for label, mins in (
            ("Every 5 minutes",  5),
            ("Every 10 minutes", 10),
            ("Every 15 minutes", 15),
            ("Every 30 minutes", 30),
            ("Every hour",       60),
            ("Manual only",      0),
        ):
            self._od_interval_combo.addItem(label, mins)
        od_saved_mins = self._sync_config.get("_od_sync_interval_min", 5)
        for i in range(self._od_interval_combo.count()):
            if self._od_interval_combo.itemData(i) == od_saved_mins:
                self._od_interval_combo.setCurrentIndex(i)
                break
        self._od_interval_combo.currentIndexChanged.connect(self._on_od_interval_changed)
        self._od_interval_combo.hide()
        od_interval_row.addWidget(self._od_interval_combo)
        od_interval_row.addStretch()
        od_layout.addLayout(od_interval_row)

        self._od_sync_log = QTextEdit()
        self._od_sync_log.setReadOnly(True)
        self._od_sync_log.setMaximumHeight(100)
        self._od_sync_log.setObjectName("card-copy")
        self._od_sync_log.setPlaceholderText("Sync output will appear here…")
        self._od_sync_log.hide()
        od_layout.addWidget(self._od_sync_log)
        self._od_sync_log_visible = False
        self._od_last_sync_lines: list[str] = []

        self._add(od_card)

        # Periodic OneDrive sync timer
        _od_startup_mins = self._sync_config.get("_od_sync_interval_min", 5)
        self._od_sync_timer = QTimer(self)
        self._od_sync_timer.timeout.connect(lambda: self._start_od_sync())
        if _od_startup_mins > 0:
            self._od_sync_timer.setInterval(_od_startup_mins * 60 * 1000)
            self._od_sync_timer.start()

        # ── Dropbox card ──────────────────────────────────────────────────────
        db_card, db_layout = _make_card()
        db_title = QLabel("Dropbox")
        db_title.setObjectName("card-title")
        db_layout.addWidget(db_title)
        db_desc = QLabel(
            "Official Dropbox client via Flatpak. Syncs ~/Dropbox automatically "
            "in the background and adds a system tray icon."
        )
        db_desc.setObjectName("card-copy")
        db_desc.setWordWrap(True)
        db_layout.addWidget(db_desc)
        self._db_status = QLabel()
        self._db_status.setWordWrap(True)
        db_layout.addWidget(self._db_status)
        db_btns = QHBoxLayout()
        db_btns.setSpacing(10)
        self._db_install_btn = QPushButton("Install via Flatpak")
        self._db_install_btn.setObjectName("primary")
        self._db_install_btn.clicked.connect(self._install_dropbox)
        db_btns.addWidget(self._db_install_btn)
        self._db_launch_btn = QPushButton("Launch Dropbox")
        self._db_launch_btn.clicked.connect(self._launch_dropbox)
        db_btns.addWidget(self._db_launch_btn)
        self._db_open_btn = QPushButton("Open Local Folder")
        self._db_open_btn.clicked.connect(self._open_db_folder)
        self._db_open_btn.hide()
        db_btns.addWidget(self._db_open_btn)
        db_btns.addStretch()
        db_layout.addLayout(db_btns)
        self._add(db_card)

        self._divider()

        refresh_row = QHBoxLayout()
        refresh_row.setSpacing(10)
        refresh_btn = QPushButton("Refresh Status")
        refresh_btn.clicked.connect(self._refresh_status)
        refresh_row.addWidget(refresh_btn)
        refresh_row.addStretch()
        self._add_layout(refresh_row)

        # ── Install progress area ─────────────────────────────────────────────
        self._op_status = QLabel()
        self._op_status.setObjectName("subheading")
        self._op_status.hide()
        self._add(self._op_status)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        self._add(self._progress)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(150)
        self._log.hide()
        self._add(self._log)

        self._stretch()
        self._refresh_status()

    # ── Status ─────────────────────────────────────────────────────────────────

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
        _restyle(self._gd_status)

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
        _restyle(self._od_status)

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
        _restyle(self._db_status)

    # ── Wizard launcher ────────────────────────────────────────────────────────

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

    def _update_gd_sync_label(self):
        """Refresh the Google Drive sync status label from stored config."""
        mins = self._sync_config.get("_sync_interval_min", 5)
        if mins == 0:
            interval_str = "manual sync only"
        elif mins < 60:
            interval_str = f"every {mins} min"
        else:
            interval_str = "every hour"

        for name, info in self._sync_config.items():
            if info.get("service") != "drive":
                continue
            last = info.get("last_sync")
            ok = info.get("last_ok", True)
            if last:
                ts = datetime.fromtimestamp(last).strftime("%H:%M")
                if ok:
                    self._gd_sync_status.setText(
                        f"Last synced at {ts} — {interval_str}"
                    )
                    self._gd_sync_status.setObjectName("status-ok")
                else:
                    self._gd_sync_status.setText(f"Sync failed at {ts}")
                    self._gd_sync_status.setObjectName("status-err")
                _restyle(self._gd_sync_status)
                return
        if mins == 0:
            self._gd_sync_status.setText("Auto-sync disabled — click Sync Now to sync manually")
        else:
            self._gd_sync_status.setText(
                f"Not synced yet — click Sync Now or wait for auto-sync ({interval_str})"
            )
        self._gd_sync_status.setObjectName("card-copy")
        _restyle(self._gd_sync_status)

    # ── Google Drive sync ──────────────────────────────────────────────────────

    def _start_gd_sync(self, remote: str | None = None, folder: str | None = None):
        if self._gd_sync_worker and self._gd_sync_worker.isRunning():
            return

        if remote is None or folder is None:
            for name, info in self._sync_config.items():
                if info.get("service") == "drive":
                    remote, folder = name, info.get("folder", "")
                    break

        if not remote or not folder:
            return

        self._gd_sync_status.setText(f"Syncing {remote}…")
        self._gd_sync_status.setObjectName("status-warn")
        _restyle(self._gd_sync_status)
        self._gd_sync_status.show()
        self._gd_sync_btn.show()
        self._gd_sync_btn.setEnabled(False)
        self._gd_open_btn.show()
        self._gd_log_btn.show()
        self._gd_last_sync_lines = []
        if self._gd_sync_log_visible:
            self._gd_sync_log.clear()
            self._gd_sync_log.show()

        self._gd_sync_worker = RcloneSyncWorker(remote, folder)
        self._gd_sync_worker.line.connect(self._on_gd_sync_line)
        self._gd_sync_worker.done.connect(lambda code: self._on_gd_sync_done(remote, code))
        self._gd_sync_worker.start()

    def _on_gd_sync_line(self, line: str):
        if line.strip():
            self._gd_last_sync_lines.append(line)
            if len(self._gd_last_sync_lines) > 200:
                self._gd_last_sync_lines = self._gd_last_sync_lines[-200:]
            if self._gd_sync_log_visible:
                self._gd_sync_log.append(line)

    def _on_gd_sync_done(self, remote: str, code: int):
        _finish_worker(self, attr="_gd_sync_worker")
        now = time.time()
        ok = code == 0
        if remote in self._sync_config:
            self._sync_config[remote]["last_sync"] = now
            self._sync_config[remote]["last_ok"] = ok
            _save_sync_config(self._sync_config)
        self._gd_sync_btn.setEnabled(True)
        self._update_gd_sync_label()
        if self._gd_sync_log_visible:
            from datetime import datetime as _dt
            ts = _dt.now().strftime("%H:%M:%S")
            self._gd_sync_log.append(
                f"\n[{ts}] Sync {'completed' if ok else 'FAILED'} (exit {code})"
            )

    def _toggle_gd_sync_log(self):
        self._gd_sync_log_visible = not self._gd_sync_log_visible
        if self._gd_sync_log_visible:
            self._gd_sync_log.clear()
            if self._gd_last_sync_lines:
                self._gd_sync_log.setPlainText("\n".join(self._gd_last_sync_lines))
            self._gd_sync_log.show()
            self._gd_log_btn.setText("Hide Log")
        else:
            self._gd_sync_log.hide()
            self._gd_log_btn.setText("Sync Log")

    # ── OneDrive sync ──────────────────────────────────────────────────────────

    def _update_od_sync_label(self):
        """Refresh the OneDrive sync status label from stored config."""
        mins = self._sync_config.get("_od_sync_interval_min", 5)
        if mins == 0:
            interval_str = "manual sync only"
        elif mins < 60:
            interval_str = f"every {mins} min"
        else:
            interval_str = "every hour"

        for name, info in self._sync_config.items():
            if info.get("service") != "onedrive":
                continue
            last = info.get("last_sync")
            ok = info.get("last_ok", True)
            if last:
                ts = datetime.fromtimestamp(last).strftime("%H:%M")
                if ok:
                    self._od_sync_status.setText(
                        f"Last synced at {ts} — {interval_str}"
                    )
                    self._od_sync_status.setObjectName("status-ok")
                else:
                    self._od_sync_status.setText(f"Sync failed at {ts}")
                    self._od_sync_status.setObjectName("status-err")
                _restyle(self._od_sync_status)
                return
        if mins == 0:
            self._od_sync_status.setText("Auto-sync disabled — click Sync Now to sync manually")
        else:
            self._od_sync_status.setText(
                f"Not synced yet — click Sync Now or wait for auto-sync ({interval_str})"
            )
        self._od_sync_status.setObjectName("card-copy")
        _restyle(self._od_sync_status)

    def _start_od_sync(self, remote: str | None = None, folder: str | None = None):
        if self._od_sync_worker and self._od_sync_worker.isRunning():
            return
        if remote is None or folder is None:
            for name, info in self._sync_config.items():
                if info.get("service") == "onedrive":
                    remote, folder = name, info.get("folder", "")
                    break
        if not remote or not folder:
            return
        self._od_sync_status.setText(f"Syncing {remote}…")
        self._od_sync_status.setObjectName("status-warn")
        _restyle(self._od_sync_status)
        self._od_sync_status.show()
        self._od_sync_btn.show()
        self._od_sync_btn.setEnabled(False)
        self._od_open_btn.show()
        self._od_log_btn.show()
        self._od_last_sync_lines = []
        if self._od_sync_log_visible:
            self._od_sync_log.clear()
            self._od_sync_log.show()
        self._od_sync_worker = RcloneSyncWorker(remote, folder)
        self._od_sync_worker.line.connect(self._on_od_sync_line)
        self._od_sync_worker.done.connect(lambda code: self._on_od_sync_done(remote, code))
        self._od_sync_worker.start()

    def _on_od_sync_line(self, line: str):
        if line.strip():
            self._od_last_sync_lines.append(line)
            if len(self._od_last_sync_lines) > 200:
                self._od_last_sync_lines = self._od_last_sync_lines[-200:]
            if self._od_sync_log_visible:
                self._od_sync_log.append(line)

    def _on_od_sync_done(self, remote: str, code: int):
        _finish_worker(self, attr="_od_sync_worker")
        now = time.time()
        ok = code == 0
        if remote in self._sync_config:
            self._sync_config[remote]["last_sync"] = now
            self._sync_config[remote]["last_ok"] = ok
            _save_sync_config(self._sync_config)
        self._od_sync_btn.setEnabled(True)
        self._update_od_sync_label()
        if self._od_sync_log_visible:
            from datetime import datetime as _dt
            ts = _dt.now().strftime("%H:%M:%S")
            self._od_sync_log.append(
                f"\n[{ts}] Sync {'completed' if ok else 'FAILED'} (exit {code})"
            )

    def _toggle_od_sync_log(self):
        self._od_sync_log_visible = not self._od_sync_log_visible
        if self._od_sync_log_visible:
            self._od_sync_log.clear()
            if self._od_last_sync_lines:
                self._od_sync_log.setPlainText("\n".join(self._od_last_sync_lines))
            self._od_sync_log.show()
            self._od_log_btn.setText("Hide Log")
        else:
            self._od_sync_log.hide()
            self._od_log_btn.setText("Sync Log")

    # ── Open local folders ─────────────────────────────────────────────────────

    def _open_folder_in_dolphin(self, folder: str):
        os.makedirs(folder, exist_ok=True)
        try:
            subprocess.Popen(["dolphin", folder])
        except Exception:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _open_gd_folder(self):
        for info in self._sync_config.values():
            if info.get("service") == "drive":
                folder = info.get("folder", os.path.expanduser("~/GoogleDrive"))
                self._open_folder_in_dolphin(folder)
                return

    def _open_od_folder(self):
        for info in self._sync_config.values():
            if info.get("service") == "onedrive":
                folder = info.get("folder", os.path.expanduser("~/OneDrive"))
                self._open_folder_in_dolphin(folder)
                return

    def _open_db_folder(self):
        folder = os.path.expanduser("~/Dropbox")
        self._open_folder_in_dolphin(folder)

    # ── Sync interval ──────────────────────────────────────────────────────────

    def _on_interval_changed(self, idx: int):
        mins = self._gd_interval_combo.itemData(idx)
        self._sync_config["_sync_interval_min"] = mins
        _save_sync_config(self._sync_config)
        if mins == 0:
            self._gd_sync_timer.stop()
        else:
            self._gd_sync_timer.setInterval(mins * 60 * 1000)
            if not self._gd_sync_timer.isActive():
                self._gd_sync_timer.start()
        self._update_gd_sync_label()

    def _on_od_interval_changed(self, idx: int):
        mins = self._od_interval_combo.itemData(idx)
        self._sync_config["_od_sync_interval_min"] = mins
        _save_sync_config(self._sync_config)
        if mins == 0:
            self._od_sync_timer.stop()
        else:
            self._od_sync_timer.setInterval(mins * 60 * 1000)
            if not self._od_sync_timer.isActive():
                self._od_sync_timer.start()
        self._update_od_sync_label()

    # ── rclone install ─────────────────────────────────────────────────────────

    def _install_rclone(self):
        self._gd_install_btn.setEnabled(False)
        self._log.clear()
        self._log.append("→ Running /usr/bin/kyth-rclone-update (pinned + verified)…\n")
        self._log.show()
        self._progress.show()
        self._op_status.setText("Installing rclone…")
        self._op_status.setObjectName("subheading")
        self._op_status.show()
        _restyle(self._op_status)
        self._worker = Worker(["sudo", "-A", "/usr/bin/kyth-rclone-update"])
        self._worker.line.connect(self._on_line)
        self._worker.done.connect(self._on_rclone_install_done)
        self._worker.start()

    def _on_rclone_install_done(self, code: int):
        self._progress.hide()
        _finish_worker(self)
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
        _restyle(self._op_status)
        self._refresh_status()

    # ── Dropbox ────────────────────────────────────────────────────────────────

    def _install_dropbox(self):
        self._db_install_btn.setEnabled(False)
        self._log.clear()
        self._log.append("→ flatpak install -y --user flathub com.dropbox.Client\n")
        self._log.show()
        self._progress.show()
        self._op_status.setText("Installing Dropbox…")
        self._op_status.setObjectName("subheading")
        self._op_status.show()
        _restyle(self._op_status)
        self._worker = Worker(["flatpak", "install", "-y", "--user", "flathub", "com.dropbox.Client"])
        self._worker.line.connect(self._on_line)
        self._worker.done.connect(self._on_dropbox_install_done)
        self._worker.start()

    def _on_dropbox_install_done(self, code: int):
        self._progress.hide()
        _finish_worker(self)
        if code == 0:
            self._op_status.setText("Dropbox installed. Launch it to sign in.")
            self._op_status.setObjectName("status-ok")
            self._log.append("\nDone.")
        else:
            self._op_status.setText(f"Installation failed (exit code {code}).")
            self._op_status.setObjectName("status-err")
        _restyle(self._op_status)
        self._refresh_status()

    def _launch_dropbox(self):
        if shutil.which("dropbox"):
            subprocess.Popen(["dropbox"])
        else:
            subprocess.Popen(["flatpak", "run", "com.dropbox.Client"])

    def _on_line(self, text: str):
        self._log.append(text)
        self._log.ensureCursorVisible()
