"""Windows Migration page — bookmarks extras cards + handlers, _BookmarksExtrasMixin."""

from __future__ import annotations

import os
from ..core_base import (
    _human_bytes,
    _release_worker_when_finished,
)
from ..services.runtime import (
    DataWorker,
)
from ..services.software import (
    _install_flatpak_inline,
)
from ..services.windows_migration import (
    _scan_windows_bookmarks,
    _scan_windows_extras,
    _windows_folder_dest,
    _write_bookmarks_html,
)
from ..qt import (  # noqa: E501
    QDesktopServices, QHBoxLayout, QLabel, QPushButton, QUrl, QVBoxLayout,
)
from ..widgets import (  # noqa: E501
    _make_card,
)


class _BookmarksExtrasMixin:
    def _build_bookmarks_card(self):
        # ── Browser bookmarks ─────────────────────────────────────────────────
        bm_card, bm_layout = _make_card()
        bm_title = QLabel("Bring your browser bookmarks")
        bm_title.setObjectName("card-title")
        bm_layout.addWidget(bm_title)
        bm_body = QLabel(
            "Bookmarks are read straight off the PC drive — Chrome, Edge, Brave, Vivaldi, "
            "Opera, and Firefox — and saved as one standard bookmarks file that any browser can "
            "import. Passwords can't be copied (Windows encrypts them per-machine); sign into "
            "Firefox Sync or your Google account to bring those across."
        )
        bm_body.setObjectName("card-copy")
        bm_body.setWordWrap(True)
        bm_layout.addWidget(bm_body)
        self._bm_status = QLabel("Scan drives above — bookmarks are found automatically.")
        self._bm_status.setObjectName("card-copy")
        self._bm_status.setWordWrap(True)
        bm_layout.addWidget(self._bm_status)
        self._bm_rows = QVBoxLayout()
        self._bm_rows.setSpacing(6)
        bm_layout.addLayout(self._bm_rows)
        bm_btns = QHBoxLayout()
        bm_btns.setSpacing(8)
        self._bm_export_btn = QPushButton("Save Bookmarks File")
        self._bm_export_btn.setObjectName("primary")
        self._bm_export_btn.hide()
        self._bm_export_btn.clicked.connect(self._export_bookmarks)
        bm_btns.addWidget(self._bm_export_btn)
        self._bm_show_btn = QPushButton("Show File")
        self._bm_show_btn.hide()
        self._bm_show_btn.clicked.connect(lambda _=False: QDesktopServices.openUrl(
            QUrl.fromLocalFile(os.path.dirname(self._bm_dest))) if self._bm_dest else None)
        bm_btns.addWidget(self._bm_show_btn)
        bm_btns.addStretch()
        bm_layout.addLayout(bm_btns)
        self._add(bm_card)



    def _build_extras_card(self):
        exe_card, exe_layout = _make_card()
        exe_title = QLabel("What about .exe installers?")
        exe_title.setObjectName("card-title")
        exe_layout.addWidget(exe_title)
        exe_body = QLabel(
            "For games, start with Steam, Heroic, or Lutris. For standalone compatibility apps, "
            "use Bottles so each app gets its own isolated Windows-like environment. "
            "If a native Linux or Flatpak version exists, prefer that first."
        )
        exe_body.setObjectName("card-copy")
        exe_body.setWordWrap(True)
        exe_layout.addWidget(exe_body)
        exe_btns = QHBoxLayout()
        exe_btns.setSpacing(8)
        bottles_btn = QPushButton("Install Bottles")
        bottles_btn.clicked.connect(lambda _=False, b=bottles_btn: _install_flatpak_inline(
            self, b, "com.usebottles.bottles", "Bottles"))
        exe_btns.addWidget(bottles_btn)
        software_btn = QPushButton("Open App Store")
        software_btn.clicked.connect(lambda _=False: self._navigate("App Store"))
        exe_btns.addWidget(software_btn)
        exe_btns.addStretch()
        exe_layout.addLayout(exe_btns)
        self._add(exe_card)



    def _start_bookmark_scan(self, partitions: list):
        profiles = [prof for part in partitions for prof in (part.get("user_profiles") or [])]
        self._clear_layout(self._bm_rows)
        self._bm_export_btn.hide()
        self._bm_show_btn.hide()
        if not profiles:
            self._bm_status.setText("No Windows user profiles found — nothing to read bookmarks from.")
            return
        if self._bm_worker is not None and self._bm_worker.isRunning():
            return
        self._bm_status.setText("Looking for browser bookmarks…")
        worker = DataWorker("bookmarks", lambda: _scan_windows_bookmarks(profiles))
        worker.result.connect(self._on_bookmarks_found)
        self._bm_worker = worker
        _release_worker_when_finished(self, "_bm_worker", worker)
        worker.start()


    def _on_bookmarks_found(self, _key: str, sources: list):
        self._bm_sources = sources
        self._clear_layout(self._bm_rows)
        if not sources:
            self._bm_status.setText("No browser bookmarks found on the scanned drives.")
            return
        total = sum(len(src["entries"]) for src in sources)
        self._bm_status.setText(
            f"Found {total} bookmark{'s' if total != 1 else ''} in "
            f"{len(sources)} browser profile{'s' if len(sources) != 1 else ''}:"
        )
        for src in sources:
            self._bm_rows.addWidget(self._make_migration_row(
                "ok", src["browser"],
                f"{len(src['entries'])} bookmarks — Windows user {src['user']}",
            ))
        self._bm_export_btn.show()


    def _export_bookmarks(self):
        if not self._bm_sources:
            return
        dest = os.path.join(_windows_folder_dest("Documents"), "Windows Bookmarks.html")
        try:
            total = _write_bookmarks_html(self._bm_sources, dest)
        except OSError as exc:
            self._bm_status.setText(f"Could not write the bookmarks file: {exc}")
            return
        self._bm_dest = dest
        home = os.path.expanduser("~")
        self._bm_status.setText(
            f"✓ Saved {total} bookmarks to {dest.replace(home, '~', 1)}. In your browser, open "
            "the bookmark manager (Ctrl+Shift+O) and choose Import bookmarks from HTML."
        )
        self._bm_show_btn.show()

    # ── PC drive extras ──────────────────────────────────────────────────


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
        worker.result.connect(self._on_extras)
        worker.failed.connect(
            lambda _key, message: self._wp_status.setText(
                f"Could not read the PC drive: {message}"))
        self._extras_worker = worker
        _release_worker_when_finished(self, "_extras_worker", worker)
        worker.start()


    def _on_extras(self, _key: str, extras: dict):
        self._extras = extras

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
                f"Found {fonts['count']} font files ({_human_bytes(fonts['bytes'])}) "
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
