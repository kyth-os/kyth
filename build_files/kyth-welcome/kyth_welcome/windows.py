# __KYTH_GENERATED_IMPORTS__
from .core_base import IS_LIVE, load_profile, restyle
from .services.bootc import current_branch
from .services.runtime import has_blocking_tasks
from .page_registry import (
    PROBLEM_ROUTES, SEARCH_ALIASES, SEARCH_ITEMS, descriptors_from_nav_groups, get_nav_groups,
)
from .qt import (
    QCompleter, QFrame, QHBoxLayout, QKeySequence, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QShortcut, QSize, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget, Qt, single_shot,
)
from .widgets import (
    _divider, _theme_icon,
)
from .services.launch import popen

# ── Sidebar nav button ─────────────────────────────────────────────────────────
def _nav_section_label(text: str) -> QLabel:
    """Create a sidebar section header label (e.g. 'System', 'Apps')."""
    lbl = QLabel(text)
    lbl.setObjectName("nav-section")
    lbl.setContentsMargins(20, 14, 16, 4)
    return lbl


class NavButton(QPushButton):
    def __init__(self, icon_names: tuple[str, ...], glyph: str, label: str):
        icon = _theme_icon(*icon_names)
        if icon.isNull():
            # No matching theme icon installed — fall back to the text glyph.
            super().__init__(f"  {glyph}  {label}")
        else:
            super().__init__(f"  {label}")
            self.setIcon(icon)
            self.setIconSize(QSize(16, 16))
        self.setObjectName("nav-item")
        self.setCheckable(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        sp = self.sizePolicy()
        sp.setHorizontalPolicy(QSizePolicy.Policy.Expanding)
        self.setSizePolicy(sp)
        self.setMinimumHeight(36)

    def set_active(self, active: bool):
        self.setObjectName("nav-item-active" if active else "nav-item")
        restyle(self)


# ── Main window ───────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KythOS")
        self.setMinimumSize(980, 660)
        self.resize(1180, 760)

        # Outer wrapper: live banner (if running from live ISO) + main content
        central = QWidget()
        central.setObjectName("content-area")
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        self.setCentralWidget(central)

        if IS_LIVE:
            banner = QWidget()
            banner.setObjectName("live-banner")
            banner_layout = QHBoxLayout(banner)
            banner_layout.setContentsMargins(16, 9, 16, 9)
            banner_layout.setSpacing(0)

            badge = QLabel("  LIVE SESSION  ")
            badge.setObjectName("live-banner-badge")
            banner_layout.addWidget(badge)
            banner_layout.addSpacing(12)

            notice = QLabel(
                "Connect to Wi-Fi or Ethernet first, then install KythOS or open System Hub for hardware checks."
            )
            notice.setObjectName("live-banner-text")
            banner_layout.addWidget(notice, 1)
            banner_layout.addSpacing(16)

            install_btn = QPushButton("Install KythOS")
            install_btn.setObjectName("primary")
            install_btn.setFixedWidth(148)
            install_btn.clicked.connect(
                lambda: popen(["/usr/bin/kyth-launch-installer"])
            )
            banner_layout.addWidget(install_btn)
            central_layout.addWidget(banner)

        # ── Top command bar: back/forward, breadcrumb, search ────────────────
        topbar = QWidget()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(46)
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(8, 6, 14, 6)
        topbar_layout.setSpacing(4)

        self._back_btn = QPushButton("←")
        self._back_btn.setObjectName("topbar-nav")
        self._back_btn.setFixedSize(36, 30)
        self._back_btn.setToolTip("Back")
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(self._go_back)
        topbar_layout.addWidget(self._back_btn)

        self._fwd_btn = QPushButton("→")
        self._fwd_btn.setObjectName("topbar-nav")
        self._fwd_btn.setFixedSize(36, 30)
        self._fwd_btn.setToolTip("Forward")
        self._fwd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fwd_btn.clicked.connect(self._go_forward)
        topbar_layout.addWidget(self._fwd_btn)

        topbar_layout.addSpacing(8)

        home_crumb = QPushButton("System Hub")
        home_crumb.setObjectName("breadcrumb-link")
        home_crumb.setCursor(Qt.CursorShape.PointingHandCursor)
        home_crumb.clicked.connect(lambda: self._navigate_to("Welcome"))
        topbar_layout.addWidget(home_crumb)

        self._crumb_lbl = QLabel("")
        self._crumb_lbl.setObjectName("breadcrumb")
        topbar_layout.addWidget(self._crumb_lbl)
        topbar_layout.addStretch()

        self._search_box = QLineEdit()
        self._search_box.setObjectName("search-box")
        self._search_box.setPlaceholderText("Find a setting")
        self._search_box.setFixedWidth(280)
        self._search_box.setClearButtonEnabled(True)
        topbar_layout.addWidget(self._search_box)

        central_layout.addWidget(topbar)

        self._search_panel = QFrame()
        self._search_panel.setObjectName("search-results-panel")
        self._search_panel.hide()
        self._search_panel_layout = QVBoxLayout(self._search_panel)
        self._search_panel_layout.setContentsMargins(266, 12, 24, 14)
        self._search_panel_layout.setSpacing(8)

        self._search_results_title = QLabel("Search results")
        self._search_results_title.setObjectName("search-results-title")
        self._search_panel_layout.addWidget(self._search_results_title)

        self._search_results_body = QVBoxLayout()
        self._search_results_body.setSpacing(6)
        self._search_panel_layout.addLayout(self._search_results_body)

        self._search_results_hint = QLabel("")
        self._search_results_hint.setObjectName("search-results-hint")
        self._search_results_hint.setWordWrap(True)
        self._search_panel_layout.addWidget(self._search_results_hint)
        central_layout.addWidget(self._search_panel)

        root = QWidget()
        root.setObjectName("content-area")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        central_layout.addWidget(root, 1)

        # ── Sidebar ──────────────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(244)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Header / branding
        logo_area = QWidget()
        logo_area.setObjectName("sidebar-header")
        logo_layout = QVBoxLayout(logo_area)
        logo_layout.setContentsMargins(20, 22, 20, 18)
        logo_layout.setSpacing(3)

        logo_lbl = QLabel("KythOS")
        logo_lbl.setObjectName("sidebar-logo")
        logo_layout.addWidget(logo_lbl)

        self._sidebar_ver_lbl = QLabel("System Hub")
        self._sidebar_ver_lbl.setObjectName("sidebar-ver")
        logo_layout.addWidget(self._sidebar_ver_lbl)
        single_shot(self, 0, self._refresh_sidebar_channel)
        sidebar_layout.addWidget(logo_area)
        sidebar_layout.addWidget(_divider())

        # Nav groups: (section_label, [(icon_names, glyph, label, key, factory), ...])
        # section_label=None omits the header row (used for Home).
        page_specs: list[tuple[str, object]] = []

        nav_groups = get_nav_groups(self._navigate_to)
        self._page_descriptors = descriptors_from_nav_groups(nav_groups, self._SEARCH_ITEMS)
        self._descriptor_by_key = {descriptor.key: descriptor for descriptor in self._page_descriptors}
        self._nav_buttons: list[NavButton] = []
        self._nav_button_by_key: dict[str, NavButton] = {}
        self._nav_section_labels: dict[str, QLabel] = {}
        self._page_crumbs: list[tuple[str | None, str]] = []
        global_idx = 0
        for section_title, items in nav_groups:
            sidebar_layout.addSpacing(4)
            if section_title is not None:
                section_lbl = _nav_section_label(section_title)
                self._nav_section_labels[section_title] = section_lbl
                sidebar_layout.addWidget(section_lbl)
            for icon_names, glyph, label, key, factory in items:
                page_specs.append((key, factory))
                self._page_crumbs.append((section_title, label))
                btn = NavButton(icon_names, glyph, label)
                btn.clicked.connect(self._make_nav_handler(global_idx))
                sidebar_layout.addWidget(btn)
                self._nav_buttons.append(btn)
                self._nav_button_by_key[key] = btn
                global_idx += 1
            sidebar_layout.addSpacing(2)

        self._page_index_by_key = {
            key: idx for idx, (key, _) in enumerate(page_specs)
        }

        sidebar_layout.addStretch()

        # Bottom version hint
        sidebar_layout.addWidget(_divider())
        ver_hint = QLabel("KythOS System Hub")
        ver_hint.setObjectName("nav-section")
        ver_hint.setContentsMargins(20, 10, 16, 12)
        sidebar_layout.addWidget(ver_hint)

        root_layout.addWidget(sidebar)

        # ── Page stack ───────────────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.setObjectName("content-area")
        self._page_factories = [factory for _, factory in page_specs]
        self._pages: list[QWidget | None] = [None] * len(page_specs)
        for _ in page_specs:
            self._stack.addWidget(QWidget())  # cheap placeholder; replaced on first visit
        root_layout.addWidget(self._stack)

        # Build Welcome page eagerly so its profile_changed signal is available.
        welcome_idx = self._page_index_by_key["Welcome"]
        welcome_page = self._ensure_page(welcome_idx)
        welcome_page.profile_changed.connect(self._apply_profile_visibility)
        self._apply_profile_visibility(load_profile())

        self._history: list[int] = []
        self._history_pos: int = -1
        self._setup_search()
        self._search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self._search_shortcut.activated.connect(self._focus_search)
        self._home_shortcut = QShortcut(QKeySequence("Alt+Home"), self)
        self._home_shortcut.activated.connect(lambda: self._navigate_to("Welcome"))
        self._switch_page(0)

    # ── Search ("Find a setting") ─────────────────────────────────────────────

    # Familiar phrasings mapped to page keys, including migration/search terms
    # people bring with them from another desktop.
    _SEARCH_ITEMS = SEARCH_ITEMS
    _SEARCH_ALIASES = SEARCH_ALIASES
    _PROBLEM_ROUTES = PROBLEM_ROUTES

    def _setup_search(self):
        self._search_key_by_entry: dict[str, str] = {}
        for key, aliases in self._SEARCH_ALIASES.items():
            if key not in self._page_index_by_key:
                continue
            title, _description, extra_terms = self._SEARCH_ITEMS.get(key, (key, "", []))
            for alias in [title, key, *aliases, *extra_terms]:
                self._search_key_by_entry.setdefault(alias, key)

        entries = sorted(self._search_key_by_entry)
        completer = QCompleter(entries, self._search_box)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.activated.connect(self._on_search_pick)
        self._search_box.setCompleter(completer)
        self._search_box.textChanged.connect(self._update_search_results)
        self._search_box.returnPressed.connect(self._on_search_return)

    def _focus_search(self):
        self._search_box.setFocus()
        self._search_box.selectAll()

    def _on_search_pick(self, entry: str):
        key = self._search_key_by_entry.get(entry)
        if key is not None:
            self._navigate_to(key)
        self._search_box.clear()
        self._search_panel.hide()

    def _on_search_return(self):
        text = self._search_box.text().strip()
        if not text:
            return
        matches = self._rank_search_results(text)
        if matches:
            self._navigate_to(matches[0][0])
            self._search_box.clear()
            self._search_panel.hide()

    def _clear_search_results(self):
        while self._search_results_body.count():
            item = self._search_results_body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rank_search_results(self, text: str) -> list[tuple[str, int]]:
        query = text.strip().lower()
        if not query:
            return []
        ranked: list[tuple[str, int]] = []
        for descriptor in self._page_descriptors:
            key = descriptor.key
            if key not in self._page_index_by_key:
                continue
            aliases = self._SEARCH_ALIASES.get(key, [])
            terms = [
                descriptor.key,
                descriptor.title,
                descriptor.search_description,
                *aliases,
                *descriptor.search_terms,
            ]
            score = 0
            for term in terms:
                lower = term.lower()
                if query == lower:
                    score = max(score, 120)
                elif lower.startswith(query):
                    score = max(score, 90)
                elif query in lower:
                    score = max(score, 60)
            haystack = " ".join(terms).lower()
            words = [part for part in query.split() if part]
            if words and all(word in haystack for word in words):
                score = max(score, 45 + len(words))
            for phrase, target_key in self._PROBLEM_ROUTES.items():
                if key == target_key and (query in phrase or phrase in query):
                    score = max(score, 130)
            if score:
                ranked.append((key, score))
        return sorted(ranked, key=lambda item: (-item[1], self._descriptor_by_key[item[0]].title))[:5]

    def _update_search_results(self, text: str):
        self._clear_search_results()
        query = text.strip()
        if not query:
            self._search_panel.hide()
            return

        matches = self._rank_search_results(query)
        self._search_panel.show()
        if not matches:
            self._search_results_title.setText("No matching settings")
            self._search_results_hint.setText(
                "Try a task name like Device Manager, game capture, map network drive, or add or remove programs."
            )
            return

        self._search_results_title.setText("Search results")
        self._search_results_hint.setText("Matched System Hub tools.")
        for key, _score in matches:
            descriptor = self._descriptor_by_key[key]
            title = descriptor.title
            description = descriptor.search_description
            section, label = self._page_crumbs[self._page_index_by_key[key]]
            crumb = label if not section or section == label else f"{section} / {label}"
            btn = QPushButton(f"{title}\n{description}\n{crumb}")
            btn.setObjectName("search-result")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._open_search_result(k))
            self._search_results_body.addWidget(btn)

    def _open_search_result(self, key: str):
        self._navigate_to(key)
        self._search_box.clear()
        self._search_panel.hide()

    # ── Usage focus ────────────────────────────────────────────────────────────

    _GAMING_PAGE_KEYS = ("Gaming", "Performance", "Compatibility", "Controllers")

    def _apply_profile_visibility(self, profile: str):
        """Tailor the sidebar to the Everyday/Gaming focus.

        Hidden pages stay in the stack and reachable through search — the
        focus only de-emphasizes, it never removes.
        """
        gaming_visible = profile == "gaming"
        work_visible = profile != "gaming"
        self._nav_section_labels["Gaming"].setVisible(gaming_visible)
        for key in self._GAMING_PAGE_KEYS:
            self._nav_button_by_key[key].setVisible(gaming_visible)
        self._nav_button_by_key["Work Setup"].setVisible(work_visible)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _refresh_sidebar_channel(self):
        branch = current_branch()
        text = {"latest": "Stable Channel", "testing": "Testing Channel"}.get(branch or "", "System Hub")
        self._sidebar_ver_lbl.setText(text)

    def _ensure_page(self, index: int) -> QWidget:
        if self._pages[index] is None:
            page = self._page_factories[index]()
            self._pages[index] = page
            placeholder = self._stack.widget(index)
            self._stack.insertWidget(index, page)
            self._stack.removeWidget(placeholder)
        return self._pages[index]  # type: ignore[return-value]

    def _make_nav_handler(self, index: int):
        return lambda: self._switch_page(index)

    def _navigate_to(self, destination: int | str):
        if isinstance(destination, str):
            index = self._page_index_by_key.get(destination)
            if index is None:
                return
            self._switch_page(index)
            return
        self._switch_page(destination)

    def _go_back(self):
        if self._history_pos > 0:
            self._history_pos -= 1
            self._switch_page(self._history[self._history_pos], record=False)

    def _go_forward(self):
        if self._history_pos < len(self._history) - 1:
            self._history_pos += 1
            self._switch_page(self._history[self._history_pos], record=False)

    def _switch_page(self, index: int, record: bool = True):
        self._ensure_page(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.set_active(i == index)
        self._stack.setCurrentIndex(index)
        if record:
            del self._history[self._history_pos + 1:]
            if not self._history or self._history[-1] != index:
                self._history.append(index)
            self._history_pos = len(self._history) - 1
        self._update_topbar(index)

    def _update_topbar(self, index: int):
        self._back_btn.setEnabled(self._history_pos > 0)
        self._fwd_btn.setEnabled(self._history_pos < len(self._history) - 1)
        section, label = self._page_crumbs[index]
        if index == 0:
            self._crumb_lbl.setText("")
        elif section and section != label:
            self._crumb_lbl.setText(f"›  {section}  ›  {label}")  # noqa: RUF001 — breadcrumb separator, deliberate typography
        else:
            self._crumb_lbl.setText(f"›  {label}")  # noqa: RUF001 — breadcrumb separator, deliberate typography

    def closeEvent(self, event):
        busy = has_blocking_tasks()
        if busy:
            QMessageBox.warning(
                self,
                "KythOS Is Busy",
                "A task is still running. Please wait for it to finish before closing.",
            )
            event.ignore()
            self.raise_()
            self.activateWindow()
            return
        super().closeEvent(event)


def __getattr__(name: str):
    """Lazy re-export of WizardWindow to avoid import cycles with the hub."""
    if name == "WizardWindow":
        from .wizard import WizardWindow
        return WizardWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
