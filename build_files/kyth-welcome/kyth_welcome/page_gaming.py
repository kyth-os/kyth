from typing import ClassVar

# __KYTH_GENERATED_IMPORTS__
from .core_base import apply_install_badge
from .services.diagnostics import command_stdout
from .services.gaming import (
    DataWorker, GameNightManager, _ProtonDbBatchWorker, _collect_gaming_dashboard, _compat_tool_version,
    _gamescope_installed, _gaming_health_items, _gaming_migration_checklist_items,
    _mangohud_installed, _proton_cachyos_version, _vkbasalt_installed
)
from .services.flatpak import _is_flatpak_installed
from .services.workers.windows_migration import WindowsLibraryWorker
from .qt import (
    QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget, Qt, single_shot
)
from .lazy_page import compose_on_first_init
from .widgets import Page, SegmentedTabBar, StatusBadge


def _load_gaming_mixins() -> tuple[type, ...]:
    from .page_gaming_dashboard import _DashboardMixin
    from .page_gaming_setup import _SetupSectionMixin
    from .page_gaming_library import _LibraryMixin
    from .page_gaming_fixes import _FixesMixin
    from .page_gaming_tools import _ToolsMixin
    from .page_gaming_migration import _MigrationMixin
    return (_DashboardMixin, _SetupSectionMixin, _LibraryMixin, _FixesMixin, _ToolsMixin, _MigrationMixin)


# ── Page: Gaming ─────────────────────────────────────────────────────────────
# Mixins load on first construction so opening System Hub does not import tools/
# migration modules until the user navigates here. Every GAMING HUB section has
# its own mixin (page_gaming_setup/library/fixes/tools/migration) plus the "all"
# dashboard view (page_gaming_dashboard); this shell only owns section-switching
# orchestration and the cross-section data-refresh plumbing.
@compose_on_first_init(_load_gaming_mixins)
class GamingPage(Page):
    _SECTION_LABELS: ClassVar[dict[str, str]] = {
        "all": "All",
        "setup": "Setup",
        "library": "Library",
        "migration": "Migration",
        "tuning": "Tuning",
        "fixes": "Fixes",
    }

    def _add(self, widget: QWidget) -> QWidget:
        added = super()._add(widget)
        section = getattr(self, "_active_gaming_section", None)
        if section and widget.isVisible():
            self._gaming_section_widgets.setdefault(section, []).append(widget)
        return added

    def _add_layout(self, layout) -> None:
        wrapper = QWidget()
        wrapper.setObjectName("gaming-section-row")
        wrapper.setLayout(layout)
        self._add(wrapper)

    def _make_section_switcher(self) -> SegmentedTabBar:
        display_labels = {
            "all": "🎮 Dashboard",
            "setup": "⚙️ Setup",
            "library": "📚 My Library",
            "migration": "⇄ Migration",
            "tuning": "⚡ Performance & Tuning",
            "fixes": "🛠️ Fixes",
        }
        items = [(key, display_labels.get(key, label)) for key, label in self._SECTION_LABELS.items()]
        bar = SegmentedTabBar(items, active=self._current_gaming_section, kicker="GAMING HUB:")
        bar.activated.connect(self._switch_gaming_section)
        return bar

    def _switch_gaming_section(self, active: str) -> None:
        self._current_gaming_section = active
        # Build on demand (dashboard/"all" seeds setup for health refresh).
        if active == "all":
            self._ensure_gaming_section("setup")
        else:
            self._ensure_gaming_section(active)
            self._kick_section_refresh(active)

        if self._tab_bar is not None:
            self._tab_bar.set_active(active)

        dashboard_visible = (active == "all")
        for widget in self._dashboard_widgets:
            widget.setVisible(dashboard_visible)

        for section, widgets in self._gaming_section_widgets.items():
            visible = (active != "all" and active == section)
            for widget in widgets:
                widget.setVisible(visible)

    @staticmethod
    def _set_status_badge(badge: StatusBadge, state: str, text: str) -> None:
        badge.set_state(state, text)
        badge.show()

    def __init__(self, wizard_mode: bool = False):
        super().__init__()
        self._wizard_mode = wizard_mode
        self._pc_update_worker = None
        self._win_lib_worker: WindowsLibraryWorker | None = None
        self._win_lib_probed = False
        self._data_workers: dict[str, DataWorker] = {}
        self._dashboard_loaded = False
        self._protondb_worker: _ProtonDbBatchWorker | None = None
        self._last_detected_games: list[dict] = []
        self._gaming_section_widgets: dict[str, list[QWidget]] = {}
        self._tab_bar: SegmentedTabBar | None = None
        self._current_gaming_section = "setup" if wizard_mode else "all"
        self._active_gaming_section = None
        self._scx_status_worker: DataWorker | None = None

        self._page_header(
            "Gaming",
            "Gaming",
            "KythOS ships a full gaming stack — Gamescope, MangoHud, Proton-CachyOS, and more. "
            "Install your preferred launchers below.",
        )

        if not wizard_mode:
            self._tab_bar = self._make_section_switcher()
            self._add(self._tab_bar)
            self._hero_card = self._make_gaming_hero_banner()
            self._hud_grid_widget = self._make_gaming_hud_grid()
            self._dashboard_widgets = [self._hero_card, self._hud_grid_widget]
            self._add(self._hero_card)
            self._add(self._hud_grid_widget)
        else:
            self._dashboard_widgets = []

        # Build section cards on first visit (setup always built for dashboard refresh).
        self._sections_built: set[str] = set()
        self._stretch()
        seed = "setup" if self._current_gaming_section == "all" else self._current_gaming_section
        self._ensure_gaming_section(seed)
        self._switch_gaming_section(self._current_gaming_section)
        self._kick_section_refresh(seed)
        single_shot(self, 80, self._refresh_status)

    def _ensure_gaming_section(self, key: str) -> None:
        """Build widgets for a gaming hub section the first time it is shown."""
        if key == "all":
            # Dashboard only needs setup for background health refresh.
            key = "setup"
        if key in self._sections_built:
            return
        builders = {
            "setup": self._build_setup_section,
            "library": self._build_library_section,
            "fixes": self._build_fixes_section,
            "tuning": self._build_tuning_section,
            "migration": self._build_migration_section,
        }
        builder = builders.get(key)
        if builder is None:
            return
        self._active_gaming_section = key
        builder()
        self._active_gaming_section = None
        self._sections_built.add(key)

    def _build_setup_section(self) -> None:
        self._add(self._make_gaming_ready_panel())
        self._build_xbox_game_bar_card()
        self._build_pc_game_library_card()
        self._build_game_night_card()
        self._build_gaming_health_card()
        self._build_migration_checklist_card()

    def _build_library_section(self) -> None:
        self._build_game_readiness_card()
        self._build_my_games_card()

    def _build_fixes_section(self) -> None:
        self._build_first_failure_playbook_card()
        self._build_fix_my_game_card()

    def _build_tuning_section(self) -> None:
        self._build_gaming_tools_section()

    def _build_migration_section(self) -> None:
        self._build_steam_library_migration_card()
        self._build_save_backup_card()
        self._build_modding_migration_card()

    def _kick_section_refresh(self, key: str) -> None:
        """Start async probes only for sections that are already built."""
        if key in ("setup", "all") and hasattr(self, "_checklist_rows_layout"):
            self._set_rows_loading(self._checklist_rows_layout, "Checking first-week setup items…")
            self._set_rows_loading(
                self._health_rows_layout,
                "Checking launchers, Vulkan, Proton, controllers, and game drives…",
            )
            single_shot(self, 0, self._refresh_gaming_dashboard)
        if key == "fixes" and hasattr(self, "_streaming_rows_layout"):
            self._set_rows_loading(
                self._streaming_rows_layout,
                "Checking Discord, OBS, capture, audio, and camera tools…",
            )
        if key == "migration" and hasattr(self, "_saves_status_lbl"):
            self._saves_status_lbl.setText("Scanning save backup tools…")
        if key == "migration" and hasattr(self, "_drive_combo"):
            self._refresh_ntfs_drives()
        if key == "tuning":
            self._update_profile_builder()

    def _make_health_row(self, status: str, title: str, summary: str) -> QFrame:
        card_name, badge_name, label = {
            "ok":   ("hw-card-ok",   "status-ok",   "Ready"),
            "warn": ("hw-card-warn", "status-warn", "Needs setup"),
            "err":  ("hw-card-err",  "status-err",  "Needs fix"),
            "dim":  ("hw-card-dim",  "status-dim",  "Optional"),
        }.get(status, ("hw-card-dim", "status-dim", "Optional"))

        row = QFrame()
        row.setObjectName(card_name)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("card-subtitle")
        layout.addWidget(title_lbl)

        summary_lbl = QLabel(summary)
        summary_lbl.setObjectName("card-copy")
        summary_lbl.setWordWrap(True)
        layout.addWidget(summary_lbl, 1)

        badge = QLabel(label)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setObjectName(badge_name)
        layout.addWidget(badge)
        return row

    def _clear_rows(self, layout: QVBoxLayout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _set_rows_loading(self, layout: QVBoxLayout, message: str):
        self._clear_rows(layout)
        layout.addWidget(self._make_health_row("dim", "Scanning", message))

    def _start_data_worker(self, key: str, fn):
        current = self._data_workers.get(key)
        if current is not None and current.isRunning():
            return
        worker = DataWorker(key, fn)
        self._data_workers[key] = worker
        worker.result.connect(self._on_data_result)
        worker.failed.connect(self._on_data_failed)
        worker.finished.connect(lambda k=key, w=worker: self._finish_data_worker(k, w))
        worker.start()

    def _finish_data_worker(self, key: str, worker: DataWorker):
        if self._data_workers.get(key) is worker:
            self._data_workers.pop(key, None)
        worker.deleteLater()

    def _on_data_failed(self, key: str, message: str):
        target = {
            "dashboard": self._health_rows_layout,
            "health": self._health_rows_layout,
            "checklist": self._checklist_rows_layout,
            "streaming": getattr(self, "_streaming_rows_layout", None),
        }.get(key)
        if target is not None:
            self._clear_rows(target)
            target.addWidget(self._make_health_row("err", "Scan failed", message))
        if key in ("dashboard", "saves") and hasattr(self, "_saves_status_lbl"):
            self._saves_status_lbl.setText(f"Scan failed: {message}")

    def _on_data_result(self, key: str, data):
        if key == "dashboard":
            self._render_health(data.get("health", []))
            self._render_migration_checklist(data.get("checklist", []))
            self._render_streaming_health(data.get("streaming", []))
            self._render_save_status(data.get("saves"))
            self._render_my_games(data.get("games", []))
            self._update_gaming_hud(data)
            self._dashboard_loaded = True
        elif key == "health":
            self._render_health(data)
        elif key == "checklist":
            self._render_migration_checklist(data)
        elif key == "streaming":
            self._render_streaming_health(data)
        elif key == "saves":
            self._render_save_status(data)
        elif key == "games":
            self._render_my_games(data)

    def _refresh_gaming_dashboard(self):
        self._set_rows_loading(self._health_rows_layout, "Checking launchers, Vulkan, Proton, controllers, and game drives…")
        self._set_rows_loading(self._checklist_rows_layout, "Checking first-week setup items…")
        if hasattr(self, "_streaming_rows_layout"):
            self._set_rows_loading(self._streaming_rows_layout, "Checking Discord, OBS, capture, audio, and camera tools…")
        if hasattr(self, "_my_games_summary_lbl"):
            self._my_games_summary_lbl.setText("Scanning installed game libraries…")
        if hasattr(self, "_saves_status_lbl"):
            self._saves_status_lbl.setText("Scanning save backup tools…")
        self._start_data_worker("dashboard", _collect_gaming_dashboard)

    def _render_health(self, items: list[tuple[str, str, str]]):
        self._clear_rows(self._health_rows_layout)
        for status, title, summary in items:
            self._health_rows_layout.addWidget(self._make_health_row(status, title, summary))

    def _refresh_gaming_health(self):
        self._set_rows_loading(self._health_rows_layout, "Checking launchers, Vulkan, Proton, controllers, and game drives…")
        self._start_data_worker("health", _gaming_health_items)

    def _refresh_migration_checklist(self):
        self._set_rows_loading(self._checklist_rows_layout, "Checking first-week setup items…")
        self._start_data_worker("checklist", _gaming_migration_checklist_items)

    def _render_migration_checklist(self, items: list[tuple[str, str, str]]):
        self._clear_rows(self._checklist_rows_layout)
        for status, title, summary in items:
            self._checklist_rows_layout.addWidget(self._make_health_row(status, title, summary))

    def _refresh_status(self):
        if hasattr(self, "_mh_badge"):
            apply_install_badge(self._mh_badge, _mangohud_installed())
        if hasattr(self, "_gs_badge"):
            apply_install_badge(self._gs_badge, _gamescope_installed())
        if hasattr(self, "_vk_badge"):
            apply_install_badge(self._vk_badge, _vkbasalt_installed())
        if hasattr(self, "_bulk_mh_badge"):
            apply_install_badge(self._bulk_mh_badge, _mangohud_installed())
        if hasattr(self, "_bulk_gs_badge"):
            apply_install_badge(self._bulk_gs_badge, _gamescope_installed())
        if hasattr(self, "_bulk_vk_badge"):
            apply_install_badge(self._bulk_vk_badge, _vkbasalt_installed())
        if hasattr(self, "_scx_badge"):
            self._refresh_scx_status()

        if hasattr(self, "_pc_badge"):
            pc_ver = _proton_cachyos_version()
            apply_install_badge(self._pc_badge, bool(pc_ver), ok_text=pc_ver or "Installed")
            self._pc_version_lbl.setText(
                f"Installed: {pc_ver}" if pc_ver
                else "Proton-CachyOS not found in compatibilitytools.d"
            )

        if hasattr(self, "_ge_badge"):
            ge_ver = _compat_tool_version("GE-Proton")
            apply_install_badge(self._ge_badge, bool(ge_ver), ok_text=ge_ver or "Installed", warn_text="Optional")
            self._ge_version_lbl.setText(
                f"Installed: {ge_ver}" if ge_ver
                else "Not installed. Optional fallback runner; Proton-CachyOS remains the recommended default."
            )

        for refs in getattr(self, "_tool_refs", []):
            installed = _is_flatpak_installed(refs["tool"]["flatpak"])
            refs["install"].setVisible(not installed)
            refs["launch"].setVisible(installed)
            refs["uninstall"].setVisible(installed)

        # Sync Game Night UI states
        gn_active = GameNightManager.is_active()
        self._game_night_start_btn.setEnabled(not gn_active)
        self._game_night_stop_btn.setEnabled(gn_active)
        if gn_active:
            self._set_status_badge(
                self._game_night_status,
                "ok",
                "Game Night Mode is on for up to 4 hours. Sleep is blocked and gaming performance mode is active.",
            )
        else:
            self._set_status_badge(
                self._game_night_status,
                "idle",
                "Game Night Mode ended. Normal desktop behavior restored.",
            )

        if hasattr(self, "_hud_game_night_start_btn"):
            self._hud_game_night_start_btn.setEnabled(not gn_active)
            self._hud_game_night_stop_btn.setEnabled(gn_active)
            if gn_active:
                self._set_status_badge(
                    self._hud_game_night_status,
                    "ok",
                    "Game Night Mode is active.",
                )
            else:
                self._set_status_badge(
                    self._hud_game_night_status,
                    "idle",
                    "Ready.",
                )

    def _refresh_scx_status(self) -> None:
        # `kyth-scx status` shells out — page_performance.py's sibling
        # `kyth-scx list` call had the same construction-time-blocking bug,
        # fixed earlier; this is the matching fix for GamingPage's own
        # call, which fires 80ms after __init__ and again after any tool
        # install/uninstall (see page_gaming_tools_*.py's _refresh_status
        # callers).
        if self._scx_status_worker is not None:
            return
        worker = DataWorker("gaming-scx-status", lambda: command_stdout(["kyth-scx", "status"], timeout=5))
        self._scx_status_worker = worker
        worker.result.connect(lambda _key, scx_status: self._apply_scx_status(scx_status))
        worker.failed.connect(lambda _key, _message: self._apply_scx_status(""))
        worker.finished.connect(lambda: setattr(self, "_scx_status_worker", None))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _apply_scx_status(self, scx_status: str) -> None:
        scx_active = "Service: active" in scx_status
        apply_install_badge(self._scx_badge, scx_active, ok_text="Active", warn_text="Inactive")
        if scx_status:
            configured = "unknown"
            for line in scx_status.splitlines():
                if line.startswith("Configured scheduler:"):
                    configured = line.split(":", 1)[1].strip() or "unknown"
                    break
            self._scx_status_lbl.setText(f"Configured: {configured}")
        else:
            self._scx_status_lbl.setText("sched-ext status unavailable.")
