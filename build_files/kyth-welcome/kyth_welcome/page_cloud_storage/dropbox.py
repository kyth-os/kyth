import os
import shutil

from ..core_base import restyle, run_worker
from ..services.banner import set_banner
from ..services.launch import flatpak_run, popen
from ..services.runtime import finish_worker
from ..qt import QHBoxLayout, QLabel, QPushButton
from ..widgets import _make_card


class _DropboxMixin:
    # ── Dropbox card ──────────────────────────────────────────────────────

    def _build_db_card(self):
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

    # ── Dropbox ───────────────────────────────────────────────────────────

    def _install_dropbox(self):
        self._db_install_btn.setEnabled(False)
        self._log.clear()
        self._log.append("→ flatpak install -y --user flathub com.dropbox.Client\n")
        self._log.show()
        self._progress.show()
        self._op_status.setText("Installing Dropbox…")
        self._op_status.setObjectName("subheading")
        self._op_status.show()
        restyle(self._op_status)
        run_worker(
            self,
            ["flatpak", "install", "-y", "--user", "flathub", "com.dropbox.Client"],
            on_line=self._on_line,
            on_done=self._on_dropbox_install_done,
        )

    def _on_dropbox_install_done(self, code: int):
        self._progress.hide()
        finish_worker(self)
        if code == 0:
            self._op_status.setText("Dropbox installed. Launch it to sign in.")
            self._op_status.setObjectName("status-ok")
            self._log.append("\nDone.")
        else:
            self._op_status.setText(f"Installation failed (exit code {code}).")
            self._op_status.setObjectName("status-err")
        restyle(self._op_status)
        self._refresh_status()

    def _launch_dropbox(self):
        proc = None
        if shutil.which("dropbox"):
            proc = popen(["dropbox"])
        if proc is None:
            proc = flatpak_run("com.dropbox.Client")
        if proc is None:
            set_banner(self._op_status, "Dropbox is not installed — install it from the App Store.", kind="err")

    def _open_db_folder(self):
        folder = os.path.expanduser("~/Dropbox")
        self._open_folder_in_dolphin(folder)
