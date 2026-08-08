"""Shared rclone sync-card plumbing for cloud storage providers.

Google Drive and OneDrive both drive rclone through an identical card:
title/description, an install-or-configure button row, a sync status +
Sync Now/Open Folder/Sync Log row, an auto-sync interval combo, and a
collapsible log. `_GoogleDriveMixin` and `_OneDriveMixin` used to each carry
a full copy of this ~230-line implementation with only prefixes and copy
text differing; this module holds the one real implementation as a small
composed helper.

`_RcloneSyncCard` is plain composition, not a shared mixin base, on purpose:
Google Drive and OneDrive config (prefix, service, copy) would otherwise
have to live as class attributes on classes that both feed into
`CloudStoragePage`'s MRO, and a diamond like that resolves `self.<attr>`
to whichever mixin comes first — silently pointing OneDrive's methods at
Google Drive's attributes. A card instance per provider avoids that.

Attribute names it sets on the owning page are still derived from `prefix`
(e.g. `_gd_status`, `_od_status`) so `CloudStoragePage`, which reaches into
those attributes directly, needs no changes.
"""
import os
import time
from datetime import datetime

from ..core_base import restyle
from ..services.cloud_sync import RcloneSyncWorker
from ..services.network import _save_sync_config
from ..services.runtime import finish_worker
from ..qt import QComboBox, QHBoxLayout, QLabel, QPushButton, QTextEdit, QTimer
from ..widgets import _make_card

_INTERVAL_CHOICES = (
    ("Every 5 minutes",  5),
    ("Every 10 minutes", 10),
    ("Every 15 minutes", 15),
    ("Every 30 minutes", 30),
    ("Every hour",       60),
    ("Manual only",      0),
)


class _RcloneSyncCard:
    """One rclone-backed provider's card, built onto `page`.

    `page` must provide `_add`, `_sync_config`, `_install_rclone`,
    `_open_wizard(key)`, and `_open_folder_in_dolphin(folder)`.
    """

    def __init__(
        self, page, *, prefix: str, service: str, title: str, desc: str,
        wizard_key: str, interval_key: str, default_folder: str,
    ):
        self._page = page
        self._prefix = prefix
        self._service = service
        self._title = title
        self._desc = desc
        self._wizard_key = wizard_key
        # Interval key is kept per-provider (not derived from prefix) for
        # backward compatibility with sync-config files written before this
        # refactor — Google Drive's predates OneDrive support and has no
        # "gd" prefix of its own.
        self._interval_key = interval_key
        self._default_folder = default_folder

    def _attr(self, name: str) -> str:
        return f"_{self._prefix}_{name}"

    def _set(self, name, value):
        setattr(self._page, self._attr(name), value)
        return value

    def _get(self, name):
        return getattr(self._page, self._attr(name))

    # ── Card construction ───────────────────────────────────────────────

    def build(self):
        page = self._page
        card, layout = _make_card()
        title = QLabel(self._title)
        title.setObjectName("card-title")
        layout.addWidget(title)
        desc = QLabel(self._desc)
        desc.setObjectName("card-copy")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        status = self._set("status", QLabel())
        status.setWordWrap(True)
        layout.addWidget(status)
        btns = QHBoxLayout()
        btns.setSpacing(10)
        install_btn = self._set("install_btn", QPushButton("Install rclone first"))
        install_btn.setObjectName("primary")
        install_btn.hide()
        install_btn.clicked.connect(page._install_rclone)
        btns.addWidget(install_btn)
        wizard_btn = self._set("wizard_btn", QPushButton("Setup Wizard…"))
        wizard_btn.setObjectName("primary")
        wizard_btn.clicked.connect(lambda: page._open_wizard(self._wizard_key))
        btns.addWidget(wizard_btn)
        btns.addStretch()
        layout.addLayout(btns)

        # Sync status row
        sync_status = self._set("sync_status", QLabel())
        sync_status.setWordWrap(True)
        sync_status.setObjectName("card-copy")
        sync_status.hide()
        layout.addWidget(sync_status)
        sync_btns = QHBoxLayout()
        sync_btns.setSpacing(10)
        sync_btn = self._set("sync_btn", QPushButton("Sync Now"))
        # start_sync's (remote, folder) are optional, not required — a direct
        # connect would bind the button's `checked` bool to `remote`.
        sync_btn.clicked.connect(lambda: self.start_sync())  # pylint: disable=unnecessary-lambda
        sync_btn.hide()
        sync_btns.addWidget(sync_btn)
        open_btn = self._set("open_btn", QPushButton("Open Local Folder"))
        open_btn.clicked.connect(self.open_folder)
        open_btn.hide()
        sync_btns.addWidget(open_btn)
        log_btn = self._set("log_btn", QPushButton("Sync Log"))
        log_btn.hide()
        log_btn.clicked.connect(self.toggle_sync_log)
        sync_btns.addWidget(log_btn)
        sync_btns.addStretch()
        layout.addLayout(sync_btns)

        # Sync interval row
        interval_row = QHBoxLayout()
        interval_row.setSpacing(8)
        interval_lbl = self._set("interval_lbl", QLabel("Auto-sync interval:"))
        interval_lbl.setObjectName("card-copy")
        interval_lbl.hide()
        interval_row.addWidget(interval_lbl)
        interval_combo = self._set("interval_combo", QComboBox())
        for label, mins in _INTERVAL_CHOICES:
            interval_combo.addItem(label, mins)
        saved_mins = page._sync_config.get(self._interval_key, 5)
        for i in range(interval_combo.count()):
            if interval_combo.itemData(i) == saved_mins:
                interval_combo.setCurrentIndex(i)
                break
        interval_combo.currentIndexChanged.connect(self.on_interval_changed)
        interval_combo.hide()
        interval_row.addWidget(interval_combo)
        interval_row.addStretch()
        layout.addLayout(interval_row)

        sync_log = self._set("sync_log", QTextEdit())
        sync_log.document().setMaximumBlockCount(5000)
        sync_log.setReadOnly(True)
        sync_log.setMaximumHeight(100)
        sync_log.setObjectName("card-copy")
        sync_log.setPlaceholderText("Sync output will appear here…")
        sync_log.hide()
        layout.addWidget(sync_log)
        self._set("sync_log_visible", False)
        self._set("last_sync_lines", [])

        page._add(card)

        # Periodic sync timer — interval loaded from config (default 5 min)
        startup_mins = page._sync_config.get(self._interval_key, 5)
        timer = self._set("sync_timer", QTimer(page))
        timer.timeout.connect(self.start_sync)
        if startup_mins > 0:
            timer.setInterval(startup_mins * 60 * 1000)
            timer.start()

    # ── Sync ─────────────────────────────────────────────────────────────

    def update_label(self):
        """Refresh the provider's sync status label from stored config."""
        page = self._page
        mins = page._sync_config.get(self._interval_key, 5)
        if mins == 0:
            interval_str = "manual sync only"
        elif mins < 60:
            interval_str = f"every {mins} min"
        else:
            interval_str = "every hour"

        sync_status = self._get("sync_status")
        for info in page._sync_config.values():
            if info.get("service") != self._service:
                continue
            last = info.get("last_sync")
            ok = info.get("last_ok", True)
            if last:
                ts = datetime.fromtimestamp(last).strftime("%H:%M")
                if ok:
                    sync_status.setText(f"Last synced at {ts} — {interval_str}")
                    sync_status.setObjectName("status-ok")
                else:
                    sync_status.setText(f"Sync failed at {ts}")
                    sync_status.setObjectName("status-err")
                restyle(sync_status)
                return
        if mins == 0:
            sync_status.setText("Auto-sync disabled — click Sync Now to sync manually")
        else:
            sync_status.setText(
                f"Not synced yet — click Sync Now or wait for auto-sync ({interval_str})"
            )
        sync_status.setObjectName("card-copy")
        restyle(sync_status)

    def start_sync(self, remote: str | None = None, folder: str | None = None):
        page = self._page
        sync_worker = self._get("sync_worker")
        if sync_worker and sync_worker.isRunning():
            return

        if remote is None or folder is None:
            for name, info in page._sync_config.items():
                if info.get("service") == self._service:
                    remote, folder = name, info.get("folder", "")
                    break

        if not remote or not folder:
            return

        sync_status = self._get("sync_status")
        sync_status.setText(f"Syncing {remote}…")
        sync_status.setObjectName("status-warn")
        restyle(sync_status)
        sync_status.show()
        sync_btn = self._get("sync_btn")
        sync_btn.show()
        sync_btn.setEnabled(False)
        self._get("open_btn").show()
        self._get("log_btn").show()
        self._set("last_sync_lines", [])
        if self._get("sync_log_visible"):
            sync_log = self._get("sync_log")
            sync_log.clear()
            sync_log.show()

        worker = self._set("sync_worker", RcloneSyncWorker(remote, folder))
        worker.line.connect(self._on_sync_line)
        worker.done.connect(lambda code: self._on_sync_done(remote, code))
        worker.start()

    def _on_sync_line(self, line: str):
        if line.strip():
            lines = self._get("last_sync_lines")
            lines.append(line)
            if len(lines) > 200:
                lines = lines[-200:]
                self._set("last_sync_lines", lines)
            if self._get("sync_log_visible"):
                self._get("sync_log").append(line)

    def _on_sync_done(self, remote: str, code: int):
        page = self._page
        finish_worker(page, attr=self._attr("sync_worker"))
        now = time.time()
        ok = code == 0
        if remote in page._sync_config:
            page._sync_config[remote]["last_sync"] = now
            page._sync_config[remote]["last_ok"] = ok
            _save_sync_config(page._sync_config)
        self._get("sync_btn").setEnabled(True)
        self.update_label()
        if self._get("sync_log_visible"):
            ts = datetime.now().strftime("%H:%M:%S")
            self._get("sync_log").append(
                f"\n[{ts}] Sync {'completed' if ok else 'FAILED'} (exit {code})"
            )

    def toggle_sync_log(self):
        visible = not self._get("sync_log_visible")
        self._set("sync_log_visible", visible)
        sync_log = self._get("sync_log")
        log_btn = self._get("log_btn")
        if visible:
            sync_log.clear()
            last_lines = self._get("last_sync_lines")
            if last_lines:
                sync_log.setPlainText("\n".join(last_lines))
            sync_log.show()
            log_btn.setText("Hide Log")
        else:
            sync_log.hide()
            log_btn.setText("Sync Log")

    def open_folder(self):
        page = self._page
        for info in page._sync_config.values():
            if info.get("service") == self._service:
                folder = info.get("folder", os.path.expanduser(self._default_folder))
                page._open_folder_in_dolphin(folder)
                return

    # ── Sync interval ────────────────────────────────────────────────────

    def on_interval_changed(self, idx: int):
        page = self._page
        mins = self._get("interval_combo").itemData(idx)
        page._sync_config[self._interval_key] = mins
        _save_sync_config(page._sync_config)
        timer = self._get("sync_timer")
        if mins == 0:
            timer.stop()
        else:
            timer.setInterval(mins * 60 * 1000)
            if not timer.isActive():
                timer.start()
        self.update_label()
