import glob
import os
import shutil

# __KYTH_GENERATED_IMPORTS__
from .core_base import _apply_install_badge, _restyle
from .services.diagnostics import _command_stdout
from .services.gaming import (  # noqa: E501
    DataWorker, GameNightManager, _ProtonDbBatchWorker, _collect_gaming_dashboard, _compat_tool_version,
    _find_ntfs_drives, _gamescope_installed, _gaming_health_items, _gaming_migration_checklist_items,
    _mangohud_installed, _proton_cachyos_version, _vkbasalt_installed
)
from .services.launch import flatpak_run, popen
from .services.software import _install_flatpak_inline, _is_flatpak_installed
from .services.workers.windows_migration import WindowsLibraryWorker
from .qt import (  # noqa: E501
    QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTimer, QVBoxLayout, QWidget, Qt
)
from .lazy_page import compose_on_first_init
from .widgets import ActionRow, Page, StatusBadge, _make_card


def _load_gaming_mixins() -> tuple[type, ...]:
    from .page_gaming_library import _LibraryMixin
    from .page_gaming_fixes import _FixesMixin
    from .page_gaming_tools import _ToolsMixin
    from .page_gaming_migration import _MigrationMixin
    return (_LibraryMixin, _FixesMixin, _ToolsMixin, _MigrationMixin)


# ── Page: Gaming ─────────────────────────────────────────────────────────────
# Mixins load on first construction so opening System Hub does not import tools/
# migration modules until the user navigates here.
@compose_on_first_init(_load_gaming_mixins)
class GamingPage(Page):
    _SECTION_LABELS = {
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

    def _make_section_switcher(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("genz-focus-row")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        lbl = QLabel("GAMING HUB:")
        lbl.setObjectName("home-kicker")
        layout.addWidget(lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        display_labels = {
            "all": "🎮 Dashboard",
            "setup": "⚙️ Setup",
            "library": "📚 My Library",
            "migration": "⇄ Migration",
            "tuning": "⚡ Performance & Tuning",
            "fixes": "🛠️ Fixes",
        }

        for key, label in self._SECTION_LABELS.items():
            display_label = display_labels.get(key, label)
            btn = QPushButton(display_label)
            btn.setObjectName("genz-mode-btn")
            btn.setCheckable(True)
            btn.setChecked(key == self._current_gaming_section)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._switch_gaming_section(k))
            self._gaming_section_buttons[key] = btn
            layout.addWidget(btn)
        layout.addStretch()
        return bar

    def _switch_gaming_section(self, active: str) -> None:
        self._current_gaming_section = active
        # Build on demand (dashboard/"all" seeds setup for health refresh).
        if active == "all":
            self._ensure_gaming_section("setup")
        else:
            self._ensure_gaming_section(active)
            self._kick_section_refresh(active)

        for key, btn in self._gaming_section_buttons.items():
            selected = key == active
            btn.setChecked(selected)
            btn.setObjectName("genz-mode-btn")
            _restyle(btn)

        dashboard_visible = (active == "all")
        for widget in self._dashboard_widgets:
            widget.setVisible(dashboard_visible)

        for section, widgets in self._gaming_section_widgets.items():
            visible = (active != "all" and active == section)
            for widget in widgets:
                widget.setVisible(visible)

    def _make_gaming_hero_banner(self) -> QFrame:
        hero_card = QFrame()
        hero_card.setObjectName("genz-hero")
        hero_layout = QHBoxLayout(hero_card)
        hero_layout.setContentsMargins(24, 20, 24, 20)
        hero_layout.setSpacing(16)

        hero_text_col = QVBoxLayout()
        hero_text_col.setSpacing(4)
        
        hero_title = QLabel("KYTHOS GAMING PLATFORM")
        hero_title.setObjectName("genz-hero-title")
        hero_text_col.addWidget(hero_title)

        hero_sub = QLabel("Curated launchers, Gamescope compositing, MangoHud overlay, and performance-tuned Proton runners.")
        hero_sub.setObjectName("genz-hero-subtitle")
        hero_text_col.addWidget(hero_sub)
        hero_layout.addLayout(hero_text_col, 1)

        self._hero_status_pill = QLabel("CHECKING STACK...")
        self._hero_status_pill.setObjectName("glowing-pill-ok")
        hero_layout.addWidget(self._hero_status_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        return hero_card

    def _make_gaming_hud_grid(self) -> QWidget:
        widget = QWidget()
        hud_grid = QGridLayout(widget)
        hud_grid.setContentsMargins(0, 0, 0, 0)
        hud_grid.setSpacing(12)

        # Card 1: Launchers
        card1 = QFrame()
        card1.setObjectName("genz-hud-card")
        layout1 = QVBoxLayout(card1)
        layout1.setContentsMargins(18, 16, 18, 16)
        layout1.setSpacing(8)
        title1 = QLabel("LAUNCHERS")
        title1.setObjectName("hud-title")
        layout1.addWidget(title1)
        self._hud_runners_desc = QLabel("Checking Flatpaks...")
        self._hud_runners_desc.setTextFormat(Qt.TextFormat.RichText)
        self._hud_runners_desc.setObjectName("hud-desc")
        self._hud_runners_desc.setWordWrap(True)
        layout1.addWidget(self._hud_runners_desc)
        hud_grid.addWidget(card1, 0, 0)

        # Card 2: Runtime Engine
        card2 = QFrame()
        card2.setObjectName("genz-hud-card")
        layout2 = QVBoxLayout(card2)
        layout2.setContentsMargins(18, 16, 18, 16)
        layout2.setSpacing(8)
        title2 = QLabel("RUNTIME ENGINE")
        title2.setObjectName("hud-title")
        layout2.addWidget(title2)
        self._hud_runtime_desc = QLabel("Checking runners & overlays...")
        self._hud_runtime_desc.setTextFormat(Qt.TextFormat.RichText)
        self._hud_runtime_desc.setObjectName("hud-desc")
        self._hud_runtime_desc.setWordWrap(True)
        layout2.addWidget(self._hud_runtime_desc)
        hud_grid.addWidget(card2, 0, 1)

        # Card 3: Storage & Saves
        card3 = QFrame()
        card3.setObjectName("genz-hud-card")
        layout3 = QVBoxLayout(card3)
        layout3.setContentsMargins(18, 16, 18, 16)
        layout3.setSpacing(8)
        title3 = QLabel("STORAGE & SAVES")
        title3.setObjectName("hud-title")
        layout3.addWidget(title3)
        self._hud_storage_desc = QLabel("Checking backups & drives...")
        self._hud_storage_desc.setTextFormat(Qt.TextFormat.RichText)
        self._hud_storage_desc.setObjectName("hud-desc")
        self._hud_storage_desc.setWordWrap(True)
        layout3.addWidget(self._hud_storage_desc)
        hud_grid.addWidget(card3, 1, 0)

        # Card 4: Quick Performance
        card4 = QFrame()
        card4.setObjectName("genz-hud-card")
        layout4 = QVBoxLayout(card4)
        layout4.setContentsMargins(18, 16, 18, 16)
        layout4.setSpacing(8)
        title4 = QLabel("QUICK PERFORMANCE")
        title4.setObjectName("hud-title")
        layout4.addWidget(title4)

        # Game Night Buttons
        gn_row = QHBoxLayout()
        gn_row.setSpacing(6)
        self._hud_game_night_start_btn = QPushButton("Start Game Night")
        self._hud_game_night_start_btn.setObjectName("primary")
        self._hud_game_night_start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hud_game_night_start_btn.clicked.connect(self._start_game_night)
        
        self._hud_game_night_stop_btn = QPushButton("End Game Night")
        self._hud_game_night_stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hud_game_night_stop_btn.clicked.connect(self._stop_game_night)
        self._hud_game_night_stop_btn.setEnabled(False)
        
        gn_row.addWidget(self._hud_game_night_start_btn)
        gn_row.addWidget(self._hud_game_night_stop_btn)
        layout4.addLayout(gn_row)

        self._hud_game_night_status = StatusBadge("Ready to tune.", "idle")
        layout4.addWidget(self._hud_game_night_status)

        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        scan_btn = QPushButton("Scan Libraries")
        scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        scan_btn.clicked.connect(lambda _=False: self._refresh_my_games(async_scan=True))
        
        fixes_btn = QPushButton("Troubleshoot")
        fixes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fixes_btn.clicked.connect(lambda _=False: self._switch_gaming_section("fixes"))
        
        action_row.addWidget(scan_btn)
        action_row.addWidget(fixes_btn)
        layout4.addLayout(action_row)

        hud_grid.addWidget(card4, 1, 1)
        return widget

    def _update_gaming_hud(self, data: dict) -> None:
        if not hasattr(self, "_hud_runners_desc"):
            return
        
        # Determine Hero status pill
        any_err = False
        health_items = data.get("health", [])
        for status, _, _ in health_items:
            if status == "err":
                any_err = True
                break
        
        if any_err:
            self._hero_status_pill.setText("ATTENTION REQUIRED")
            self._hero_status_pill.setObjectName("glowing-pill-warn")
        else:
            self._hero_status_pill.setText("GAMING STACK READY")
            self._hero_status_pill.setObjectName("glowing-pill-ok")
        _restyle(self._hero_status_pill)

        # 1. Launchers
        steam_ok = _is_flatpak_installed("com.valvesoftware.Steam")
        heroic_ok = _is_flatpak_installed("com.heroicgameslauncher.hgl")
        lutris_ok = _is_flatpak_installed("net.lutris.Lutris")
        bottles_ok = _is_flatpak_installed("com.usebottles.bottles")
        
        steam_status = "🟢 Installed" if steam_ok else "🔴 Missing"
        heroic_status = "🟢 Installed" if heroic_ok else "⚪ Optional"
        lutris_status = "🟢 Installed" if lutris_ok else "⚪ Optional"
        bottles_status = "🟢 Installed" if bottles_ok else "⚪ Optional"
        
        self._hud_runners_desc.setText(
            f"<b>Steam:</b> {steam_status}<br>"
            f"<b>Heroic Games Launcher:</b> {heroic_status}<br>"
            f"<b>Lutris:</b> {lutris_status}<br>"
            f"<b>Bottles:</b> {bottles_status}"
        )

        # 2. Runtime Engine
        pc_ver = _proton_cachyos_version() or "None"
        mangohud = "🟢 Active" if _mangohud_installed() else "🔴 Missing"
        vkbasalt = "🟢 Active" if _vkbasalt_installed() else "⚪ Optional"
        gamescope = "🟢 Active" if _gamescope_installed() else "🔴 Missing"

        self._hud_runtime_desc.setText(
            f"<b>Proton-CachyOS:</b> {pc_ver}<br>"
            f"<b>Gamescope compositor:</b> {gamescope}<br>"
            f"<b>MangoHud overlay:</b> {mangohud}<br>"
            f"<b>vkBasalt post-processing:</b> {vkbasalt}"
        )

        # 3. Storage & Saves
        saves_info = data.get("saves")
        saves_details = saves_info[2] if (saves_info and len(saves_info) >= 3) else "Install Ludusavi for backup diagnostics."
        if "backup/config path found:" in saves_details:
            saves_details = "Ludusavi installed & backups verified."
        elif "run a backup" in saves_details:
            saves_details = "Ludusavi installed; no backups made yet."
            
        windows_drives = _find_ntfs_drives()
        ntfs_count = sum(not d.get("is_bitlocker") for d in windows_drives)
        bitlocker_count = sum(bool(d.get("is_bitlocker")) for d in windows_drives)
        
        if windows_drives:
            drive_desc = f"⚠️ {ntfs_count} NTFS drive(s)"
            if bitlocker_count:
                drive_desc += f", {bitlocker_count} BitLocker locked"
            drive_desc += " found (migration ready)"
        else:
            drive_desc = "🟢 Storage optimized for Linux"

        self._hud_storage_desc.setText(
            f"<b>Game Save Backups:</b> {saves_details}<br>"
            f"<b>PC Game Drives:</b> {drive_desc}"
        )

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
        self._gaming_section_buttons: dict[str, QPushButton] = {}
        self._current_gaming_section = "setup" if wizard_mode else "all"
        self._active_gaming_section = None

        self._page_header(
            "Gaming",
            "Gaming",
            "KythOS ships a full gaming stack — Gamescope, MangoHud, Proton-CachyOS, and more. "
            "Install your preferred launchers below.",
        )

        if not wizard_mode:
            self._add(self._make_section_switcher())
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
        QTimer.singleShot(80, self._refresh_status)
        self._refresh_ntfs_drives()

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
            QTimer.singleShot(0, self._refresh_gaming_dashboard)
        if key == "fixes" and hasattr(self, "_streaming_rows_layout"):
            self._set_rows_loading(
                self._streaming_rows_layout,
                "Checking Discord, OBS, capture, audio, and camera tools…",
            )
        if key == "migration" and hasattr(self, "_saves_status_lbl"):
            self._saves_status_lbl.setText("Scanning save backup tools…")
        if key == "tuning":
            self._update_profile_builder()

    def _build_xbox_game_bar_card(self):
        # ── Xbox Game Bar parity ─────────────────────────────────────────────
        game_bar_card, game_bar_layout = _make_card("card-accent-ok")
        game_bar_title = QLabel("Xbox Game Bar → GPU Screen Recorder")
        game_bar_title.setObjectName("card-title")
        game_bar_layout.addWidget(game_bar_title)
        game_bar_body = QLabel(
            "Record gameplay, keep an instant-replay buffer, capture screenshots, and "
            "use AMD, Intel, or NVIDIA hardware encoding with very little performance "
            "impact. The fullscreen overlay opens with Left Alt+Z after it is enabled "
            "inside GPU Screen Recorder."
        )
        game_bar_body.setObjectName("card-copy")
        game_bar_body.setWordWrap(True)
        game_bar_layout.addWidget(game_bar_body)
        game_bar_actions = ActionRow("Ready to configure capture.", "idle")
        self._game_bar_btn = game_bar_actions.add_button(
            "", self._open_or_install_game_bar, primary=True
        )
        game_bar_actions.finish()
        self._game_bar_status = game_bar_actions.status
        game_bar_layout.addWidget(game_bar_actions)
        self._refresh_game_bar_btn()
        self._add(game_bar_card)

    def _build_pc_game_library_card(self):
        # ── PC Game Library ──────────────────────────────────────────────
        self._win_lib_card, self._win_lib_layout = _make_card("card-accent-ok")
        self._win_lib_card.hide()
        self._add(self._win_lib_card)
        self._divider()

    def _build_game_night_card(self):
        # ── Game Night Mode ──────────────────────────────────────────────────
        night_card, night_layout = _make_card("card-accent-ok")
        night_title = QLabel("Game Night Mode")
        night_title.setObjectName("card-title")
        night_layout.addWidget(night_title)
        night_body = QLabel(
            "One click for a calm play session: prevent sleep, apply KythOS gaming "
            "performance mode, keep the desktop quiet, and launch the apps players usually need."
        )
        night_body.setObjectName("card-copy")
        night_body.setWordWrap(True)
        night_layout.addWidget(night_body)
        night_actions = ActionRow("Ready when you are.", "idle")
        self._game_night_start_btn = night_actions.add_button(
            "Start Game Night", self._start_game_night, primary=True
        )
        self._game_night_stop_btn = night_actions.add_button("End Game Night", self._stop_game_night)
        self._game_night_stop_btn.setEnabled(False)
        for label, cmd in (
            ("Open Steam", ["flatpak", "run", "com.valvesoftware.Steam"]),
            ("Open Discord", ["flatpak", "run", "com.discordapp.Discord"]),
            ("Open OBS", ["flatpak", "run", "com.obsproject.Studio"]),
        ):
            night_actions.add_button(label, lambda _=False, c=cmd: popen(c))
        night_actions.finish()
        self._game_night_status = night_actions.status
        night_layout.addWidget(night_actions)
        self._game_night_inhibit = None
        self._add(night_card)

    def _build_gaming_health_card(self):
        # ── Gaming Health Check ──────────────────────────────────────────────
        health_card, health_layout = _make_card()
        health_top = QHBoxLayout()
        health_title = QLabel("Gaming Health Check")
        health_title.setObjectName("card-title")
        health_top.addWidget(health_title)
        health_top.addStretch()
        health_refresh = QPushButton("Refresh")
        health_refresh.clicked.connect(self._refresh_gaming_dashboard)
        health_top.addWidget(health_refresh)
        health_layout.addLayout(health_top)
        health_desc = QLabel(
            "Fast checks for the pieces that make PC games feel plug-and-play: "
            "Steam, Proton runners, Vulkan, NTSYNC, launchers, overlays, controllers, "
            "PC game drives, and staged OS updates."
        )
        health_desc.setObjectName("card-copy")
        health_desc.setWordWrap(True)
        health_layout.addWidget(health_desc)
        self._health_rows_layout = QVBoxLayout()
        self._health_rows_layout.setSpacing(8)
        health_layout.addLayout(self._health_rows_layout)
        self._add(health_card)

    def _build_migration_checklist_card(self):
        # ── PC gamer migration checklist ───────────────────────────────
        checklist_card, checklist_layout = _make_card("card-accent-ok")
        checklist_top = QHBoxLayout()
        checklist_title = QLabel("PC Game Migration Checklist")
        checklist_title.setObjectName("card-title")
        checklist_top.addWidget(checklist_title)
        checklist_top.addStretch()
        checklist_refresh = QPushButton("Refresh")
        checklist_refresh.clicked.connect(self._refresh_gaming_dashboard)
        checklist_top.addWidget(checklist_refresh)
        checklist_layout.addLayout(checklist_top)
        checklist_desc = QLabel(
            "A retention checklist for the first week: launchers, Proton, saves, "
            "controllers, streaming tools, and known blocked games."
        )
        checklist_desc.setObjectName("card-copy")
        checklist_desc.setWordWrap(True)
        checklist_layout.addWidget(checklist_desc)
        self._checklist_rows_layout = QVBoxLayout()
        self._checklist_rows_layout.setSpacing(8)
        checklist_layout.addLayout(self._checklist_rows_layout)
        self._add(checklist_card)

    def _start_game_night(self):
        if not GameNightManager.start():
            return
        self._game_night_start_btn.setEnabled(False)
        self._game_night_stop_btn.setEnabled(True)
        self._set_status_badge(
            self._game_night_status,
            "ok",
            "Game Night Mode is on for up to 4 hours. Sleep is blocked and gaming performance mode is active.",
        )
        if hasattr(self, "_hud_game_night_start_btn"):
            self._hud_game_night_start_btn.setEnabled(False)
            self._hud_game_night_stop_btn.setEnabled(True)
            self._set_status_badge(
                self._hud_game_night_status,
                "ok",
                "Game Night Mode is active.",
            )

    def _stop_game_night(self):
        GameNightManager.stop()
        self._game_night_start_btn.setEnabled(True)
        self._game_night_stop_btn.setEnabled(False)
        self._set_status_badge(
            self._game_night_status,
            "idle",
            "Game Night Mode ended. Normal desktop behavior restored.",
        )
        if hasattr(self, "_hud_game_night_start_btn"):
            self._hud_game_night_start_btn.setEnabled(True)
            self._hud_game_night_stop_btn.setEnabled(False)
            self._set_status_badge(
                self._hud_game_night_status,
                "idle",
                "Ready.",
            )

    def _make_health_row(self, status: str, title: str, summary: str) -> QFrame:
        bg, fg, label = {
            "ok": ("#121e2d", "#4fc1ff", "Ready"),
            "warn": ("#1e1a06", "#d4a843", "Needs setup"),
            "err": ("#3a1010", "#f48771", "Needs fix"),
            "dim": ("#252526", "#858585", "Optional"),
        }.get(status, ("#252526", "#858585", "Optional"))

        row = QFrame()
        row.setObjectName({
            "ok": "hw-card-ok",
            "warn": "hw-card-warn",
            "err": "hw-card-err",
            "dim": "hw-card-dim",
        }.get(status, "hw-card-dim"))
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("card-summary")
        title_lbl.setStyleSheet("font-size:13px; font-weight:700;")
        layout.addWidget(title_lbl)

        summary_lbl = QLabel(summary)
        summary_lbl.setObjectName("card-copy")
        summary_lbl.setWordWrap(True)
        layout.addWidget(summary_lbl, 1)

        badge = QLabel(f"  {label}  ")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background:{bg}; color:{fg}; border:1px solid {fg}; "
            "border-radius:3px; padding:2px 8px; font-size:11px; font-weight:700;"
        )
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
            "streaming": self._streaming_rows_layout,
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
        self._set_rows_loading(self._streaming_rows_layout, "Checking Discord, OBS, capture, audio, and camera tools…")
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
        _apply_install_badge(self._mh_badge, _mangohud_installed())
        if hasattr(self, "_gs_badge"):
            _apply_install_badge(self._gs_badge, _gamescope_installed())
        if hasattr(self, "_vk_badge"):
            _apply_install_badge(self._vk_badge, _vkbasalt_installed())
        if hasattr(self, "_scx_badge"):
            scx_status = _command_stdout(["kyth-scx", "status"], timeout=5)
            scx_active = "Service: active" in scx_status
            _apply_install_badge(self._scx_badge, scx_active, ok_text="Active", warn_text="Inactive")
            if scx_status:
                configured = "unknown"
                for line in scx_status.splitlines():
                    if line.startswith("Configured scheduler:"):
                        configured = line.split(":", 1)[1].strip() or "unknown"
                        break
                self._scx_status_lbl.setText(f"Configured: {configured}")
            else:
                self._scx_status_lbl.setText("sched-ext status unavailable.")

        pc_ver = _proton_cachyos_version()
        _apply_install_badge(self._pc_badge, bool(pc_ver), ok_text=pc_ver or "Installed")
        self._pc_version_lbl.setText(
            f"Installed: {pc_ver}" if pc_ver
            else "Proton-CachyOS not found in compatibilitytools.d"
        )

        if hasattr(self, "_ge_badge"):
            ge_ver = _compat_tool_version("GE-Proton")
            _apply_install_badge(self._ge_badge, bool(ge_ver), ok_text=ge_ver or "Installed", warn_text="Optional")
            self._ge_version_lbl.setText(
                f"Installed: {ge_ver}" if ge_ver
                else "Not installed. Optional fallback runner; Proton-CachyOS remains the recommended default."
            )

        for refs in self._tool_refs:
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

    def _refresh_game_bar_btn(self):
        installed = _is_flatpak_installed("com.dec05eba.gpu_screen_recorder")
        self._game_bar_btn.setText(
            "Open GPU Screen Recorder" if installed else "Install Game Bar Alternative"
        )
        self._set_status_badge(
            self._game_bar_status,
            "ok" if installed else "idle",
            "GPU Screen Recorder is installed." if installed else "Install GPU Screen Recorder for capture and instant replay.",
        )

    def _open_or_install_game_bar(self):
        app_id = "com.dec05eba.gpu_screen_recorder"
        if _is_flatpak_installed(app_id):
            try:
                flatpak_run(app_id)
                self._set_status_badge(self._game_bar_status, "ok", "Opening GPU Screen Recorder.")
            except OSError as exc:
                self._set_status_badge(self._game_bar_status, "err", f"Could not open GPU Screen Recorder: {exc}")
                QMessageBox.warning(self, "Could not open GPU Screen Recorder", str(exc))
            return

        def _installed(code: int):
            if code == 0:
                self._game_bar_btn.setEnabled(True)
                self._refresh_game_bar_btn()
            else:
                self._set_status_badge(self._game_bar_status, "err", "GPU Screen Recorder installation failed.")

        self._set_status_badge(self._game_bar_status, "running", "Installing GPU Screen Recorder…")
        _install_flatpak_inline(
            self, self._game_bar_btn, app_id, "GPU Screen Recorder",
            done_cb=_installed,
        )

    def _make_gaming_ready_panel(self) -> QFrame:
        steam_ok = _is_flatpak_installed("com.valvesoftware.Steam")
        pc_ver = _proton_cachyos_version()
        vulkan_hint = bool(glob.glob("/dev/dri/renderD*")) or shutil.which("vulkaninfo") is not None
        ntsync_ok = os.path.exists("/dev/ntsync")
        items = [
            ("ok" if steam_ok else "warn", "Steam", "Installed." if steam_ok else "Install Steam for your library."),
            ("ok" if pc_ver else "err", "Proton-CachyOS", pc_ver or "Update Proton-CachyOS before testing PC games."),
            ("ok" if vulkan_hint else "err", "Vulkan", "Render device found." if vulkan_hint else "No Vulkan render device found."),
            ("ok" if ntsync_ok else "warn", "NTSYNC", "Ready." if ntsync_ok else "Not active; Proton can fall back safely."),
            ("ok" if _gamescope_installed() else "warn", "Gamescope", "Ready." if _gamescope_installed() else "Install for scaling, HDR, and frame pacing presets."),
            ("ok" if _mangohud_installed() else "warn", "MangoHud", "Ready." if _mangohud_installed() else "Install for the performance overlay."),
        ]
        ok_count = sum(1 for status, _, _ in items if status == "ok")
        issue_count = sum(1 for status, _, _ in items if status == "err")
        warn_count = sum(1 for status, _, _ in items if status == "warn")
        total = len(items)

        card, layout = _make_card("ready-panel")
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(18)

        score_col = QVBoxLayout()
        score_col.setSpacing(2)
        score = QLabel(f"{ok_count}/{total}")
        score.setObjectName("ready-score-err" if issue_count else "ready-score-warn" if warn_count else "ready-score")
        score_col.addWidget(score)
        score_label = QLabel("gaming checks ready")
        score_label.setObjectName("stat-label")
        score_col.addWidget(score_label)
        top.addLayout(score_col)

        copy_col = QVBoxLayout()
        copy_col.setSpacing(5)
        title = QLabel("Gaming readiness")
        title.setObjectName("card-title")
        copy_col.addWidget(title)
        if issue_count:
            summary = "A couple of core pieces need attention before PC games will feel smooth."
        elif warn_count:
            summary = "The core stack is close. Review the yellow items before benchmarking or migrating."
        else:
            summary = "The important pieces are in place. Scroll down for launchers, Proton, and game tools."
        body = QLabel(summary)
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        copy_col.addWidget(body)
        top.addLayout(copy_col, 1)
        layout.addLayout(top)

        pill_grid = QVBoxLayout()
        pill_grid.setSpacing(8)
        for start in (0, 3):
            row = QHBoxLayout()
            row.setSpacing(8)
            for item in items[start:start + 3]:
                row.addWidget(self._make_ready_pill(*item), 1)
            pill_grid.addLayout(row)
        layout.addLayout(pill_grid)

        return card

    def _make_ready_pill(self, status: str, name: str, summary: str) -> QLabel:
        prefix = {
            "ok": "Ready",
            "warn": "Check",
            "err": "Fix",
            "dim": "Optional",
        }.get(status, "Info")
        label = QLabel(f"{prefix}: {name}\n{summary}")
        label.setObjectName(f"ready-row-{status if status in {'ok', 'warn', 'err', 'dim'} else 'dim'}")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        label.setMinimumHeight(74)
        return label
