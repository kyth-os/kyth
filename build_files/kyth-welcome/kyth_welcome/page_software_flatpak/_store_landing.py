# __KYTH_GENERATED_IMPORTS__
from ..qt import (
    QFrame, QHBoxLayout, QIcon, QLabel, QPushButton, QVBoxLayout,
)
from ..services.appstream import load_appstream_catalog
from ..services.runtime import DataWorker, release_worker_when_finished
from ..widgets import _make_card


class _StoreLandingMixin:
    def _fallback_store_names(self) -> dict[str, tuple[str, str]]:
        names: dict[str, tuple[str, str]] = {}
        for pack in self._STARTER_PACKS:
            for app_id, label, _selected_by_default, desc in pack["apps"]:
                names[app_id] = (label, desc)
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
        # Avoid blocking the tab construction on synchronous appstream parse
        if self._fp_appstream_cache is None and not getattr(self, "_fp_catalog_loading", False):
            self._fp_catalog_loading = True
            self._fp_status.setText("Loading catalog…")
            self._fp_status.setObjectName("status-dim")
            self._fp_status.show()
            from ..core_base import restyle
            restyle(self._fp_status)
            # Skeleton placeholder while catalog loads
            placeholder = QLabel("Loading featured apps…")
            placeholder.setObjectName("card-copy")
            self._fp_results_layout.addWidget(placeholder)
            worker = DataWorker("flatpak-appstream", load_appstream_catalog)
            worker.result.connect(lambda _k, cat: self._on_appstream_loaded(cat))
            worker.failed.connect(lambda _k, _e: self._on_appstream_loaded({}))
            # S11: pair every DataWorker with release_worker_when_finished so
            # the thread is tracked and released once done, not leaked past
            # this call's scope.
            release_worker_when_finished(self, "_fp_appstream_worker", worker)
            worker.start()
            # Render trending with fallback names immediately so user sees something
            catalog = {}
        elif self._fp_appstream_cache is None:
            # Catalog still loading — show fallback rendering
            catalog = {}
        else:
            catalog = self._fp_appstream_catalog()
        self._fp_status.setText(
            "Featured Kyth picks. Search or browse the catalog for more."
            if catalog else
            "Featured Kyth picks. Refresh metadata for richer descriptions, icons, and categories."
        )
        self._fp_status.setObjectName("status-dim")
        self._fp_status.show()
        from ..core_base import restyle
        restyle(self._fp_status)

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

    def _on_appstream_loaded(self, catalog: dict):
        self._fp_appstream_cache = catalog
        self._fp_catalog_loading = False
        # Re-render landing with rich names now that catalog is cached. This
        # is a queued signal from a background thread — the page can already
        # be torn down (window closed while the catalog load was in flight)
        # by the time it's delivered, leaving the wrapped Qt widgets deleted.
        try:
            self._render_store_landing()
        except RuntimeError:
            pass

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
