"""Windows Migration page — drives cards + handlers, _DrivesMixin."""

from __future__ import annotations

from ..core_base import (
    _release_worker_when_finished,
    _restyle,
)
from ..services.runtime import (
    DataWorker,
)
from ..services.software import (
    _finish_worker,
)
from ..services.windows_migration import (
    WindowsLibraryWorker,
    _unlock_bitlocker_drive,
)
from ..qt import (  # noqa: E501
    QDesktopServices, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QProgressBar, QPushButton, QUrl, QVBoxLayout,
)
from ..widgets import (  # noqa: E501
    _make_card,
)


class _DrivesMixin:
    def _build_drives_card(self):
        drives, drives_layout = _make_card()
        drives_top = QHBoxLayout()
        drives_title = QLabel("PC drives")
        drives_title.setObjectName("card-title")
        drives_top.addWidget(drives_title)
        drives_top.addStretch()
        refresh_btn = QPushButton("Scan Drives")
        refresh_btn.setObjectName("primary")
        refresh_btn.clicked.connect(self._scan_windows_drives)
        drives_top.addWidget(refresh_btn)
        drives_layout.addLayout(drives_top)
        drives_desc = QLabel(
            "Looks for NTFS partitions, hibernation/dirty flags, Windows user folders, mount points, and Steam folders. "
            "If a drive is hibernated, boot the other system once and choose full Shut Down before copying from it."
        )
        drives_desc.setObjectName("card-copy")
        drives_desc.setWordWrap(True)
        drives_layout.addWidget(drives_desc)
        ntfs_warn = QLabel(
            "⚠  Browse and copy files from PC drives freely — but don't add one as a Steam "
            "library or launch games from it. Proton needs a Linux-formatted disk; games run "
            "straight off NTFS break in confusing ways. Use Copy Games to KythOS instead."
        )
        ntfs_warn.setObjectName("card-copy")
        ntfs_warn.setWordWrap(True)
        ntfs_warn.setStyleSheet("color: #d4a843;")
        drives_layout.addWidget(ntfs_warn)
        self._drive_status = QLabel("Click Scan Drives to look for system partitions.")
        self._drive_status.setObjectName("card-copy")
        self._drive_status.setWordWrap(True)
        drives_layout.addWidget(self._drive_status)
        self._drive_progress = QProgressBar()
        self._drive_progress.setRange(0, 0)
        self._drive_progress.hide()
        drives_layout.addWidget(self._drive_progress)
        self._drive_rows = QVBoxLayout()
        self._drive_rows.setSpacing(8)
        drives_layout.addLayout(self._drive_rows)
        self._add(drives)



    def _build_clock_card(self):
        # Dual-boot clock fix card
        clock_card, clock_layout = _make_card("card-accent-warn")
        clock_title = QLabel("Dual-booting? Fix the clock.")
        clock_title.setObjectName("card-title")
        clock_layout.addWidget(clock_title)
        clock_body = QLabel(
            "After booting KythOS, Windows often shows the wrong time — sometimes off by several hours. "
            "This happens because Windows and Linux disagree about whether the hardware clock stores "
            "local time or UTC. One command fixes it permanently with no reboot needed."
        )
        clock_body.setObjectName("card-copy")
        clock_body.setWordWrap(True)
        clock_layout.addWidget(clock_body)
        clock_btns = QHBoxLayout()
        clock_btns.setSpacing(8)
        clock_fix_btn = QPushButton("Fix Dual-Boot Clock")
        clock_fix_btn.setObjectName("primary")
        clock_fix_btn.setToolTip("Runs: sudo timedatectl set-local-rtc 1 --adjust-system-clock")
        clock_fix_btn.clicked.connect(lambda _=False: self._run_ujust("fix-dualboot-clock", clock_fix_btn))
        clock_btns.addWidget(clock_fix_btn)
        clock_btns.addStretch()
        clock_layout.addLayout(clock_btns)
        self._add(clock_card)



    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


    def _clear_drive_rows(self):
        self._clear_layout(self._drive_rows)


    def _scan_windows_drives(self):
        if self._worker and self._worker.isRunning():
            return
        self._clear_drive_rows()
        self._drive_progress.show()
        self._drive_status.setText("Scanning NTFS partitions…")
        self._drive_status.setObjectName("subheading")
        _restyle(self._drive_status)
        self._worker = WindowsLibraryWorker()
        self._worker.result.connect(self._on_windows_drives)
        self._worker.start()


    def _on_windows_drives(self, partitions: list):
        self._drive_progress.hide()
        _finish_worker(self)
        if not partitions:
            self._drive_status.setText("No Windows/NTFS partitions found.")
            self._drive_status.setObjectName("status-warn")
            self._migration_score_lbl.setText("Switch readiness: 2/5. Install your launchers and Ludusavi, then connect your PC drive or cloud backup when ready.")
            _restyle(self._drive_status)
            self._populate_files_card([])
            self._start_bookmark_scan([])
            self._start_extras_scan([])
            return
        self._drive_status.setText(f"Found {len(partitions)} Windows-style partition{'s' if len(partitions) != 1 else ''}.")
        self._drive_status.setObjectName("status-ok")
        _restyle(self._drive_status)
        locked = sum(1 for p in partitions if p.get("is_bitlocker"))
        clean = sum(1 for p in partitions if not p.get("is_dirty") and not p.get("is_hibernated") and not p.get("is_bitlocker"))
        steam = sum(len(p.get("steam_paths") or []) for p in partitions)
        profiles = sum(len(p.get("user_profiles") or []) for p in partitions)
        score = 2 + (1 if clean else 0) + (1 if steam else 0) + (1 if profiles else 0)
        score_text = (
            f"Switch readiness: {score}/5. Found {clean} safely readable drive(s), "
            f"{steam} Steam folder(s), and {profiles} Windows user profile(s). "
            "Back up saves with Ludusavi before copying large libraries."
        )
        if locked:
            score_text += (
                f" {locked} drive(s) are BitLocker-encrypted — unlock them below "
                "to copy files and bookmarks."
            )
        self._migration_score_lbl.setText(score_text)
        for part in partitions:
            self._drive_rows.addWidget(self._make_drive_row(part))
        self._populate_files_card(partitions)
        self._start_bookmark_scan(partitions)
        self._start_extras_scan(partitions)


    def _make_drive_row(self, part: dict) -> QFrame:
        if part.get("is_bitlocker"):
            return self._make_bitlocker_row(part)
        status = "warn" if part.get("is_dirty") or part.get("is_hibernated") else "ok"
        label = part.get("label") or part.get("device") or "PC drive"
        if part.get("windows_root"):
            label = f"Windows (C:) — {label}" if part.get("label") else "Windows (C:)"
        mount = part.get("mountpoint") or "not mounted"
        steam_count = len(part.get("steam_paths") or [])
        profile_count = len(part.get("user_profiles") or [])
        summary = (
            f"{part.get('device', '')} · {part.get('size', '')} · {mount} · "
            f"{profile_count} user profile{'s' if profile_count != 1 else ''} · "
            f"{steam_count} Steam folder{'s' if steam_count != 1 else ''}"
        )
        if part.get("is_hibernated"):
            summary += " · hibernated"
        elif part.get("is_dirty"):
            summary += " · needs Windows shutdown"
        row = self._make_migration_row(status, label, summary)
        layout = row.layout()
        if part.get("mountpoint"):
            open_btn = QPushButton("Open Drive")
            open_btn.clicked.connect(
                lambda _=False, path=part["mountpoint"]: QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            )
            layout.addWidget(open_btn)
        profiles = part.get("user_profiles") or []
        if profiles:
            profile = profiles[0]
            files_btn = QPushButton("Open Windows Files")
            files_btn.clicked.connect(
                lambda _=False, path=profile["path"]: QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            )
            files_btn.setToolTip(", ".join(profile.get("folders") or []))
            layout.addWidget(files_btn)
        steam_paths = part.get("steam_paths") or []
        if steam_paths:
            steam_btn = QPushButton("Open Steam Library")
            steam_btn.setToolTip(
                "Read-only browsing is fine. Don't add this folder as a Steam library on "
                "KythOS — copy the games to your Linux disk instead."
            )
            steam_btn.clicked.connect(
                lambda _=False, path=steam_paths[0]: QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            )
            layout.addWidget(steam_btn)
        gaming_btn = QPushButton("Copy Games to KythOS")
        gaming_btn.setToolTip("Opens Gaming → Steam Library migration: scans this drive and copies games to your Linux disk.")
        gaming_btn.clicked.connect(lambda _=False: self._navigate("Gaming"))
        layout.addWidget(gaming_btn)
        return row


    def _make_bitlocker_row(self, part: dict) -> QFrame:
        label = part.get("label") or part.get("device") or "PC drive"
        summary = (
            f"{part.get('device', '')} · {part.get('size', '')} · "
            "locked with BitLocker — unlock to copy files, bookmarks, and games"
        )
        row = self._make_migration_row("warn", f"{label} (BitLocker)", summary)
        unlock_btn = QPushButton("Unlock Drive…")
        unlock_btn.setObjectName("primary")
        unlock_btn.setToolTip(
            "Enter your BitLocker password or the 48-digit recovery key. "
            "Find the recovery key at aka.ms/myrecoverykey (sign in with the "
            "Microsoft account used on the Windows PC)."
        )
        unlock_btn.clicked.connect(
            lambda _=False, d=part.get("device", ""), b=unlock_btn: self._unlock_bitlocker(d, b)
        )
        row.layout().addWidget(unlock_btn)
        return row


    def _unlock_bitlocker(self, dev: str, btn: QPushButton):
        if not dev:
            return
        key, ok = QInputDialog.getText(
            self, "Unlock BitLocker drive",
            f"Enter the BitLocker password or 48-digit recovery key for {dev}.\n"
            "Recovery key: aka.ms/myrecoverykey (Microsoft account of the Windows PC).",
            QLineEdit.EchoMode.Password,
        )
        key = (key or "").strip()
        if not ok or not key:
            return
        btn.setEnabled(False)
        btn.setText("Unlocking…")
        self._drive_status.setText(f"Unlocking {dev}…")
        self._drive_status.setObjectName("subheading")
        _restyle(self._drive_status)
        worker = DataWorker("bitlocker", lambda: _unlock_bitlocker_drive(dev, key))
        worker.result.connect(self._on_bitlocker_unlock)
        self._bitlocker_worker = worker
        _release_worker_when_finished(self, "_bitlocker_worker", worker)
        worker.start()


    def _on_bitlocker_unlock(self, _key: str, result: tuple):
        ok, message = result
        if ok:
            # Rescan so the now-visible NTFS partition gets the full treatment
            # (user profiles, Steam folders, bookmarks, file copy).
            self._scan_windows_drives()
        else:
            self._drive_status.setText(f"BitLocker unlock failed: {message}")
            self._drive_status.setObjectName("status-warn")
            _restyle(self._drive_status)
            self._clear_drive_rows()
            self._on_windows_drives_requery()


    def _on_windows_drives_requery(self):
        """Rebuild drive rows without resetting status (after failed unlock)."""
        worker = WindowsLibraryWorker()
        worker.result.connect(lambda parts: [
            self._drive_rows.addWidget(self._make_drive_row(p)) for p in parts
        ])
        self._requery_worker = worker
        _release_worker_when_finished(self, "_requery_worker", worker)
        worker.start()
