"""Windows Migration page — wallpaper/fonts/saves/sticky-notes/RDP cards and
the single PC-drive scan that populates all of them, _PcDriveExtrasMixin.
"""

from __future__ import annotations

import os
import shutil
from ..services.process import human_bytes, run_command
from ..services.runtime import (
    DataWorker, guard_disposed, release_worker_when_finished,
)
from ..services.launch import popen
from ..services.windows_migration import (
    _copy_game_saves,
    _copy_windows_fonts,
    _export_sticky_notes,
    _image_extension,
    _import_rdp_bookmarks,
    _scan_windows_extras,
    _windows_folder_dest,
)
from ..qt import (
    QComboBox, QDesktopServices, QHBoxLayout, QLabel, QPushButton, QUrl, QVBoxLayout,
)
from ..widgets import (
    _make_card,
)


class _PcDriveExtrasMixin:
    def _build_wallpaper_card(self):
        # ── Windows wallpaper ─────────────────────────────────────────────────
        wp_card, wp_layout = _make_card()
        wp_title = QLabel("Keep your Windows wallpaper")
        wp_title.setObjectName("card-title")
        wp_layout.addWidget(wp_title)
        wp_body = QLabel(
            "Your desktop background comes straight off the PC drive and is saved "
            "into Pictures — one click and the desktop feels like home."
        )
        wp_body.setObjectName("card-copy")
        wp_body.setWordWrap(True)
        wp_layout.addWidget(wp_body)
        self._wp_status = QLabel("Scan drives above — wallpapers are found automatically.")
        self._wp_status.setObjectName("card-copy")
        self._wp_status.setWordWrap(True)
        wp_layout.addWidget(self._wp_status)
        self._wp_combo = QComboBox()
        self._wp_combo.hide()
        wp_layout.addWidget(self._wp_combo)
        wp_btns = QHBoxLayout()
        wp_btns.setSpacing(8)
        self._wp_apply_btn = QPushButton("Use This Wallpaper")
        self._wp_apply_btn.setObjectName("primary")
        self._wp_apply_btn.hide()
        self._wp_apply_btn.clicked.connect(self._apply_windows_wallpaper)
        wp_btns.addWidget(self._wp_apply_btn)
        wp_btns.addStretch()
        wp_layout.addLayout(wp_btns)
        self._add(wp_card)

    def _build_fonts_card(self):
        # ── system fonts ─────────────────────────────────────────────────────
        fonts_card, fonts_layout = _make_card()
        fonts_title = QLabel("Bring your system fonts")
        fonts_title.setObjectName("card-title")
        fonts_layout.addWidget(fonts_title)
        fonts_body = QLabel(
            "Modern documents use Segoe UI, Calibri, and Cambria — fonts the downloadable "
            "core-fonts set doesn't include. Copying your own fonts from the original install "
            "on this PC makes documents render identically here."
        )
        fonts_body.setObjectName("card-copy")
        fonts_body.setWordWrap(True)
        fonts_layout.addWidget(fonts_body)
        self._fonts_status = QLabel("Scan drives above — system font folders are found automatically.")
        self._fonts_status.setObjectName("card-copy")
        self._fonts_status.setWordWrap(True)
        fonts_layout.addWidget(self._fonts_status)
        fonts_btns = QHBoxLayout()
        fonts_btns.setSpacing(8)
        self._fonts_btn = QPushButton("Copy Windows Fonts")
        self._fonts_btn.setObjectName("primary")
        self._fonts_btn.hide()
        self._fonts_btn.clicked.connect(self._copy_fonts_clicked)
        fonts_btns.addWidget(self._fonts_btn)
        fonts_btns.addStretch()
        fonts_layout.addLayout(fonts_btns)
        self._add(fonts_card)

    def _build_saves_card(self):
        # ── Game saves rescue ─────────────────────────────────────────────────
        saves_card, saves_layout = _make_card()
        saves_title = QLabel("Rescue game saves from the PC drive")
        saves_title.setObjectName("card-title")
        saves_layout.addWidget(saves_title)
        saves_body = QLabel(
            "Saves hide in My Games, Saved Games, AppData, and Ubisoft's launcher folder. "
            "This finds them and copies everything into Documents → Rescued Game Saves, "
            "so nothing is lost when the PC drive goes away. Ludusavi can help place "
            "them into each game's new home."
        )
        saves_body.setObjectName("card-copy")
        saves_body.setWordWrap(True)
        saves_layout.addWidget(saves_body)
        self._saves_status = QLabel("Scan drives above — save locations are found automatically.")
        self._saves_status.setObjectName("card-copy")
        self._saves_status.setWordWrap(True)
        saves_layout.addWidget(self._saves_status)
        self._saves_rows = QVBoxLayout()
        self._saves_rows.setSpacing(4)
        saves_layout.addLayout(self._saves_rows)
        saves_btns = QHBoxLayout()
        saves_btns.setSpacing(8)
        self._saves_btn = QPushButton("Copy All Found Saves")
        self._saves_btn.setObjectName("primary")
        self._saves_btn.hide()
        self._saves_btn.clicked.connect(self._copy_saves_clicked)
        saves_btns.addWidget(self._saves_btn)
        self._saves_show_btn = QPushButton("Show Folder")
        self._saves_show_btn.hide()
        self._saves_show_btn.clicked.connect(lambda _=False: QDesktopServices.openUrl(
            QUrl.fromLocalFile(os.path.join(_windows_folder_dest("Documents"), "Rescued Game Saves"))))
        saves_btns.addWidget(self._saves_show_btn)
        saves_btns.addStretch()
        saves_layout.addLayout(saves_btns)
        self._add(saves_card)

    def _build_sticky_card(self):
        # ── Sticky Notes ──────────────────────────────────────────────────────
        sticky_card, sticky_layout = _make_card()
        sticky_title = QLabel("Bring your Sticky Notes")
        sticky_title.setObjectName("card-title")
        sticky_layout.addWidget(sticky_title)
        sticky_body = QLabel(
            "Notes from the Windows Sticky Notes app are read from the drive and saved as "
            "text files in Documents → Sticky Notes. For the same look here, right-click "
            "the desktop → Add Widgets → Sticky Note, then paste a note in."
        )
        sticky_body.setObjectName("card-copy")
        sticky_body.setWordWrap(True)
        sticky_layout.addWidget(sticky_body)
        self._sticky_status = QLabel("Scan drives above — Sticky Notes are found automatically.")
        self._sticky_status.setObjectName("card-copy")
        self._sticky_status.setWordWrap(True)
        sticky_layout.addWidget(self._sticky_status)
        sticky_btns = QHBoxLayout()
        sticky_btns.setSpacing(8)
        self._sticky_btn = QPushButton("Export Notes")
        self._sticky_btn.setObjectName("primary")
        self._sticky_btn.hide()
        self._sticky_btn.clicked.connect(self._export_sticky_clicked)
        sticky_btns.addWidget(self._sticky_btn)
        self._sticky_show_btn = QPushButton("Show Folder")
        self._sticky_show_btn.hide()
        self._sticky_show_btn.clicked.connect(lambda _=False: QDesktopServices.openUrl(
            QUrl.fromLocalFile(os.path.join(_windows_folder_dest("Documents"), "Sticky Notes"))))
        sticky_btns.addWidget(self._sticky_show_btn)
        sticky_btns.addStretch()
        sticky_layout.addLayout(sticky_btns)
        self._add(sticky_card)

    def _build_rdp_card(self):
        # ── Remote Desktop connections ────────────────────────────────────────
        rdp_card, rdp_layout = _make_card()
        rdp_title = QLabel("Remote Desktop connections")
        rdp_title.setObjectName("card-title")
        rdp_layout.addWidget(rdp_title)
        rdp_body = QLabel(
            "Saved .rdp files from your Windows Desktop, Documents, and Downloads become "
            "bookmarks in KRDC — the built-in Remote Desktop client (the mstsc equivalent)."
        )
        rdp_body.setObjectName("card-copy")
        rdp_body.setWordWrap(True)
        rdp_layout.addWidget(rdp_body)
        self._rdp_status = QLabel("Scan drives above — saved connections are found automatically.")
        self._rdp_status.setObjectName("card-copy")
        self._rdp_status.setWordWrap(True)
        rdp_layout.addWidget(self._rdp_status)
        rdp_btns = QHBoxLayout()
        rdp_btns.setSpacing(8)
        self._rdp_btn = QPushButton("Add to KRDC")
        self._rdp_btn.setObjectName("primary")
        self._rdp_btn.hide()
        self._rdp_btn.clicked.connect(self._import_rdp_clicked)
        rdp_btns.addWidget(self._rdp_btn)
        self._rdp_open_btn = QPushButton("Open KRDC")
        self._rdp_open_btn.hide()
        self._rdp_open_btn.clicked.connect(
            lambda _=False: popen(["krdc"]))
        rdp_btns.addWidget(self._rdp_open_btn)
        rdp_btns.addStretch()
        rdp_layout.addLayout(rdp_btns)
        self._add(rdp_card)

    # ── PC drive scan — feeds every card built above ────────────────────────

    def _start_extras_scan(self, partitions: list):
        if self._extras_worker is not None and self._extras_worker.isRunning():
            return
        self._extras = {}
        usable = [
            part for part in partitions
            if part.get("mountpoint") or part.get("user_profiles")
        ]
        if not usable:
            no_drive = "No readable PC drive — scan or unlock one above first."
            for lbl in (self._wp_status, self._fonts_status, self._saves_status,
                        self._sticky_status, self._rdp_status):
                lbl.setText(no_drive)
            for widget in (self._wp_combo, self._wp_apply_btn, self._fonts_btn,
                           self._saves_btn, self._sticky_btn, self._rdp_btn):
                widget.hide()
            self._clear_layout(self._saves_rows)
            return
        for lbl in (self._wp_status, self._fonts_status, self._saves_status,
                    self._sticky_status, self._rdp_status):
            lbl.setText("Looking on the PC drive…")
        worker = DataWorker("win-extras", lambda: _scan_windows_extras(usable))
        worker.result.connect(guard_disposed(self._on_extras))
        worker.failed.connect(
            guard_disposed(lambda _key, message: self._wp_status.setText(
                f"Could not read the PC drive: {message}")))
        self._extras_worker = worker
        release_worker_when_finished(self, "_extras_worker", worker)
        worker.start()

    def _on_extras(self, _key: str, extras: dict):
        self._extras = extras
        # Feed Takeout wizard with saves/wallpaper enrichment
        try:
            from ..services.windows_migration import enrich_with_extras
            if getattr(self, "_takeout_summary", None) is not None:
                self._takeout_summary = enrich_with_extras(self._takeout_summary, [extras])
                self._render_takeout()
            else:
                self._update_takeout()
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            pass

        wallpapers = extras.get("wallpapers") or []
        self._wp_combo.clear()
        if wallpapers:
            for item in wallpapers:
                self._wp_combo.addItem(f"Wallpaper of Windows user {item['user']}", item["path"])
            self._wp_combo.setVisible(len(wallpapers) > 1)
            self._wp_apply_btn.show()
            self._wp_status.setText(
                f"Found the desktop wallpaper for {len(wallpapers)} Windows "
                f"user{'s' if len(wallpapers) != 1 else ''}."
            )
        else:
            self._wp_combo.hide()
            self._wp_apply_btn.hide()
            self._wp_status.setText("No cached wallpaper found on the PC drive.")

        fonts = extras.get("fonts") or {}
        if fonts.get("count"):
            self._fonts_btn.show()
            self._fonts_status.setText(
                f"Found {fonts['count']} font files ({human_bytes(fonts['bytes'])}) "
                "in the system font folders."
            )
        else:
            self._fonts_btn.hide()
            self._fonts_status.setText("No font folders found on the PC drive.")

        saves = extras.get("saves") or []
        self._clear_layout(self._saves_rows)
        if saves:
            for item in saves[:8]:
                where = f"Windows user {item['user']}" if item["user"] else "Drive-level launcher folder"
                self._saves_rows.addWidget(self._make_migration_row("ok", item["label"], where))
            if len(saves) > 8:
                self._saves_rows.addWidget(self._make_migration_row(
                    "dim", f"+{len(saves) - 8} more", "All found locations are copied together."))
            self._saves_btn.show()
            self._saves_status.setText(
                f"Found {len(saves)} likely save location{'s' if len(saves) != 1 else ''}:"
            )
        else:
            self._saves_btn.hide()
            self._saves_status.setText("No game save folders found on the PC drive.")

        sticky = extras.get("sticky") or []
        total_notes = sum(len(src["notes"]) for src in sticky)
        if total_notes:
            self._sticky_btn.show()
            users = ", ".join(src["user"] for src in sticky)
            self._sticky_status.setText(
                f"Found {total_notes} sticky note{'s' if total_notes != 1 else ''} "
                f"from another system user{'s' if len(sticky) != 1 else ''} {users}."
            )
        else:
            self._sticky_btn.hide()
            self._sticky_status.setText("No Sticky Notes found on the PC drive.")

        rdp = extras.get("rdp") or []
        if rdp:
            self._rdp_btn.show()
            preview = ", ".join(f"{c['name']} ({c['host']})" for c in rdp[:4])
            if len(rdp) > 4:
                preview += f", +{len(rdp) - 4} more"
            self._rdp_status.setText(
                f"Found {len(rdp)} saved connection{'s' if len(rdp) != 1 else ''}: {preview}"
            )
        else:
            self._rdp_btn.hide()
            self._rdp_status.setText("No saved .rdp connection files found on the PC drive.")

    # ── Per-card actions ─────────────────────────────────────────────────

    def _apply_windows_wallpaper(self):
        src = self._wp_combo.currentData()
        if not src:
            wallpapers = self._extras.get("wallpapers") or []
            src = wallpapers[0]["path"] if wallpapers else ""
        if not src:
            return
        dest_dir = _windows_folder_dest("Pictures")
        dest = os.path.join(dest_dir, "Windows Wallpaper" + _image_extension(src))
        try:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(src, dest)
        except OSError as exc:
            self._wp_status.setText(f"Could not copy the wallpaper: {exc}")
            return
        home = os.path.expanduser("~")
        shown = dest.replace(home, "~", 1)
        if shutil.which("plasma-apply-wallpaperimage"):
            result = run_command(["plasma-apply-wallpaperimage", dest], timeout=30)
            if result is not None and result.returncode == 0:
                self._wp_status.setText(f"✓ Wallpaper applied — saved to {shown}.")
                return
        self._wp_status.setText(
            f"✓ Saved to {shown}. Right-click the desktop → Configure Desktop and "
            "Wallpaper to apply it."
        )

    def _copy_fonts_clicked(self):
        if self._fonts_copy_worker is not None and self._fonts_copy_worker.isRunning():
            return
        dirs = list((self._extras.get("fonts") or {}).get("dirs") or [])
        if not dirs:
            return
        self._fonts_btn.setEnabled(False)
        self._fonts_status.setText("Copying fonts…")
        worker = DataWorker("fonts-copy", lambda: _copy_windows_fonts(dirs))

        def _done(_key: str, result: tuple):
            copied, skipped = result
            self._fonts_btn.setEnabled(True)
            extra = f" ({skipped} already present)" if skipped else ""
            self._fonts_status.setText(
                f"✓ Installed {copied} fonts{extra}. Apps pick them up immediately; "
                "documents now render with their original fonts."
            )
        worker.result.connect(guard_disposed(_done))
        worker.failed.connect(
            guard_disposed(lambda _key, message: (
                self._fonts_btn.setEnabled(True),
                self._fonts_status.setText(f"Could not copy fonts: {message}"),
            )))
        self._fonts_copy_worker = worker
        release_worker_when_finished(self, "_fonts_copy_worker", worker)
        worker.start()

    def _copy_saves_clicked(self):
        if self._saves_copy_worker is not None and self._saves_copy_worker.isRunning():
            return
        saves = list(self._extras.get("saves") or [])
        if not saves:
            return
        self._saves_btn.setEnabled(False)
        self._saves_status.setText("Copying save folders…")
        worker = DataWorker("saves-copy", lambda: _copy_game_saves(saves))

        def _done(_key: str, result: tuple):
            ok, failed, base = result
            self._saves_btn.setEnabled(True)
            home = os.path.expanduser("~")
            text = f"✓ Copied {ok} save folder{'s' if ok != 1 else ''} to {base.replace(home, '~', 1)}."
            if failed:
                text += f" {failed} could not be read — if the other system wasn't fully shut down, boot it once and retry."
            self._saves_status.setText(text)
            self._saves_show_btn.show()
        worker.result.connect(guard_disposed(_done))
        worker.failed.connect(
            guard_disposed(lambda _key, message: (
                self._saves_btn.setEnabled(True),
                self._saves_status.setText(f"Could not copy saves: {message}"),
            )))
        self._saves_copy_worker = worker
        release_worker_when_finished(self, "_saves_copy_worker", worker)
        worker.start()

    def _export_sticky_clicked(self):
        sticky = self._extras.get("sticky") or []
        if not sticky:
            return
        try:
            count, base = _export_sticky_notes(sticky)
        except OSError as exc:
            self._sticky_status.setText(f"Could not export the notes: {exc}")
            return
        home = os.path.expanduser("~")
        self._sticky_status.setText(
            f"✓ Exported {count} note{'s' if count != 1 else ''} to {base.replace(home, '~', 1)}."
        )
        self._sticky_show_btn.show()

    def _import_rdp_clicked(self):
        rdp = self._extras.get("rdp") or []
        if not rdp:
            return
        try:
            added, dupes = _import_rdp_bookmarks(rdp)
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
            self._rdp_status.setText(f"Could not write the KRDC bookmarks: {exc}")
            return
        text = f"✓ Added {added} connection{'s' if added != 1 else ''} to KRDC bookmarks."
        if dupes:
            text += f" {dupes} already existed."
        self._rdp_status.setText(text)
        self._rdp_open_btn.show()
