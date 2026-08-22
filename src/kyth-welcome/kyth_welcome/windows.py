# __KYTH_GENERATED_IMPORTS__
from .core_base import IS_LIVE, load_profile, restyle, save_profile
from .services.bootc import current_branch
from .services.hardware import detect_nvidia_async
from .services.runtime import has_blocking_tasks
from .page_registry import (
    PULSE_RAIL,
    PROBLEM_ROUTES,
    SEARCH_ITEMS,
    descriptors_from_nav_groups,
    destination_for_page,
    get_nav_groups,
    landing_for_page,
    section_for_page,
    visible_for_profile,
)
from .qt import (
    QCompleter, QDialog, QHBoxLayout, QKeySequence, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QShortcut, QSize, QStackedWidget, QVBoxLayout, QWidget, Qt, single_shot,
)
from .widgets import (
    _theme_icon, fade_in,
)
from .services.launch import popen

# ── Pulse icon-rail button ─────────────────────────────────────────────────────
class RailButton(QPushButton):
    def __init__(self, icon_names: tuple[str, ...], glyph: str, label: str, hint: str = ""):
        icon = _theme_icon(*icon_names)
        if icon.isNull():
            super().__init__(glyph)
        else:
            super().__init__("")
            self.setIcon(icon)
            self.setIconSize(QSize(22, 22))
        self.setObjectName("pulse-rail-btn")
        self.setCheckable(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(48, 48)
        self.setToolTip(f"{label} — {hint}" if hint else label)
        self.setAccessibleName(label)

    def set_active(self, active: bool):
        if active:
            self.setObjectName("pulse-rail-btn-active")
        elif self.objectName() != "pulse-rail-btn-badge":
            self.setObjectName("pulse-rail-btn")
        restyle(self)


# ── Main window ───────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KythOS")
        self.setMinimumSize(980, 660)
        self.resize(1180, 760)
        self._profile = load_profile()

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
                "Connect to Wi-Fi or Ethernet first, then install KythOS or open Pulse for hardware checks."
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
        self._mission_bar = None
        self._mission_pills = []
        self._mission_guardian_hint = None
        self._mission_ai_hint = None
        self._build_search_panel(central_layout)

        root = self._create_main_content_root()
        central_layout.addWidget(root, 1)

        self._build_sidebar(root.layout())
        self._build_page_stack(root.layout())

        single_shot(self, 0, lambda: self._sync_mode_switch(load_profile()))

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
        # Paint the shell first; Home (and its widget tree) hydrates on the
        # next event-loop tick so showMaximized is not blocked on WelcomePage.
        single_shot(self, 0, lambda: self._switch_page(0, animate=False))
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

        home_crumb = QPushButton("Pulse")
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
        self._search_box.setPlaceholderText("Ask Kyth or jump to a task…")
        self._search_box.setToolTip("Search tasks, apps, or familiar names (Ctrl+K)")
        self._search_box.setFixedWidth(380)
        self._search_box.setClearButtonEnabled(True)
        topbar_layout.addWidget(self._search_box)

        topbar_layout.addSpacing(10)
        self._mode_buttons: dict[str, QPushButton] = {}
        for key, label in (("everyday", "Everyday"), ("gaming", "Gaming")):
            btn = QPushButton(label)
            btn.setObjectName("mode-switch")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip("Everyday lights Apps. Gaming lights Play. Search still finds everything.")
            btn.clicked.connect(lambda _=False, k=key: self._set_profile(k))
            self._mode_buttons[key] = btn
            topbar_layout.addWidget(btn)

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
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                branch = "System Hub"
            try:
                staged = has_staged_update()
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                staged = False
            try:
                rollback = has_rollback_deployment()
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                rollback = False
            try:
                portal = command_stdout(["systemctl", "--user", "is-active", "xdg-desktop-portal.service"], timeout=2) or ""
                portal = portal.strip()
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                portal = ""
            # Guardian: unresolved recommended recipes in the same 6h window as notifications
            guardian = {}
            try:
                from kyth_shared.guardian import pending_recommendations, suppression_reason as _supp

                pending = pending_recommendations()
                guardian["fresh"] = len(pending)
                if pending:
                    guardian["label"] = str(pending[-1].get("recipe_id", ""))
                try:
                    guardian["suppressed"] = _supp()
                except (OSError, ValueError, RuntimeError, AttributeError, KeyError):
                    guardian["suppressed"] = ""
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError, ImportError):
                guardian = {}
            repair_summary = ""
            try:
                from kyth_shared.ai_assist import build_repair_plan

                plan = build_repair_plan()
                repair_summary = str(plan.get("summary", ""))[:80]
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError, ImportError):
                repair_summary = ""
            return {
                "branch": branch,
                "staged": staged,
                "rollback": rollback,
                "portal": portal,
                "guardian": guardian,
                "repair_summary": repair_summary,
            }

        self._mission_worker = DataWorker("mission-bar", _gather)
        self._mission_worker.result.connect(guard_disposed(self._on_mission_bar_ready))
        self._mission_worker.failed.connect(guard_disposed(self._on_mission_bar_failed))
        self._mission_worker.finished.connect(lambda: setattr(self, "_mission_worker", None))
        self._mission_worker.finished.connect(self._mission_worker.deleteLater)
        self._mission_worker.start()

    def _on_mission_bar_failed(self, _key: str, message: str) -> None:
        """Surface probe failures instead of leaving the mission bar blank."""
        import logging

        logging.getLogger(__name__).warning("mission-bar probe failed: %s", message)
        pills = getattr(self, "_mission_pills", None) or []
        if pills:
            pills[0].setText("Status unavailable")
            pills[0].setToolTip(str(message or "Mission bar probe failed")[:200])
            pills[0].show()
            restyle(pills[0])
            for pill in pills[1:]:
                pill.hide()

    def _on_mission_bar_ready(self, _key: str, facts: object):
        if not isinstance(facts, dict):
            return
        # Share staged/rollback with Repair/Update via the Hub control plane.
        try:
            from .services.hub_state import HUB_STATE

            staged = bool(facts.get("staged"))
            rollback = bool(facts.get("rollback"))
            if staged:
                HUB_STATE.set_update_status("staged", "Reboot to apply staged image")
            elif rollback:
                HUB_STATE.set_update_status("idle", "Rollback available")
            else:
                HUB_STATE.set_update_status("idle", "System current")
            HUB_STATE.set_rollback_available(rollback)
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError, ImportError):  # noqa: BLE001
            pass
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
                pill.setToolTip("")
                pill.show()
            else:
                pill.hide()
            restyle(pill)

        # Guardian pill + sidebar badge (phase 2 polish)
        guardian = facts.get("guardian", {}) if isinstance(facts.get("guardian"), dict) else {}
        fresh = int(guardian.get("fresh", 0) or 0)
        suppressed = str(guardian.get("suppressed", "") or "")
        try:
            btn = self._rail_buttons.get("This PC")
            if btn is not None:
                is_active = btn.objectName() == "pulse-rail-btn-active"
                if fresh and not suppressed:
                    if not is_active:
                        btn.setObjectName("pulse-rail-btn-badge")
                    btn.setToolTip(f"{fresh} issue(s) need review in Guardian")
                else:
                    if btn.objectName() == "pulse-rail-btn-badge":
                        btn.setObjectName("pulse-rail-btn")
                    if fresh and suppressed:
                        btn.setToolTip(f"Guardian paused — {suppressed}")
                    else:
                        btn.setToolTip("This PC — Health, updates, and hardware")
                restyle(btn)
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001
            pass

        try:
            hint = getattr(self, "_mission_guardian_hint", None)
            if hint is not None:
                # wire click once
                if not getattr(hint, "_guardian_wired", False):
                    hint.clicked.connect(lambda _=False: self._navigate_to("Guardian"))
                    hint._guardian_wired = True  # type: ignore[attr-defined]
                if fresh and not suppressed:
                    label = str(guardian.get("label", "") or "").strip()
                    count_txt = f"{fresh} need review" if fresh > 1 else "needs review"
                    hint.setText(f"⬢ Guardian — {label} {count_txt}".strip() if label else f"⬢ Guardian — {count_txt}")
                    hint.setToolTip("Open Guardian for fresh recommendations")
                    hint.show()
                elif suppressed and fresh:
                    hint.setText(f"⬢ Guardian paused — {suppressed}")
                    hint.setToolTip("Guardian will resume automatically")
                    hint.show()
                else:
                    hint.hide()
                restyle(hint)
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001
            pass

        # AI hint: surface repair plan summary gathered off-thread
        try:
            hint = getattr(self, "_mission_ai_hint", None)
            if hint is None:
                return
            summary = str(facts.get("repair_summary") or "")[:80]
            if summary and "healthy" not in summary.lower():
                hint.setText(summary)
                hint.show()
            else:
                hint.hide()
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            hint = getattr(self, "_mission_ai_hint", None)
            if hint is not None:
                hint.hide()

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

        lst = QListWidget(dlg)

        class _PaletteSearch(QLineEdit):
            """Arrow keys move the result list; other keys keep normal line-edit behavior.

            Replaces a brittle instance monkey-patch that called
            ``edit.keyPressEvent.__self__`` after reassignment and raised
            AttributeError on every non-arrow keystroke.
            """

            def keyPressEvent(self, event):  # type: ignore[override]
                if event.key() == Qt.Key.Key_Down:
                    row = lst.currentRow()
                    if row < lst.count() - 1:
                        lst.setCurrentRow(row + 1)
                    return
                if event.key() == Qt.Key.Key_Up:
                    row = lst.currentRow()
                    if row > 0:
                        lst.setCurrentRow(row - 1)
                    return
                super().keyPressEvent(event)

        edit = _PaletteSearch(dlg)
        edit.setPlaceholderText("Search tasks, apps, or a familiar name — try hdr, clipboard, fancyzones")
        edit.setObjectName("search-box")
        lay.addWidget(edit)
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
        rail = QWidget()
        rail.setObjectName("pulse-rail")
        rail.setFixedWidth(72)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(0, 12, 0, 12)
        rail_layout.setSpacing(6)

        self._rail_logo = QLabel("K")
        self._rail_logo.setObjectName("pulse-rail-logo")
        self._rail_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._rail_logo.setToolTip("Kyth Pulse")
        rail_layout.addWidget(self._rail_logo)
        rail_layout.addSpacing(8)

        self._page_specs: list[tuple[str, object]] = []
        self._nav_buttons = []
        self._nav_button_by_key = {}
        self._nav_section_labels = {}
        self._rail_buttons: dict[str, RailButton] = {}
        self._page_crumbs = []
        self._sidebar_ver_lbl = self._rail_logo
        single_shot(self, 0, self._refresh_sidebar_channel)

        nav_groups = get_nav_groups(self._navigate_to)
        self._initialize_page_specs(nav_groups)

        self._page_descriptors = descriptors_from_nav_groups(nav_groups, self._SEARCH_ITEMS)
        self._descriptor_by_key = {descriptor.key: descriptor for descriptor in self._page_descriptors}
        self._page_index_by_key = {key: idx for idx, (key, _) in enumerate(self._page_specs)}

        for item in PULSE_RAIL:
            btn = RailButton(item.icon_names, item.glyph, item.title, item.hint)
            btn.clicked.connect(lambda _=False, key=item.landing_key: self._navigate_to(key))
            rail_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self._nav_buttons.append(btn)
            self._rail_buttons[item.dest] = btn
            self._nav_button_by_key[item.landing_key] = btn

        self._nvidia_nav_worker = None
        rail_layout.addStretch()
        parent_layout.addWidget(rail)

    def _initialize_page_specs(self, nav_groups):
        for section_title, items in nav_groups:
            for _icon_names, _glyph, label, key, factory in items:
                self._page_specs.append((key, factory))
                self._page_crumbs.append((section_title, label))

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
            self._search_results_title.setText("No matching tasks")
            self._search_results_hint.setText(
                "Try a task name like Device Manager, game capture, map network drive, or add or remove programs."
            )
            return

        self._search_results_title.setText("Search results")
        self._search_results_hint.setText("Open in Pulse.")
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

    def _set_profile(self, profile: str) -> None:
        save_profile(profile)
        self._sync_mode_switch(profile)
        self._apply_profile_visibility(profile)
        idx = self._page_index_by_key.get("Welcome")
        page = self._pages[idx] if idx is not None else None
        if page is not None and hasattr(page, "set_profile"):
            page.set_profile(profile)
        for constructed in self._pages:
            if constructed is not None and hasattr(constructed, "apply_profile"):
                constructed.apply_profile(profile)

    def _sync_mode_switch(self, profile: str) -> None:
        mode = "gaming" if profile == "gaming" else "everyday"
        for key, btn in self._mode_buttons.items():
            active = key == mode
            btn.setChecked(active)
            btn.setObjectName("mode-switch-active" if active else "mode-switch")
            restyle(btn)

    def _apply_profile_visibility(self, profile: str):
        """Mode changes prominence, not availability. The rail stays at five."""
        self._profile = profile
        for key, btn in self._nav_button_by_key.items():
            desc = self._descriptor_by_key.get(key)
            if desc is None:
                continue
            # Rail destinations stay visible; leftover mapped buttons honor profile.
            if key in {item.landing_key for item in PULSE_RAIL}:
                btn.setVisible(True)
                continue
            btn.setVisible(visible_for_profile(desc, profile))

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
        self._sidebar_channel_worker.failed.connect(guard_disposed(self._on_sidebar_channel_failed))
        self._sidebar_channel_worker.finished.connect(lambda: setattr(self, "_sidebar_channel_worker", None))
        self._sidebar_channel_worker.finished.connect(self._sidebar_channel_worker.deleteLater)
        self._sidebar_channel_worker.start()

    def _on_sidebar_channel_ready(self, _key: str, branch: object):
        text = {"latest": "Stable channel", "testing": "Testing channel"}.get(branch or "", "System Hub")
        self._sidebar_ver_lbl.setToolTip(f"KythOS · {text}")

    def _on_sidebar_channel_failed(self, _key: str, message: str) -> None:
        import logging

        logging.getLogger(__name__).warning("sidebar channel probe failed: %s", message)
        self._sidebar_ver_lbl.setToolTip(str(message or "Could not read update channel")[:200])

    def _refresh_nvidia_nav_visibility(self):
        """NVIDIA is search- and This PC-only now. Keep the probe so pages
        that still listen for the worker attr do not see a missing start."""
        if getattr(self, "_nvidia_nav_worker", None) is not None:
            return
        detect_nvidia_async(self, self._on_nvidia_nav_detected, attr="_nvidia_nav_worker")

    def _on_nvidia_nav_detected(self, has_nvidia: bool):
        self._has_nvidia = bool(has_nvidia)

    def _ensure_page(self, index: int) -> QWidget:
        if self._pages[index] is None:
            page = self._page_factories[index]()
            self._pages[index] = page
            placeholder = self._stack.widget(index)
            self._stack.insertWidget(index, page)
            self._stack.removeWidget(placeholder)
            if hasattr(page, "apply_profile"):
                page.apply_profile(getattr(self, "_profile", "everyday"))
        return self._pages[index]  # type: ignore[return-value]

    def _make_nav_handler(self, index: int):
        return lambda: self._switch_page(index)

    # R3: legacy aliases so old keys (System/Graphics/...) still navigate
    _LEGACY_ALIASES = {
        "System": "Hardware",
        "Graphics": "Performance",
        "Network": "VPN",
        "Software": "App Store",
        "Updates": "Update",
        "Display": "Plasma Wayland",
        "About": "Feedback",
    }

    def _navigate_to(self, destination: int | str):
        if isinstance(destination, int):
            self._switch_page(destination)
            return
        key = destination
        index = self._page_index_by_key.get(key)
        if index is None:
            alias = self._LEGACY_ALIASES.get(key)
            if alias is not None:
                key = alias
                index = self._page_index_by_key.get(key)
        if index is None:
            return
        section = section_for_page(key)
        if section:
            landing = landing_for_page(key)
            landing_index = self._page_index_by_key.get(landing, index)
            self._switch_page(landing_index)
            page = self._pages[landing_index]
            if page is not None and hasattr(page, "show_section"):
                page.show_section(section)
            self._update_topbar(landing_index)
            return
        self._switch_page(index)
        page = self._pages[index]
        if page is not None and hasattr(page, "show_section"):
            page.show_section("overview")
            self._update_topbar(index)

    def _go_back(self):
        if self._history_pos > 0:
            self._history_pos -= 1
            self._switch_page(self._history[self._history_pos], record=False)

    def _go_forward(self):
        if self._history_pos < len(self._history) - 1:
            self._history_pos += 1
            self._switch_page(self._history[self._history_pos], record=False)

    def _switch_page(self, index: int, record: bool = True, animate: bool = True):
        self._ensure_page(index)
        key = self._page_specs[index][0] if 0 <= index < len(self._page_specs) else "Welcome"
        dest = destination_for_page(key)
        for rail_dest, btn in self._rail_buttons.items():
            btn.set_active(rail_dest == dest)
        self._stack.setCurrentIndex(index)
        if animate and record:
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
        if index == 0:
            self._crumb_lbl.setText("")
            return
        key = self._page_specs[index][0] if 0 <= index < len(self._page_specs) else "Welcome"
        dest = destination_for_page(key)
        page = self._pages[index] if 0 <= index < len(self._pages) else None
        section_key = ""
        if page is not None and hasattr(page, "current_section"):
            section_key = str(page.current_section() or "")
        if section_key and section_key != "overview":
            child_idx = self._page_index_by_key.get(section_key)
            child_label = self._page_crumbs[child_idx][1] if child_idx is not None else section_key
            self._crumb_lbl.setText(f"›  {dest}  ›  {child_label}")  # noqa: RUF001 — breadcrumb separator, deliberate typography
            return
        _section, label = self._page_crumbs[index]
        if dest and dest != "Pulse" and dest != label:
            self._crumb_lbl.setText(f"›  {dest}  ›  {label}")  # noqa: RUF001 — breadcrumb separator, deliberate typography
            return
        if _section and _section != label:
            self._crumb_lbl.setText(f"›  {_section}  ›  {label}")  # noqa: RUF001 — breadcrumb separator, deliberate typography
            return
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
