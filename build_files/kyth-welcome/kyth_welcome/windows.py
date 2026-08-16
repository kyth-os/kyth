# __KYTH_GENERATED_IMPORTS__
from .core_base import IS_LIVE, load_profile, restyle
from .services.bootc import current_branch
from .services.hardware import detect_nvidia_async
from .services.runtime import has_blocking_tasks
from .page_registry import PROBLEM_ROUTES, SEARCH_ITEMS, descriptors_from_nav_groups, get_nav_groups
from .qt import (
    QCompleter, QDialog, QFrame, QHBoxLayout, QKeySequence, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QScrollArea, QShortcut, QSize, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget, Qt, single_shot,
)
from .widgets import (
    _divider, _theme_icon, fade_in,
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
            self.setIconSize(QSize(18, 18))
        self.setObjectName("nav-item")
        self.setCheckable(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        sp = self.sizePolicy()
        sp.setHorizontalPolicy(QSizePolicy.Policy.Expanding)
        self.setSizePolicy(sp)
        self.setMinimumHeight(32)

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

        self._build_topbar(central_layout)
        self._build_mission_bar(central_layout)
        self._build_search_panel(central_layout)

        root = self._create_main_content_root()
        central_layout.addWidget(root, 1)

        self._build_sidebar(root.layout())
        self._build_page_stack(root.layout())

        # Welcome profile wiring was eager — defer to next tick so first
        # frame paints without blocking on WelcomePage construction (see #1 cold-start).
        def _wire_welcome_profile():
            idx = self._page_index_by_key.get("Welcome")
            if idx is None:
                return
            try:
                page = self._ensure_page(idx)
                page.profile_changed.connect(self._apply_profile_visibility)
            except Exception:  # nosec B110 -- best-effort, failure here is non-fatal by design
                pass
            try:
                self._apply_profile_visibility(load_profile())
            except Exception:
                pass

        single_shot(self, 0, _wire_welcome_profile)

        self._history: list[int] = []
        self._history_pos: int = -1
        self._setup_search()
        self._search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self._search_shortcut.activated.connect(self._focus_search)
        self._palette_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self._palette_shortcut.activated.connect(self._show_palette)
        self._mission_worker = None
        single_shot(self, 150, self._refresh_mission_bar)
        self._sidebar_channel_worker = None
        self._home_shortcut = QShortcut(QKeySequence("Alt+Home"), self)
        self._home_shortcut.activated.connect(lambda: self._navigate_to("Welcome"))
        self._switch_page(0)
        single_shot(self, 0, self._refresh_nvidia_nav_visibility)

    def _build_topbar(self, central_layout):
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
        self._search_box.setPlaceholderText("Search settings, apps, features (Ctrl+K)...")
        self._search_box.setToolTip("Search settings, apps, or Windows names (Ctrl+K)")
        self._search_box.setFixedWidth(340)
        self._search_box.setClearButtonEnabled(True)
        topbar_layout.addWidget(self._search_box)

        central_layout.addWidget(topbar)

    def _build_mission_bar(self, central_layout):
        from .windows_panels import build_mission_bar

        return build_mission_bar(self, central_layout)

    def _refresh_mission_bar(self):
        if self._mission_worker is not None:
            return
        from .services.runtime import DataWorker, guard_disposed

        def _gather():
            from .services.bootc import branch_display_name, current_branch, has_rollback_deployment, has_staged_update
            from .services.process import command_stdout

            try:
                branch = branch_display_name(current_branch())
            except Exception:
                branch = "System Hub"
            try:
                staged = has_staged_update()
            except Exception:
                staged = False
            try:
                rollback = has_rollback_deployment()
            except Exception:
                rollback = False
            try:
                portal = command_stdout(["systemctl", "--user", "is-active", "xdg-desktop-portal.service"], timeout=2) or ""
                portal = portal.strip()
            except Exception:
                portal = ""
            return {"branch": branch, "staged": staged, "rollback": rollback, "portal": portal}

        self._mission_worker = DataWorker("mission-bar", _gather)
        self._mission_worker.result.connect(guard_disposed(self._on_mission_bar_ready))
        self._mission_worker.failed.connect(lambda _k, _m: None)
        self._mission_worker.finished.connect(lambda: setattr(self, "_mission_worker", None))
        self._mission_worker.finished.connect(self._mission_worker.deleteLater)
        self._mission_worker.start()

    def _on_mission_bar_ready(self, _key: str, facts: object):
        if not isinstance(facts, dict):
            return
        pills = []
        branch = str(facts.get("branch") or "")
        if branch:
            pills.append(branch)
        if facts.get("staged"):
            pills.append("Update staged — reboot to apply")
        elif facts.get("rollback"):
            pills.append("Rollback available")
        else:
            pills.append("System current")
        portal = str(facts.get("portal") or "")
        if portal == "active":
            pills.append("Portal active")
        elif portal:
            pills.append(f"Portal {portal}")

        for i, pill in enumerate(self._mission_pills):
            if i < len(pills):
                pill.setText(pills[i])
                pill.show()
            else:
                pill.hide()
            restyle(pill)

        # AI hint: surface repair plan summary if available (non-blocking, no glow)
        try:
            from kyth_shared.ai_assist import build_repair_plan

            plan = build_repair_plan()
            summary = str(plan.get("summary", ""))[:80]
            if summary and "healthy" not in summary.lower():
                self._mission_ai_hint.setText(summary)
                self._mission_ai_hint.show()
            else:
                self._mission_ai_hint.hide()
        except Exception:
            self._mission_ai_hint.hide()

    def _show_palette(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Command palette")
        dlg.setModal(True)
        dlg.resize(560, 380)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        hint = QLabel("Type to filter — Enter to open, Esc to close")
        hint.setObjectName("mission-kicker")
        lay.addWidget(hint)

        edit = QLineEdit(dlg)
        edit.setPlaceholderText("Search settings, apps, or Windows name — try hdr, clipboard, fancyzones")
        edit.setObjectName("search-box")
        lay.addWidget(edit)

        lst = QListWidget(dlg)
        lay.addWidget(lst, 1)

        def _refill(text: str):
            lst.clear()
            for key, _score in self._rank_search_results(text or " "):
                desc = self._descriptor_by_key.get(key)
                if not desc:
                    continue
                item = QListWidgetItem(f"{desc.title} — {desc.search_description}")
                item.setData(Qt.ItemDataRole.UserRole, key)
                lst.addItem(item)
            if lst.count():
                lst.setCurrentRow(0)

        def _accept():
            it = lst.currentItem()
            key = it.data(Qt.ItemDataRole.UserRole) if it else None
            if key:
                dlg.accept()
                self._navigate_to(key)
            else:
                txt = edit.text().strip()
                matches = self._rank_search_results(txt)
                if matches:
                    dlg.accept()
                    self._navigate_to(matches[0][0])

        def _key_press(event):
            if event.key() == Qt.Key.Key_Down:
                row = lst.currentRow()
                if row < lst.count() - 1:
                    lst.setCurrentRow(row + 1)
                return True
            elif event.key() == Qt.Key.Key_Up:
                row = lst.currentRow()
                if row > 0:
                    lst.setCurrentRow(row - 1)
                return True
            return False

        edit.keyPressEvent = lambda ev: (edit.keyPressEvent.__self__.keyPressEvent(ev) if not _key_press(ev) else None)
        edit.textChanged.connect(_refill)
        edit.returnPressed.connect(_accept)
        lst.itemActivated.connect(lambda it: (dlg.accept(), self._navigate_to(it.data(Qt.ItemDataRole.UserRole))))
        lst.itemClicked.connect(lambda it: (dlg.accept(), self._navigate_to(it.data(Qt.ItemDataRole.UserRole))))

        _refill("")
        edit.setFocus()
        dlg.exec()

    def _build_search_panel(self, central_layout):
        from .windows_panels import build_search_panel

        return build_search_panel(self, central_layout)

    def _create_main_content_root(self) -> QWidget:
        root = QWidget()
        root.setObjectName("content-area")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        return root

    def _build_sidebar(self, parent_layout):
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(240)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

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

        self._page_specs: list[tuple[str, object]] = []
        self._nav_buttons = []
        self._nav_button_by_key = {}
        self._nav_section_labels = {}
        self._page_crumbs = []

        scroll = QScrollArea()
        scroll.setObjectName("sidebar-scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_content.setObjectName("sidebar-scroll-content")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(0)

        nav_groups = get_nav_groups(self._navigate_to)
        self._initialize_page_specs(nav_groups, scroll_layout)

        self._page_descriptors = descriptors_from_nav_groups(nav_groups, self._SEARCH_ITEMS)
        self._descriptor_by_key = {descriptor.key: descriptor for descriptor in self._page_descriptors}
        self._page_index_by_key = {key: idx for idx, (key, _) in enumerate(self._page_specs)}

        self._nvidia_nav_worker = None
        nvidia_btn = self._nav_button_by_key.get("NVIDIA")
        if nvidia_btn is not None:
            nvidia_btn.setVisible(False)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        sidebar_layout.addWidget(scroll, 1)

        sidebar_layout.addWidget(_divider())
        ver_hint = QLabel("KythOS System Hub")
        ver_hint.setObjectName("nav-section")
        ver_hint.setContentsMargins(20, 10, 16, 12)
        sidebar_layout.addWidget(ver_hint)

        parent_layout.addWidget(sidebar)

    def _initialize_page_specs(self, nav_groups, sidebar_layout):
        global_idx = 0
        for section_title, items in nav_groups:
            sidebar_layout.addSpacing(4)
            if section_title is not None:
                section_lbl = _nav_section_label(section_title)
                self._nav_section_labels[section_title] = section_lbl
                sidebar_layout.addWidget(section_lbl)
            for icon_names, glyph, label, key, factory in items:
                self._page_specs.append((key, factory))
                self._page_crumbs.append((section_title, label))
                btn = NavButton(icon_names, glyph, label)
                btn.clicked.connect(self._make_nav_handler(global_idx))
                sidebar_layout.addWidget(btn)
                self._nav_buttons.append(btn)
                self._nav_button_by_key[key] = btn
                global_idx += 1
            sidebar_layout.addSpacing(2)

    def _build_page_stack(self, parent_layout):
        self._stack = QStackedWidget()
        self._stack.setObjectName("content-area")
        self._page_factories = [factory for _, factory in self._page_specs]
        self._pages = [None] * len(self._page_factories)
        for _ in self._page_factories:
            self._stack.addWidget(QWidget())
        parent_layout.addWidget(self._stack)

    # Familiar phrasings mapped to page keys, including migration/search terms
    # people bring with them from another desktop.
    _SEARCH_ITEMS = SEARCH_ITEMS
    _PROBLEM_ROUTES = PROBLEM_ROUTES

    def _setup_search(self):
        self._search_key_by_entry: dict[str, str] = {}
        for key, item in self._SEARCH_ITEMS.items():
            if key not in self._page_index_by_key:
                continue
            # S10: use typed SearchItem helpers if available, else tuple
            if hasattr(item, "title"):
                title, terms = item.title, tuple(item.terms)
            else:
                title, _description, terms = item  # type: ignore[misc]
                terms = tuple(terms)
            for alias in [title, key, *terms]:
                # S10: normalize alias lower at insert to make rank stable
                norm = alias.strip().lower()
                if norm:
                    self._search_key_by_entry.setdefault(alias, key)
                    self._search_key_by_entry.setdefault(norm, key)

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
            terms = [
                descriptor.key,
                descriptor.title,
                descriptor.search_description,
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
        # W4: stable tie-break — score desc then key asc (not title alpha which drifts with search_terms)
        return sorted(ranked, key=lambda item: (-item[1], item[0]))[:5]

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
        # current_branch() can shell out to `bootc status` on a cold cache
        # (DISK_TTL["bootc-branch"] = 90s) — run it off the UI thread like
        # _refresh_mission_bar, instead of blocking startup on the main thread.
        if self._sidebar_channel_worker is not None:
            return
        from .services.runtime import DataWorker, guard_disposed

        self._sidebar_channel_worker = DataWorker("sidebar-channel", current_branch)
        self._sidebar_channel_worker.result.connect(guard_disposed(self._on_sidebar_channel_ready))
        self._sidebar_channel_worker.failed.connect(lambda _k, _m: None)
        self._sidebar_channel_worker.finished.connect(lambda: setattr(self, "_sidebar_channel_worker", None))
        self._sidebar_channel_worker.finished.connect(self._sidebar_channel_worker.deleteLater)
        self._sidebar_channel_worker.start()

    def _on_sidebar_channel_ready(self, _key: str, branch: object):
        text = {"latest": "Stable Channel", "testing": "Testing Channel"}.get(branch or "", "System Hub")
        self._sidebar_ver_lbl.setText(text)

    def _refresh_nvidia_nav_visibility(self):
        """The NVIDIA nav button starts hidden (see __init__) since
        detecting a GPU means an lspci call. Run it on a background thread
        and reveal the button afterward instead of blocking startup."""
        if "NVIDIA" not in self._nav_button_by_key:
            return
        detect_nvidia_async(self, self._on_nvidia_nav_detected, attr="_nvidia_nav_worker")

    def _on_nvidia_nav_detected(self, has_nvidia: bool):
        if has_nvidia:
            self._nav_button_by_key["NVIDIA"].setVisible(True)

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

    # R3: legacy aliases so old keys (System/Graphics/...) still navigate
    _LEGACY_ALIASES = {
        "System": "Hardware",
        "Graphics": "Performance",
        "Network": "VPN",
        "Software": "App Store",
        "Display": "Plasma Wayland",
        "About": "Feedback",
    }

    def _navigate_to(self, destination: int | str):
        if isinstance(destination, str):
            index = self._page_index_by_key.get(destination)
            if index is None:
                alias = self._LEGACY_ALIASES.get(destination)
                if alias is not None:
                    index = self._page_index_by_key.get(alias)
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
        fade_in(self._stack.currentWidget())
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
