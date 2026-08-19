import os

# __KYTH_GENERATED_IMPORTS__
from ..qt import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QTextEdit, QVBoxLayout,
)
from ..widgets import _make_card, _set_log_panel


class _LibraryMixin:
    def _build_steam_library_migration_card(self):
        self._divider()
        migrate_head = QLabel("Steam Library \u2014 Migrate from another system")
        migrate_head.setObjectName("section-heading")
        self._add(migrate_head)
        migrate_sub = QLabel(
            "Dual-booting? Use this tool to copy your Steam library from another system's "
            "NTFS partition directly into Steam on KythOS. The drive is mounted "
            "read-only \u2014 your original install is never modified."
        )
        migrate_sub.setObjectName("card-copy")
        migrate_sub.setWordWrap(True)
        self._add(migrate_sub)

        hibernate_warn = QLabel(
            "\u26a0  Before scanning: boot Windows and do a full Shut Down (not Restart). "
            "Windows Fast Startup leaves NTFS volumes in a hibernated state \u2014 Linux "
            "can read them safely read-only, but Windows may report errors on resume "
            "if any other tool writes to the partition. This tool never writes to it."
        )
        hibernate_warn.setObjectName("text-warn")
        hibernate_warn.setWordWrap(True)
        self._add(hibernate_warn)

        migrate_card, migrate_layout = _make_card()

        drive_row = QHBoxLayout()
        drive_row.setSpacing(8)
        drive_lbl = QLabel("PC drive:")
        drive_lbl.setObjectName("card-copy")
        drive_row.addWidget(drive_lbl)
        self._drive_combo = QComboBox()
        self._drive_combo.setMinimumWidth(280)
        drive_row.addWidget(self._drive_combo)
        migrate_refresh_btn = QPushButton("Refresh")
        migrate_refresh_btn.clicked.connect(self._refresh_ntfs_drives)
        drive_row.addWidget(migrate_refresh_btn)
        migrate_scan_btn = QPushButton("Scan for Steam")
        migrate_scan_btn.setObjectName("primary")
        migrate_scan_btn.clicked.connect(self._scan_steam_on_drive)
        drive_row.addWidget(migrate_scan_btn)
        drive_row.addStretch()
        migrate_layout.addLayout(drive_row)

        self._migrate_found_lbl = QLabel("Select a drive above and click Scan for Steam.")
        self._migrate_found_lbl.setObjectName("card-copy")
        self._migrate_found_lbl.setWordWrap(True)
        migrate_layout.addWidget(self._migrate_found_lbl)

        self._lib_combo = QComboBox()
        self._lib_combo.setMinimumWidth(400)
        self._lib_combo.hide()
        migrate_layout.addWidget(self._lib_combo)

        check_row = QHBoxLayout()
        check_row.setSpacing(8)
        self._winlib_check_btn = QPushButton("Check My Games")
        self._winlib_check_btn.hide()
        self._winlib_check_btn.clicked.connect(self._check_windows_library_compat)
        check_row.addWidget(self._winlib_check_btn)
        check_row.addStretch()
        migrate_layout.addLayout(check_row)
        self._winlib_summary_lbl = QLabel()
        self._winlib_summary_lbl.setObjectName("card-copy")
        self._winlib_summary_lbl.setWordWrap(True)
        self._winlib_summary_lbl.hide()
        migrate_layout.addWidget(self._winlib_summary_lbl)
        self._winlib_rows = QVBoxLayout()
        self._winlib_rows.setSpacing(6)
        migrate_layout.addLayout(self._winlib_rows)
        self._winlib_games: list[dict] = []
        self._winlib_protondb_worker = None

        dst_row = QHBoxLayout()
        dst_row.setSpacing(8)
        dst_lbl = QLabel("Copy to:")
        dst_lbl.setObjectName("card-copy")
        dst_row.addWidget(dst_lbl)
        self._migrate_dst_edit = QLineEdit(
            os.path.expanduser("~/.local/share/Steam/steamapps")
        )
        dst_row.addWidget(self._migrate_dst_edit, 1)
        browse_btn = QPushButton("Browse\u2026")
        browse_btn.clicked.connect(self._browse_migrate_dst)
        dst_row.addWidget(browse_btn)
        migrate_layout.addLayout(dst_row)

        copy_btn_row = QHBoxLayout()
        copy_btn_row.setSpacing(8)
        self._copy_btn = QPushButton("Copy Library")
        self._copy_btn.setObjectName("primary")
        self._copy_btn.setEnabled(False)
        self._copy_btn.clicked.connect(self._start_steam_copy)
        copy_btn_row.addWidget(self._copy_btn)
        self._copy_cancel_btn = QPushButton("Cancel")
        self._copy_cancel_btn.hide()
        self._copy_cancel_btn.clicked.connect(self._cancel_steam_copy)
        copy_btn_row.addWidget(self._copy_cancel_btn)
        copy_btn_row.addStretch()
        migrate_layout.addLayout(copy_btn_row)

        self._migrate_status = QLabel()
        self._migrate_status.setObjectName("subheading")
        self._migrate_status.hide()
        migrate_layout.addWidget(self._migrate_status)

        self._migrate_progress = QProgressBar()
        self._migrate_progress.setRange(0, 0)
        self._migrate_progress.hide()
        migrate_layout.addWidget(self._migrate_progress)

        self._migrate_log_toggle = QPushButton("Show details")
        self._migrate_log_toggle.setCheckable(True)
        self._migrate_log_toggle.hide()
        self._migrate_log_toggle.clicked.connect(
            lambda checked: _set_log_panel(self._migrate_log_toggle, self._migrate_log, checked)
        )
        migrate_layout.addWidget(self._migrate_log_toggle)

        self._migrate_log = QTextEdit()
        self._migrate_log.document().setMaximumBlockCount(5000)
        self._migrate_log.setReadOnly(True)
        self._migrate_log.setMaximumHeight(140)
        self._migrate_log.hide()
        migrate_layout.addWidget(self._migrate_log)

        self._add(migrate_card)
        self._migrate_worker = None
        self._scanned_mount = None
        self._ntfs_drives_worker = None
        self._steam_scan_worker = None
