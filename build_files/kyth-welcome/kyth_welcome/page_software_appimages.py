import os
import re
import shutil
from .core_base import _restyle
from .qt import (
    QDesktopServices, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QUrl,
    QVBoxLayout, QWidget, Qt,
)
from .widgets import AppImageDropCard, _make_card


class _AppImageTabMixin:
    # ── Tab 2: AppImages ──────────────────────────────────────────────────────

    def _build_appimage_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)

        import_card = AppImageDropCard(self._import_appimage_path, self._set_appimage_icon_path)
        import_layout = QVBoxLayout(import_card)
        import_layout.setContentsMargins(24, 22, 24, 22)
        import_layout.setSpacing(16)

        import_top = QHBoxLayout()
        import_top.setSpacing(16)
        drop_glyph = QLabel("APP")
        drop_glyph.setObjectName("drop-glyph")
        drop_glyph.setFixedSize(58, 58)
        drop_glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        import_top.addWidget(drop_glyph)

        import_text = QVBoxLayout()
        import_text.setSpacing(5)
        import_title = QLabel("Import AppImages")
        import_title.setObjectName("drop-title")
        import_text.addWidget(import_title)
        import_body = QLabel(
            "Drop an AppImage here, or drop a PNG/SVG/JPG icon first. KythOS copies the app to ~/Applications, makes it executable, and can create a polished launcher."
        )
        import_body.setObjectName("card-copy")
        import_body.setWordWrap(True)
        import_text.addWidget(import_body)
        import_top.addLayout(import_text, 1)
        import_layout.addLayout(import_top)

        import_btn_row = QHBoxLayout()
        import_btn_row.setSpacing(10)
        self._ai_import_btn = QPushButton("Import .AppImage…")
        self._ai_import_btn.setObjectName("primary")
        self._ai_import_btn.clicked.connect(self._import_appimage)
        import_btn_row.addWidget(self._ai_import_btn)
        self._ai_icon_btn = QPushButton("Choose Icon…")
        self._ai_icon_btn.clicked.connect(self._choose_appimage_icon)
        import_btn_row.addWidget(self._ai_icon_btn)
        self._ai_icon_clear_btn = QPushButton("Clear Icon")
        self._ai_icon_clear_btn.clicked.connect(self._clear_appimage_icon)
        self._ai_icon_clear_btn.hide()
        import_btn_row.addWidget(self._ai_icon_clear_btn)
        import_btn_row.addStretch()
        import_layout.addLayout(import_btn_row)
        self._ai_icon_status = QLabel("No custom icon selected.")
        self._ai_icon_status.setObjectName("status-dim")
        import_layout.addWidget(self._ai_icon_status)
        self._ai_status = QLabel()
        self._ai_status.setObjectName("subheading")
        self._ai_status.hide()
        import_layout.addWidget(self._ai_status)
        layout.addWidget(import_card)

        curated_card, curated_layout = _make_card()
        curated_title = QLabel("Popular AppImages")
        curated_title.setObjectName("card-title")
        curated_layout.addWidget(curated_title)
        curated_body = QLabel(
            "Apps distributed only as AppImages. Download from their official site, "
            "then use Import above to register them in your app menu."
        )
        curated_body.setObjectName("card-copy")
        curated_body.setWordWrap(True)
        curated_layout.addWidget(curated_body)
        for entry in self._CURATED_APPIMAGES:
            row = QFrame()
            row.setObjectName("stat-tile")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 10, 14, 10)
            row_layout.setSpacing(12)
            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            name_lbl = QLabel(entry["name"])
            name_lbl.setObjectName("card-summary")
            text_col.addWidget(name_lbl)
            desc_lbl = QLabel(entry["desc"])
            desc_lbl.setObjectName("card-copy")
            desc_lbl.setWordWrap(True)
            text_col.addWidget(desc_lbl)
            row_layout.addLayout(text_col, 1)
            dl_btn = QPushButton("Download Page")
            dl_btn.clicked.connect(
                lambda _=False, url=entry["url"]: QDesktopServices.openUrl(QUrl(url))
            )
            row_layout.addWidget(dl_btn)
            curated_layout.addWidget(row)
        layout.addWidget(curated_card)
        return tab

    def _import_appimage(self):
        src, _ = QFileDialog.getOpenFileName(
            self,
            "Select AppImage",
            os.path.expanduser("~"),
            "AppImages (*.AppImage *.appimage);;All Files (*)",
        )
        if not src:
            return
        self._import_appimage_path(src)

    def _choose_appimage_icon(self):
        src, _ = QFileDialog.getOpenFileName(
            self,
            "Select App Icon",
            os.path.expanduser("~"),
            "Images (*.png *.svg *.svgz *.jpg *.jpeg *.webp *.ico *.xpm);;All Files (*)",
        )
        if src:
            self._set_appimage_icon_path(src)

    def _set_appimage_icon_path(self, src: str):
        if not AppImageDropCard._is_icon_path(src) or not os.path.isfile(src):
            self._ai_icon_status.setText("That file does not look like a usable app icon.")
            self._ai_icon_status.setObjectName("status-warn")
            _restyle(self._ai_icon_status)
            return
        self._ai_icon_path = src
        self._ai_icon_status.setText(f"Icon ready: {os.path.basename(src)}")
        self._ai_icon_status.setObjectName("status-ok")
        self._ai_icon_clear_btn.show()
        _restyle(self._ai_icon_status)

    def _clear_appimage_icon(self):
        self._ai_icon_path = ""
        self._ai_icon_status.setText("No custom icon selected.")
        self._ai_icon_status.setObjectName("status-dim")
        self._ai_icon_clear_btn.hide()
        _restyle(self._ai_icon_status)

    def _import_appimage_path(self, src: str):
        if not re.search(r"\.[Aa]pp[Ii]mage$", src):
            self._ai_status.setText("That file does not look like an AppImage.")
            self._ai_status.setObjectName("status-warn")
            self._ai_status.show()
            _restyle(self._ai_status)
            return
        if not os.path.isfile(src):
            self._ai_status.setText("Dropped AppImage file was not found.")
            self._ai_status.setObjectName("status-err")
            self._ai_status.show()
            _restyle(self._ai_status)
            return
        apps_dir = os.path.expanduser("~/Applications")
        try:
            os.makedirs(apps_dir, exist_ok=True)
        except OSError as exc:
            self._ai_status.setText(f"Cannot create ~/Applications: {exc}")
            self._ai_status.setObjectName("status-err")
            self._ai_status.show()
            _restyle(self._ai_status)
            return

        basename = os.path.basename(src)
        dest = os.path.join(apps_dir, basename)
        if os.path.realpath(src) != os.path.realpath(dest):
            try:
                shutil.copy2(src, dest)
            except OSError as exc:
                self._ai_status.setText(f"Copy failed: {exc}")
                self._ai_status.setObjectName("status-err")
                self._ai_status.show()
                _restyle(self._ai_status)
                return
        try:
            os.chmod(dest, 0o700)  # nosemgrep
        except OSError:
            pass

        name = re.sub(r"\.[Aa]pp[Ii]mage$", "", basename)
        reply = QMessageBox.question(
            self,
            "Add to App Menu?",
            f"Add “{name}” to your application menu?\n\n"
            "This creates a launcher in ~/.local/share/applications/.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._create_appimage_launcher(name, dest, self._ai_icon_path)

        self._ai_status.setText(f"{name} imported to ~/Applications.")
        self._ai_status.setObjectName("status-ok")
        self._ai_status.show()
        _restyle(self._ai_status)
        self._clear_appimage_icon()

    def _create_appimage_launcher(self, name: str, appimage_path: str, icon_path: str = ""):
        desktop_dir = os.path.expanduser("~/.local/share/applications")
        try:
            os.makedirs(desktop_dir, exist_ok=True)
            safe_name = re.sub(r"[^a-zA-Z0-9_-]", "-", name)
            desktop_path = os.path.join(desktop_dir, f"{safe_name}.desktop")
            launcher_icon = "application-x-executable"
            if icon_path and os.path.isfile(icon_path):
                icon_dir = os.path.expanduser("~/.local/share/icons/kyth-appimages")
                os.makedirs(icon_dir, exist_ok=True)
                ext = os.path.splitext(icon_path)[1].lower() or ".png"
                icon_dest = os.path.join(icon_dir, f"{safe_name}{ext}")
                shutil.copy2(icon_path, icon_dest)
                launcher_icon = icon_dest
            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={name}\n"
                f"Exec={appimage_path}\n"
                f"Icon={launcher_icon}\n"
                "Terminal=false\n"
                "Categories=Utility;\n"
            )
            with open(desktop_path, "w", encoding="utf-8") as f:
                f.write(content)
            os.chmod(desktop_path, 0o600)
        except OSError:
            return
        from .services.desktop import refresh_desktop_database
        refresh_desktop_database(desktop_dir)
