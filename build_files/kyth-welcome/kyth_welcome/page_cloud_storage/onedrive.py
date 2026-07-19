import os
import time
from datetime import datetime

from ..core_base import _restyle
from ..services.cloud_sync import RcloneSyncWorker
from ..services.network import _save_sync_config
from ..services.software import _finish_worker
from ..qt import QComboBox, QHBoxLayout, QLabel, QPushButton, QTextEdit, QTimer
from ..widgets import _make_card


class _OneDriveMixin:
    # ── OneDrive card ─────────────────────────────────────────────────────

    def _build_od_card(self):
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
        # _start_od_sync's (remote, folder) are optional, not required — a
        # direct connect would bind the button's `checked` bool to `remote`.
        self._od_sync_btn.clicked.connect(lambda: self._start_od_sync())  # pylint: disable=unnecessary-lambda
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
        self._od_sync_log.document().setMaximumBlockCount(5000)
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
        self._od_sync_timer.timeout.connect(self._start_od_sync)
        if _od_startup_mins > 0:
            self._od_sync_timer.setInterval(_od_startup_mins * 60 * 1000)
            self._od_sync_timer.start()

    # ── OneDrive sync ─────────────────────────────────────────────────────

    def _update_od_sync_label(self):
        """Refresh the OneDrive sync status label from stored config."""
        mins = self._sync_config.get("_od_sync_interval_min", 5)
        if mins == 0:
            interval_str = "manual sync only"
        elif mins < 60:
            interval_str = f"every {mins} min"
        else:
            interval_str = "every hour"

        for info in self._sync_config.values():
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
            ts = datetime.now().strftime("%H:%M:%S")
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

    def _open_od_folder(self):
        for info in self._sync_config.values():
            if info.get("service") == "onedrive":
                folder = info.get("folder", os.path.expanduser("~/OneDrive"))
                self._open_folder_in_dolphin(folder)
                return

    # ── Sync interval ─────────────────────────────────────────────────────

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
