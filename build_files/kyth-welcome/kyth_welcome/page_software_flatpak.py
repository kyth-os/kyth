import json
import os
import shlex
from .services.launch import flatpak_run, popen
from .core_base import _restyle
from .services.software import Worker, _finish_worker, _is_flatpak_installed, load_appstream_catalog
from .qt import (  # noqa: E501
    QDesktopServices, QDialog, QFrame, QHBoxLayout, QIcon, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QTextEdit, QUrl, QVBoxLayout, QWidget,
)
from .widgets import _make_card, _set_log_panel


class _FlatpakStoreTabMixin:
    # ── Tab 4: Flatpak Store ──────────────────────────────────────────────────

    def _build_flatpak_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        hero = QFrame()
        hero.setObjectName("store-hero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(22, 20, 22, 20)
        hero_layout.setSpacing(18)
        hero_text = QVBoxLayout()
        hero_text.setSpacing(6)
        kicker = QLabel("KYTH APP STORE")
        kicker.setObjectName("store-kicker")
        hero_text.addWidget(kicker)
        title = QLabel("Useful apps, ready to install")
        title.setObjectName("store-hero-title")
        title.setWordWrap(True)
        hero_text.addWidget(title)
        intro = QLabel(
            "Install trusted Flatpaks without leaving System Hub. Start with trending picks, browse curated shelves, or search the full Flathub catalog."
        )
        intro.setObjectName("card-copy")
        intro.setWordWrap(True)
        hero_text.addWidget(intro)
        hero_layout.addLayout(hero_text, 1)
        hero_actions = QVBoxLayout()
        hero_actions.setSpacing(8)
        featured_btn = QPushButton("Show Featured")
        featured_btn.setObjectName("primary")
        featured_btn.clicked.connect(lambda _=False: self._render_store_landing())
        hero_actions.addWidget(featured_btn)
        browse_btn = QPushButton("Browse Catalog")
        browse_btn.clicked.connect(lambda _=False: self._load_fp_catalog())
        hero_actions.addWidget(browse_btn)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_fp_metadata)
        hero_actions.addWidget(refresh_btn)
        hero_actions.addStretch()
        hero_layout.addLayout(hero_actions)
        layout.addWidget(hero)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self._fp_refresh_btn = QPushButton("Refresh")
        self._fp_refresh_btn.clicked.connect(self._refresh_fp_metadata)
        action_row.addWidget(self._fp_refresh_btn)
        self._fp_catalog_btn = QPushButton("Browse All")
        self._fp_catalog_btn.clicked.connect(lambda _=False: self._load_fp_catalog())
        action_row.addWidget(self._fp_catalog_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        category_row = QHBoxLayout()
        category_row.setSpacing(8)
        for label, query in self._STORE_CATEGORIES:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, q=query, l=label: self._show_fp_category(q, l))
            category_row.addWidget(btn)
        category_row.addStretch()
        layout.addLayout(category_row)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self._fp_search_box = QLineEdit()
        self._fp_search_box.setPlaceholderText("Search Flathub...  e.g. firefox, obsidian, gimp")
        self._fp_search_box.returnPressed.connect(self._run_fp_search)
        search_row.addWidget(self._fp_search_box, 1)
        self._fp_search_btn = QPushButton("Search")
        self._fp_search_btn.setObjectName("primary")
        self._fp_search_btn.clicked.connect(self._run_fp_search)
        search_row.addWidget(self._fp_search_btn)
        layout.addLayout(search_row)

        self._fp_status = QLabel()
        self._fp_status.setObjectName("status-dim")
        self._fp_status.hide()
        layout.addWidget(self._fp_status)

        self._fp_progress = QProgressBar()
        self._fp_progress.setRange(0, 0)
        self._fp_progress.hide()
        layout.addWidget(self._fp_progress)

        self._fp_install_log_toggle = QPushButton("Show details")
        self._fp_install_log_toggle.setCheckable(True)
        self._fp_install_log_toggle.hide()
        layout.addWidget(self._fp_install_log_toggle)

        self._fp_install_log = QTextEdit()
        self._fp_install_log.document().setMaximumBlockCount(5000)
        self._fp_install_log.setReadOnly(True)
        self._fp_install_log.setMaximumHeight(130)
        self._fp_install_log.hide()
        layout.addWidget(self._fp_install_log)
        self._fp_install_log_toggle.clicked.connect(
            lambda checked: _set_log_panel(self._fp_install_log_toggle, self._fp_install_log, checked)
        )

        self._fp_results_layout = QVBoxLayout()
        self._fp_results_layout.setSpacing(8)
        layout.addLayout(self._fp_results_layout)

        self._render_store_landing()
        return tab

    def _fallback_store_names(self) -> dict[str, tuple[str, str]]:
        names: dict[str, tuple[str, str]] = {}
        for pack in self._STARTER_PACKS:
            for app_id, label, _ in pack["apps"]:
                names[app_id] = (label, pack["desc"])
        for tool in self._CR_TOOLS + self._SEC_HOST_TOOLS:
            names[tool["flatpak"]] = (tool["name"], tool["desc"])
        for _, desc, app_id in self._FAMILIAR_APPS:
            if app_id:
                names.setdefault(app_id, (app_id.rsplit(".", 1)[-1], desc))
        names.update({
            "io.github.flattool.Warehouse": ("Warehouse", "Manage Flatpak apps, remotes, data, and leftover files."),
            "com.mattjakeman.ExtensionManager": ("Extension Manager", "Browse, install, and manage GNOME Shell extensions."),
            "org.freedesktop.Piper": ("Piper", "Configure gaming mice and supported peripherals."),
        })
        return names

    def _store_entry_for_app(self, app_id: str) -> dict:
        details = self._fp_appstream_details(app_id)
        fallback_name, fallback_summary = self._fallback_store_names().get(
            app_id, (app_id.rsplit(".", 1)[-1], "")
        )
        return {
            "application_id": app_id,
            "name": details.get("name") or fallback_name,
            "description": details.get("summary") or fallback_summary,
            "version": details.get("version", ""),
            "remote": "flathub",
        }

    def _render_store_landing(self):
        self._clear_fp_results()
        catalog = self._fp_appstream_catalog()
        self._fp_status.setText(
            "Featured Kyth picks. Search or browse the catalog for more."
            if catalog else
            "Featured Kyth picks. Refresh metadata for richer descriptions, icons, and categories."
        )
        self._fp_status.setObjectName("status-dim")
        self._fp_status.show()
        _restyle(self._fp_status)

        trending_label = QLabel("Trending on Kyth")
        trending_label.setObjectName("section-heading")
        self._fp_results_layout.addWidget(trending_label)

        rows = [self._TRENDING_APPS[:4], self._TRENDING_APPS[4:]]
        for app_ids in rows:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(10)
            for app_id in app_ids:
                row_layout.addWidget(self._make_store_app_card(self._store_entry_for_app(app_id)), 1)
            self._fp_results_layout.addLayout(row_layout)

        categories_label = QLabel("Browse by category")
        categories_label.setObjectName("section-heading")
        self._fp_results_layout.addWidget(categories_label)

        shelf_row = QHBoxLayout()
        shelf_row.setSpacing(10)
        for shelf in self._STORE_SHELVES:
            shelf_row.addWidget(self._make_store_category_card(shelf), 1)
        self._fp_results_layout.addLayout(shelf_row)

        for shelf in self._STORE_SHELVES[:3]:
            self._fp_results_layout.addWidget(self._make_store_shelf(shelf))

    def _make_store_app_card(self, entry: dict) -> QFrame:
        app_id = entry.get("application_id", "").strip()
        name = entry.get("name", app_id).strip() or app_id
        summary = entry.get("description", "").strip()
        details = self._fp_appstream_details(app_id)

        card = QFrame()
        card.setObjectName("store-app-card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(44, 44)
        icon_path = self._fp_icon_path(app_id)
        icon = QIcon(icon_path) if icon_path else QIcon.fromTheme("package-x-generic")
        icon_lbl.setPixmap(icon.pixmap(44, 44))
        top.addWidget(icon_lbl)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        name_lbl = QLabel(name)
        name_lbl.setObjectName("card-summary")
        name_lbl.setWordWrap(True)
        title_col.addWidget(name_lbl)
        meta = QLabel("Verified" if details.get("verified") else "Flatpak")
        meta.setObjectName("starter-pack-meta")
        title_col.addWidget(meta)
        top.addLayout(title_col, 1)
        layout.addLayout(top)

        summary_lbl = QLabel(summary or app_id)
        summary_lbl.setObjectName("card-copy")
        summary_lbl.setWordWrap(True)
        summary_lbl.setMinimumHeight(48)
        layout.addWidget(summary_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        details_btn = QPushButton("Details")
        details_btn.clicked.connect(lambda _=False, e=entry: self._show_fp_details(e))
        btn_row.addWidget(details_btn)
        open_btn = QPushButton("Open")
        install_btn = QPushButton()
        self._configure_fp_lifecycle_buttons(app_id, name, install_btn, open_btn)
        btn_row.addWidget(open_btn)
        btn_row.addWidget(install_btn)
        layout.addLayout(btn_row)
        return card

    def _make_store_category_card(self, shelf: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("store-category-card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)
        title = QLabel(shelf["name"])
        title.setObjectName("card-title")
        title.setWordWrap(True)
        layout.addWidget(title)
        count = QLabel(f"{len(shelf['apps'])}+ picks")
        count.setObjectName("starter-pack-meta")
        layout.addWidget(count)
        btn = QPushButton("Open Shelf")
        btn.clicked.connect(lambda _=False, s=shelf: self._open_store_shelf(s))
        layout.addWidget(btn)
        return card

    def _make_store_shelf(self, shelf: dict) -> QFrame:
        panel, layout = _make_card()
        head = QHBoxLayout()
        title = QLabel(shelf["name"])
        title.setObjectName("card-title")
        head.addWidget(title, 1)
        all_btn = QPushButton("More")
        all_btn.clicked.connect(lambda _=False, q=shelf["query"], n=shelf["name"]: self._show_fp_category(q, n))
        head.addWidget(all_btn)
        layout.addLayout(head)
        row = QHBoxLayout()
        row.setSpacing(10)
        for app_id in shelf["apps"]:
            row.addWidget(self._make_store_app_card(self._store_entry_for_app(app_id)), 1)
        layout.addLayout(row)
        return panel

    def _open_store_shelf(self, shelf: dict):
        self._clear_fp_results()
        self._set_fp_task_state(f"{shelf['name']}: curated apps for Kyth users.", "idle")
        self._fp_results_layout.addWidget(self._make_store_shelf(shelf))
        more_btn = QPushButton(f"Browse more {shelf['name']} apps")
        more_btn.clicked.connect(lambda _=False, q=shelf["query"], n=shelf["name"]: self._show_fp_category(q, n))
        self._fp_results_layout.addWidget(more_btn)

    def _run_fp_search(self):
        if self._fp_search_worker and self._fp_search_worker.isRunning():
            return
        query = self._fp_search_box.text().strip()
        if not query:
            return
        self._clear_fp_results()
        self._fp_search_lines = []
        self._fp_progress.show()
        self._set_fp_task_state(f"Searching Flathub for “{query}”…", "running")
        self._fp_search_btn.setEnabled(False)
        self._fp_search_worker = Worker(
            ["flatpak", "search", "-j", query]
        )
        self._fp_search_worker.line.connect(self._on_fp_search_line)
        self._fp_search_worker.done.connect(self._on_fp_search_done)
        self._fp_search_worker.start()

    def _on_fp_search_line(self, ln: str):
        self._fp_search_lines.append(ln)

    def _on_fp_search_done(self, code: int):
        self._fp_progress.hide()
        _finish_worker(self, attr="_fp_search_worker")
        self._fp_search_btn.setEnabled(True)
        self._clear_fp_results()
        output = "\n".join(self._fp_search_lines).strip()
        results = []
        if output.startswith("["):
            try:
                for item in json.loads(output):
                    app_id = (item.get("application_id") or item.get("application") or "").strip()
                    if app_id:
                        results.append({
                            "application_id": app_id,
                            "name": (item.get("name") or app_id).strip(),
                            "description": (item.get("description") or "").strip(),
                            "version": (item.get("version") or "").strip(),
                            "remote": (item.get("remotes") or item.get("remote") or "flathub").strip(),
                        })
            except (json.JSONDecodeError, TypeError):
                results = []
        else:
            for line in self._fp_search_lines:
                parts = line.split("\t")
                if len(parts) >= 2:
                    app_id = parts[0].strip()
                    name = parts[1].strip()
                    summary = parts[2].strip() if len(parts) >= 3 else ""
                    if app_id:
                        results.append({
                            "application_id": app_id,
                            "name": name or app_id,
                            "description": summary,
                            "version": "",
                            "remote": "flathub",
                        })
        if not results:
            detail = next((line.strip() for line in self._fp_search_lines if line.strip()), "")
            if code == 0:
                msg = "No results found."
            elif detail:
                msg = f"Search failed — {detail}"
            else:
                msg = "Search failed — check that Flatpak and Flathub are available."
            self._set_fp_task_state(msg, "idle" if code == 0 else "warn")
            return
        shown = results[:30]
        count_msg = f"{len(results)} result{'s' if len(results) != 1 else ''} found"
        if len(results) > 30:
            count_msg += " — showing top 30"
        self._set_fp_task_state(count_msg + ".", "idle")
        for entry in shown:
            self._fp_results_layout.addWidget(self._make_fp_result_row(entry))

    def _clear_fp_results(self):
        def clear_layout(layout):
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                child_layout = item.layout()
                if widget:
                    widget.deleteLater()
                elif child_layout:
                    clear_layout(child_layout)
        while self._fp_results_layout.count():
            item = self._fp_results_layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget:
                widget.deleteLater()
            elif child_layout:
                clear_layout(child_layout)

    def _refresh_fp_metadata(self):
        if self._fp_refresh_worker and self._fp_refresh_worker.isRunning():
            return
        self._fp_search_lines = []
        self._fp_progress.show()
        self._set_fp_task_state("Refreshing Flathub metadata...", "running")
        self._fp_refresh_btn.setEnabled(False)
        self._fp_refresh_worker = Worker(["flatpak", "update", "--appstream"])
        self._fp_refresh_worker.line.connect(self._on_fp_search_line)
        self._fp_refresh_worker.done.connect(self._on_fp_refresh_done)
        self._fp_refresh_worker.start()

    def _on_fp_refresh_done(self, code: int):
        self._fp_progress.hide()
        _finish_worker(self, attr="_fp_refresh_worker")
        self._fp_refresh_btn.setEnabled(True)
        self._fp_appstream_cache = None
        self._fp_catalog_entries = []
        if code == 0:
            self._set_fp_task_state("Flathub metadata refreshed.", "success")
        else:
            detail = next((line.strip() for line in self._fp_search_lines if line.strip()), "")
            self._set_fp_task_state(detail or f"Metadata refresh failed (exit {code}). Cached data can still be used.", "warn")

    def _load_fp_catalog(self):
        if self._fp_catalog_worker and self._fp_catalog_worker.isRunning():
            return
        self._clear_fp_results()
        self._fp_catalog_lines = []
        self._fp_progress.show()
        self._set_fp_task_state("Loading cached Flathub catalog...", "running")
        self._fp_catalog_btn.setEnabled(False)
        self._fp_catalog_worker = Worker([
            "flatpak", "remote-ls", "--cached", "--app",
            "--columns=application,name,description,version,download-size,installed-size",
            "-j", "flathub",
        ])
        self._fp_catalog_worker.line.connect(self._on_fp_catalog_line)
        self._fp_catalog_worker.done.connect(self._on_fp_catalog_done)
        self._fp_catalog_worker.start()

    def _on_fp_catalog_line(self, ln: str):
        self._fp_catalog_lines.append(ln)

    def _on_fp_catalog_done(self, code: int):
        self._fp_progress.hide()
        _finish_worker(self, attr="_fp_catalog_worker")
        self._fp_catalog_btn.setEnabled(True)
        output = "\n".join(self._fp_catalog_lines).strip()
        entries = []
        if output.startswith("["):
            try:
                for item in json.loads(output):
                    app_id = (item.get("application_id") or item.get("application") or "").strip()
                    if app_id:
                        item["application_id"] = app_id
                        item["remote"] = "flathub"
                        entries.append(item)
            except (json.JSONDecodeError, TypeError):
                entries = []
        if code != 0 or not entries:
            detail = next((line.strip() for line in self._fp_catalog_lines if line.strip()), "")
            self._set_fp_task_state(detail or "Cached Flathub catalog could not be loaded.", "warn")
            return
        self._fp_catalog_entries = entries
        self._render_fp_entries(entries, "Cached Flathub catalog")

    def _render_fp_entries(self, entries: list[dict], title: str, limit: int = 60):
        self._clear_fp_results()
        shown = entries[:limit]
        count_msg = f"{title}: {len(entries)} app{'s' if len(entries) != 1 else ''}"
        if len(entries) > limit:
            count_msg += f" — showing first {limit}"
        self._set_fp_task_state(count_msg + ".", "idle")
        for entry in shown:
            self._fp_results_layout.addWidget(self._make_fp_result_row(entry))

    def _show_fp_category(self, category_query: str, label: str):
        catalog = self._fp_appstream_catalog()
        tokens = {token.strip().lower() for token in category_query.split() if token.strip()}
        matches = []
        for app_id, details in catalog.items():
            categories = {cat.lower() for cat in details.get("categories", [])}
            if not tokens.intersection(categories):
                continue
            entry = {
                "application_id": app_id,
                "name": details.get("name", app_id),
                "description": details.get("summary", ""),
                "version": details.get("version", ""),
                "remote": "flathub",
            }
            matches.append(entry)
        matches.sort(key=lambda item: (item.get("name") or item.get("application_id") or "").lower())
        self._render_fp_entries(matches, label)

    def _fp_icon_path(self, app_id: str) -> str:
        for size in ("128x128", "64x64"):
            path = f"/var/lib/flatpak/appstream/flathub/x86_64/active/icons/{size}/{app_id}.png"
            if os.path.exists(path):
                return path
        return ""

    def _fp_appstream_catalog(self) -> dict[str, dict]:
        if self._fp_appstream_cache is not None:
            return self._fp_appstream_cache
        self._fp_appstream_cache = load_appstream_catalog()
        return self._fp_appstream_cache

    def _fp_appstream_details(self, app_id: str) -> dict:
        return self._fp_appstream_catalog().get(app_id, {})

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
        id_lbl = QLabel("  •  ".join(meta_bits))
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

    def _open_fp_app(self, app_id: str) -> None:
        flatpak_run(app_id)

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

    def _fp_install(self, app_id: str, name: str, btn: QPushButton, open_btn: QPushButton | None = None):
        if self._fp_install_worker and self._fp_install_worker.isRunning():
            return
        self._fp_installing = app_id
        btn.setText("Installing…")
        btn.setEnabled(False)
        self._fp_install_log.clear()
        self._fp_install_log.append(f"→ flatpak install flathub {app_id}\n")
        self._fp_install_log_toggle.show()
        _set_log_panel(self._fp_install_log_toggle, self._fp_install_log, False)
        self._fp_progress.show()
        self._set_fp_task_state(f"Installing {name or app_id}…", "running")
        cmd = [
            "bash", "-c",
            "flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
            f" && flatpak install -y flathub {shlex.quote(app_id)}",
        ]
        self._fp_install_worker = Worker(cmd)
        self._fp_install_worker.line.connect(self._on_fp_install_line)
        self._fp_install_worker.done.connect(
            lambda code, aid=app_id, n=name, b=btn, ob=open_btn: self._on_fp_install_done(code, aid, n, b, ob)
        )
        self._fp_install_worker.start()

    def _on_fp_install_line(self, ln: str):
        self._fp_install_log.append(ln)
        self._fp_install_log.ensureCursorVisible()

    def _on_fp_install_done(self, code: int, app_id: str, name: str, btn: QPushButton, open_btn: QPushButton | None = None):
        self._fp_progress.hide()
        _finish_worker(self, attr="_fp_install_worker")
        self._fp_installing = None
        if code == 0:
            self._set_fp_task_state(f"{name or app_id} installed.", "success")
            self._fp_install_log.append("\nDone.")
            self._configure_fp_lifecycle_buttons(app_id, name, btn, open_btn, installed=True)
        else:
            self._set_fp_task_state(f"Install failed (exit {code}).", "error")
            _set_log_panel(self._fp_install_log_toggle, self._fp_install_log, True)
            self._configure_fp_lifecycle_buttons(app_id, name, btn, open_btn, installed=False)

    def _fp_store_uninstall(self, app_id: str, name: str, btn: QPushButton, open_btn: QPushButton | None = None):
        if (self._fp_install_worker and self._fp_install_worker.isRunning()) or \
                (self._fp_uninstall_worker and self._fp_uninstall_worker.isRunning()):
            return
        reply = QMessageBox.question(
            self,
            f"Uninstall {name or app_id}",
            f"Remove {name or app_id}?\n\n{app_id}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        btn.setText("Uninstalling…")
        btn.setEnabled(False)
        self._fp_install_log.clear()
        self._fp_install_log.append(f"→ flatpak uninstall -y {app_id}\n")
        self._fp_install_log_toggle.show()
        _set_log_panel(self._fp_install_log_toggle, self._fp_install_log, False)
        self._fp_progress.show()
        self._set_fp_task_state(f"Uninstalling {name or app_id}…", "running")
        self._fp_uninstall_worker = Worker(["flatpak", "uninstall", "-y", app_id])
        self._fp_uninstall_worker.line.connect(self._on_fp_uninstall_line)
        self._fp_uninstall_worker.done.connect(
            lambda code, aid=app_id, n=name, b=btn, ob=open_btn: self._on_fp_store_uninstall_done(code, aid, n, b, ob)
        )
        self._fp_uninstall_worker.start()

    def _on_fp_uninstall_line(self, ln: str):
        self._fp_install_log.append(ln)
        self._fp_install_log.ensureCursorVisible()

    def _on_fp_store_uninstall_done(self, code: int, app_id: str, name: str, btn: QPushButton, open_btn: QPushButton | None = None):
        self._fp_progress.hide()
        _finish_worker(self, attr="_fp_uninstall_worker")
        if code == 0:
            self._set_fp_task_state(f"{name or app_id} uninstalled.", "success")
            self._fp_install_log.append("\nDone.")
            self._configure_fp_lifecycle_buttons(app_id, name, btn, open_btn, installed=False)
        else:
            self._set_fp_task_state(f"Uninstall failed (exit {code}).", "error")
            _set_log_panel(self._fp_install_log_toggle, self._fp_install_log, True)
            self._configure_fp_lifecycle_buttons(app_id, name, btn, open_btn, installed=True)
