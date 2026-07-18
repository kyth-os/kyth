# __KYTH_GENERATED_IMPORTS__
from ._store_landing import _StoreLandingMixin
from ._search import _SearchMixin
from ._catalog import _CatalogMixin
from ._details import _DetailsMixin
from ._lifecycle import _LifecycleMixin
from ..qt import (  # noqa: E501
    QFrame, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)
from ..widgets import _set_log_panel


class _FlatpakStoreTabMixin(
    _StoreLandingMixin,
    _SearchMixin,
    _CatalogMixin,
    _DetailsMixin,
    _LifecycleMixin,
):
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
