"""Windows Migration page — browser bookmarks card + handlers, plus the small
static ".exe installers" tip card, _BookmarksMixin.

The PC-drive "extras" scan (wallpaper/fonts/saves/sticky/rdp) used to live in
this file too under a same-named `_build_extras_card`/`_on_extras` pair, but
`_on_extras` only ever populates widgets owned by pc_drive_extras.py's
cards — it has moved there so the scan sits next to what it drives.
"""

from __future__ import annotations

import os
from ..services.runtime import DataWorker, release_worker_when_finished
from ..actions import _install_flatpak_inline
from ..services.windows_migration import (
    _scan_windows_bookmarks,
    _windows_folder_dest,
    _write_bookmarks_html,
)
from ..qt import (
    QDesktopServices, QHBoxLayout, QLabel, QPushButton, QUrl, QVBoxLayout,
)
from ..widgets import (
    _make_card, _make_tip_card,
)


class _BookmarksMixin:
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
        # Bottles installs inline: the button disables/relabels itself
        # while running, so it needs a live reference to itself —
        # connected below instead of passed as a callback.
        card, (bottles_btn, _store_btn) = _make_tip_card(
            "What about .exe installers?",
            "For games, start with Steam, Heroic, or Lutris. For standalone compatibility apps, "
            "use Bottles so each app gets its own isolated Windows-like environment. "
            "If a native Linux or Flatpak version exists, prefer that first.",
            primary=None,
            buttons=[
                ("Install Bottles", None),
                ("Open App Store", lambda _=False: self._navigate("App Store")),
            ],
        )
        bottles_btn.clicked.connect(lambda _=False, b=bottles_btn: _install_flatpak_inline(
            self, b, "com.usebottles.bottles", "Bottles"))
        self._add(card)

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
        release_worker_when_finished(self, "_bm_worker", worker)
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
