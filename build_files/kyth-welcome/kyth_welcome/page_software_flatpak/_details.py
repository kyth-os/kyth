# __KYTH_GENERATED_IMPORTS__
from ..core_base import _restyle
from ..services.flatpak import _is_flatpak_installed
from ..qt import (
    QDesktopServices, QDialog, QFrame, QHBoxLayout, QIcon, QLabel, QPushButton, QTextEdit, QUrl, QVBoxLayout,
)


class _DetailsMixin:
    def _show_fp_details(self, entry: dict):
        app_id = entry.get("application_id", "").strip()
        details = self._fp_appstream_details(app_id)
        name = details.get("name") or entry.get("name") or app_id
        dlg = QDialog(self)
        dlg.setWindowTitle(name)
        dlg.setMinimumWidth(640)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(64, 64)
        icon_path = self._fp_icon_path(app_id)
        icon = QIcon(icon_path) if icon_path else QIcon.fromTheme("package-x-generic")
        icon_lbl.setPixmap(icon.pixmap(64, 64))
        header.addWidget(icon_lbl)
        title_col = QVBoxLayout()
        title = QLabel(name)
        title.setObjectName("card-title")
        title_col.addWidget(title)
        meta = QLabel(app_id)
        meta.setObjectName("card-copy")
        title_col.addWidget(meta)
        header.addLayout(title_col, 1)
        layout.addLayout(header)

        summary = QLabel(details.get("summary") or entry.get("description") or "")
        summary.setObjectName("card-summary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        body_text = details.get("description") or "No extended AppStream description is available for this app yet."
        body = QTextEdit()
        body.setReadOnly(True)
        body.setMaximumHeight(180)
        body.setPlainText(body_text)
        layout.addWidget(body)

        facts = []
        if details.get("developer"):
            facts.append(f"Developer: {details['developer']}")
        version = entry.get("version") or details.get("version")
        if version:
            facts.append(f"Version: {version}")
        if entry.get("download_size"):
            facts.append(f"Download: {entry['download_size']}")
        if entry.get("installed_size"):
            facts.append(f"Installed size: {entry['installed_size']}")
        if details.get("license"):
            facts.append(f"License: {details['license']}")
        if details.get("categories"):
            facts.append("Categories: " + ", ".join(details["categories"][:6]))
        facts.append("Flathub verification: " + ("verified" if details.get("verified") else "not marked verified"))
        fact_lbl = QLabel("\n".join(facts))
        fact_lbl.setObjectName("card-copy")
        fact_lbl.setWordWrap(True)
        layout.addWidget(fact_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        homepage = details.get("homepage")
        if homepage:
            homepage_btn = QPushButton("Homepage")
            homepage_btn.clicked.connect(lambda _=False, url=homepage: QDesktopServices.openUrl(QUrl(url)))
            btn_row.addWidget(homepage_btn)
        screenshots = details.get("screenshots") or []
        if screenshots:
            shot_btn = QPushButton("Screenshot")
            shot_btn.clicked.connect(lambda _=False, url=screenshots[0]: QDesktopServices.openUrl(QUrl(url)))
            btn_row.addWidget(shot_btn)
        flathub_btn = QPushButton("Flathub Page")
        flathub_btn.clicked.connect(lambda _=False, aid=app_id: QDesktopServices.openUrl(QUrl(f"https://flathub.org/apps/{aid}")))
        btn_row.addWidget(flathub_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dlg.exec()

    def _make_fp_result_row(self, entry: dict) -> QFrame:
        app_id = entry.get("application_id", "").strip()
        name = entry.get("name", app_id).strip() or app_id
        summary = entry.get("description", "").strip()
        version = entry.get("version", "").strip()
        download_size = entry.get("download_size", "").strip()
        details = self._fp_appstream_details(app_id)
        if details:
            name = details.get("name") or name
            summary = details.get("summary") or summary
            version = version or details.get("version", "")

        row = QFrame()
        row.setObjectName("stat-tile")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(14, 10, 14, 10)
        row_layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(48, 48)
        icon_path = self._fp_icon_path(app_id)
        icon = QIcon(icon_path) if icon_path else QIcon.fromTheme("package-x-generic")
        icon_lbl.setPixmap(icon.pixmap(48, 48))
        row_layout.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name_lbl = QLabel(name or app_id)
        name_lbl.setObjectName("card-summary")
        text_col.addWidget(name_lbl)
        meta_bits = [app_id]
        if version:
            meta_bits.append(version)
        if download_size:
            meta_bits.append(download_size)
        if details.get("verified"):
            meta_bits.append("Verified")
        id_lbl = QLabel("  \u2022  ".join(meta_bits))
        id_lbl.setObjectName("card-copy")
        text_col.addWidget(id_lbl)
        if summary:
            summary_lbl = QLabel(summary)
            summary_lbl.setObjectName("card-copy")
            summary_lbl.setWordWrap(True)
            text_col.addWidget(summary_lbl)
        row_layout.addLayout(text_col, 1)

        details_btn = QPushButton("Details")
        details_btn.clicked.connect(lambda _=False, e=entry: self._show_fp_details(e))
        row_layout.addWidget(details_btn)

        open_btn = QPushButton("Open")
        row_layout.addWidget(open_btn)

        install_btn = QPushButton()
        self._configure_fp_lifecycle_buttons(app_id, name, install_btn, open_btn)
        row_layout.addWidget(install_btn)
        return row

    def _configure_fp_lifecycle_buttons(
        self,
        app_id: str,
        name: str,
        action_btn: QPushButton,
        open_btn: QPushButton | None = None,
        installed: bool | None = None,
    ) -> None:
        installed = _is_flatpak_installed(app_id) if installed is None else installed
        for btn in (action_btn, open_btn):
            if btn is None:
                continue
            try:
                btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass

        if open_btn is not None:
            open_btn.setVisible(installed)
            open_btn.setEnabled(installed)
            open_btn.setObjectName("primary" if installed else "")
            if installed:
                open_btn.clicked.connect(lambda _=False, aid=app_id: self._open_fp_app(aid))
            _restyle(open_btn)

        if installed:
            action_btn.setText("Uninstall")
            action_btn.setObjectName("danger")
            action_btn.clicked.connect(
                lambda _=False, aid=app_id, n=name, b=action_btn, ob=open_btn: self._fp_store_uninstall(aid, n, b, ob)
            )
        else:
            action_btn.setText("Install")
            action_btn.setObjectName("primary")
            action_btn.clicked.connect(
                lambda _=False, aid=app_id, n=name, b=action_btn, ob=open_btn: self._fp_install(aid, n, b, ob)
            )
        action_btn.setEnabled(True)
        _restyle(action_btn)

    def _set_fp_task_state(self, message: str, state: str) -> None:
        styles = {
            "idle": "task-status-idle",
            "running": "task-status-running",
            "success": "task-status-ok",
            "warn": "task-status-warn",
            "error": "task-status-err",
        }
        self._fp_status.setText(message)
        self._fp_status.setObjectName(styles.get(state, "task-status-idle"))
        self._fp_status.show()
        _restyle(self._fp_status)
