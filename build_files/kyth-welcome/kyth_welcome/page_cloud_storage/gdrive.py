import os
import time
from datetime import datetime

from ..core_base import _restyle
from ..services.cloud_sync import RcloneSyncWorker
from ..services.network import _save_sync_config
from ..services.software import _finish_worker
from ..qt import QComboBox, QHBoxLayout, QLabel, QPushButton, QTextEdit, QTimer
from ..widgets import _make_card


class _GoogleDriveMixin:
    # ── Google Drive card ─────────────────────────────────────────────────

    def _build_gd_card(self):
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
        # _start_gd_sync's (remote, folder) are optional, not required — a
        # direct connect would bind the button's `checked` bool to `remote`.
        self._gd_sync_btn.clicked.connect(lambda: self._start_gd_sync())  # pylint: disable=unnecessary-lambda
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
        self._gd_sync_log.document().setMaximumBlockCount(5000)
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
        self._gd_sync_timer.timeout.connect(self._start_gd_sync)
        if _startup_mins > 0:
            self._gd_sync_timer.setInterval(_startup_mins * 60 * 1000)
            self._gd_sync_timer.start()

    # ── Google Drive sync ────────────────────────────────────────────────

    def _update_gd_sync_label(self):
        """Refresh the Google Drive sync status label from stored config."""
        mins = self._sync_config.get("_sync_interval_min", 5)
        if mins == 0:
            interval_str = "manual sync only"
        elif mins < 60:
            interval_str = f"every {mins} min"
        else:
            interval_str = "every hour"

        for info in self._sync_config.values():
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
            ts = datetime.now().strftime("%H:%M:%S")
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

    def _open_gd_folder(self):
        for info in self._sync_config.values():
            if info.get("service") == "drive":
                folder = info.get("folder", os.path.expanduser("~/GoogleDrive"))
                self._open_folder_in_dolphin(folder)
                return

    # ── Sync interval ─────────────────────────────────────────────────────

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
