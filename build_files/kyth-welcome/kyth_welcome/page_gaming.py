import glob
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

# __KYTH_GENERATED_IMPORTS__
from .core import (  # noqa: E501
    DataWorker, Worker, _PROTONDB_TIER_STYLE, _ProtonDbBatchWorker, _apply_install_badge, _cancel_worker, _collect_gaming_dashboard, _command_stdout, _compat_tool_version, _detect_installed_games, _find_ntfs_drives, _find_steam_libraries, _finish_worker, _gamescope_installed, _gaming_health_items, _gaming_migration_checklist_items, _ge_proton_version, _install_flatpak_inline, _is_flatpak_installed, _load_protondb_cache, _ludusavi_backup_summary, _mangohud_installed, _release_worker_when_finished, _restyle, _save_protondb_cache, _scan_steamapps_manifests, _streaming_health_items, _vkbasalt_installed,
)
from .page_cloud_storage import (  # noqa: E501
    SteamCopyWorker, _copy_text, _launch_opt_label, _launch_opt_value,
)
from .page_compatibility import (  # noqa: E501
    _COMPAT_GAMES,
)
from .page_windows_migration import (  # noqa: E501
    WindowsLibraryWorker,
)
from .qt import (  # noqa: E501
    QApplication, QComboBox, QDesktopServices, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QTextEdit, QTimer, QUrl, QVBoxLayout, QWidget, Qt,
)
from .widgets import (  # noqa: E501
    ActionRow, CommandResultPanel, Page, StatusBadge, _make_card, _set_log_panel,
)

# ── Page: Gaming ─────────────────────────────────────────────────────────────
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
        ge_ver = _ge_proton_version() or "None"
        mangohud = "🟢 Active" if _mangohud_installed() else "🔴 Missing"
        vkbasalt = "🟢 Active" if _vkbasalt_installed() else "⚪ Optional"
        gamescope = "🟢 Active" if _gamescope_installed() else "🔴 Missing"
        
        self._hud_runtime_desc.setText(
            f"<b>GE-Proton:</b> {ge_ver}<br>"
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

    @staticmethod
    def _command_details(cmd: list[str], result=None, exc: Exception | None = None) -> str:
        lines = ["Command:", "  " + " ".join(cmd)]
        if exc is not None:
            lines.extend(["", "Error:", str(exc)])
            return "\n".join(lines)
        if result is None:
            return "\n".join(lines)
        lines.extend(["", f"Exit code: {result.returncode}"])
        stdout = result.stdout.decode("utf-8", errors="replace").strip() if result.stdout else ""
        stderr = result.stderr.decode("utf-8", errors="replace").strip() if result.stderr else ""
        if stdout:
            lines.extend(["", "stdout:", stdout])
        if stderr:
            lines.extend(["", "stderr:", stderr])
        return "\n".join(lines)

    def __init__(self, wizard_mode: bool = False):
        super().__init__()
        self._wizard_mode = wizard_mode
        self._ge_update_worker = None
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
            "KythOS ships a full gaming stack — Gamescope, MangoHud, GE-Proton, and more. "
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

        self._active_gaming_section = "setup"
        self._add(self._make_gaming_ready_panel())

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

        # ── PC Game Library ──────────────────────────────────────────────
        self._win_lib_card, self._win_lib_layout = _make_card("card-accent-ok")
        self._win_lib_card.hide()
        self._add(self._win_lib_card)
        self._divider()

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
            night_actions.add_button(label, lambda _=False, c=cmd: subprocess.Popen(c))  # nosec B603 # nosemgrep
        night_actions.finish()
        self._game_night_status = night_actions.status
        night_layout.addWidget(night_actions)
        self._game_night_inhibit = None
        self._add(night_card)

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

        self._active_gaming_section = "library"
        # ── Game readiness scanner ───────────────────────────────────────────
        scanner_card, scanner_layout = _make_card()
        scanner_title = QLabel("Game Readiness Scanner")
        scanner_title.setObjectName("card-title")
        scanner_layout.addWidget(scanner_title)
        scanner_desc = QLabel(
            "Search the KythOS compatibility list and get the recommended launcher, "
            "runner, launch profile, save step, and source check date."
        )
        scanner_desc.setObjectName("card-copy")
        scanner_desc.setWordWrap(True)
        scanner_layout.addWidget(scanner_desc)
        scanner_row = QHBoxLayout()
        scanner_row.setSpacing(8)
        self._readiness_combo = QComboBox()
        self._readiness_combo.setEditable(True)
        self._readiness_combo.setMinimumWidth(320)
        for game in sorted(_COMPAT_GAMES, key=lambda item: item.name.lower()):
            self._readiness_combo.addItem(game.name)
        scanner_row.addWidget(self._readiness_combo, 1)
        readiness_btn = QPushButton("Check Game")
        readiness_btn.setObjectName("primary")
        readiness_btn.clicked.connect(self._check_game_readiness)
        scanner_row.addWidget(readiness_btn)
        scanner_layout.addLayout(scanner_row)
        self._readiness_result = QLabel("Pick a game or type a title to check readiness.")
        self._readiness_result.setObjectName("card-copy")
        self._readiness_result.setWordWrap(True)
        scanner_layout.addWidget(self._readiness_result)
        scanner_btns = QHBoxLayout()
        scanner_btns.setSpacing(8)
        protondb_lookup = QPushButton("Open ProtonDB")
        protondb_lookup.clicked.connect(self._open_readiness_protondb)
        scanner_btns.addWidget(protondb_lookup)
        anticheat_lookup = QPushButton("Open Anti-Cheat Status")
        anticheat_lookup.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://areweanticheatyet.com")))
        scanner_btns.addWidget(anticheat_lookup)
        scanner_btns.addStretch()
        scanner_layout.addLayout(scanner_btns)
        self._add(scanner_card)

        # ── My Games dashboard ───────────────────────────────────────────────
        my_games_card, my_games_layout = _make_card()
        my_games_top = QHBoxLayout()
        my_games_title = QLabel("My Games")
        my_games_title.setObjectName("card-title")
        my_games_top.addWidget(my_games_title)
        my_games_top.addStretch()
        my_games_refresh = QPushButton("Scan Libraries")
        my_games_refresh.clicked.connect(lambda _=False: self._refresh_my_games(async_scan=True))
        my_games_top.addWidget(my_games_refresh)
        my_games_layout.addLayout(my_games_top)
        my_games_desc = QLabel(
            "Detects installed games from Steam, Heroic, Lutris, and Bottles, then "
            "adds KythOS compatibility and profile hints when a title matches the curated list."
        )
        my_games_desc.setObjectName("card-copy")
        my_games_desc.setWordWrap(True)
        my_games_layout.addWidget(my_games_desc)
        self._my_games_summary_lbl = QLabel("Scan libraries to build your local dashboard.")
        self._my_games_summary_lbl.setObjectName("card-copy")
        self._my_games_summary_lbl.setWordWrap(True)
        my_games_layout.addWidget(self._my_games_summary_lbl)
        self._my_games_rows_layout = QVBoxLayout()
        self._my_games_rows_layout.setSpacing(8)
        my_games_layout.addLayout(self._my_games_rows_layout)
        self._add(my_games_card)

        self._active_gaming_section = "fixes"
        # ── First-failure playbook ────────────────────────────────────────────
        playbook_card, playbook_layout = _make_card()
        playbook_title = QLabel("Game will not launch")
        playbook_title.setObjectName("card-title")
        playbook_layout.addWidget(playbook_title)
        playbook_desc = QLabel(
            "Start simple: try a clean Proton runner, collect a log, then disable one "
            "sync path at a time. These launch options are safe per-game tests."
        )
        playbook_desc.setObjectName("card-copy")
        playbook_desc.setWordWrap(True)
        playbook_layout.addWidget(playbook_desc)
        for label, opt in (
            ("Capture Proton log:", "PROTON_LOG=1 %command%"),
            ("Disable NTSYNC:", "PROTON_NO_NTSYNC=1 %command%"),
            ("Disable esync:", "PROTON_NO_ESYNC=1 %command%"),
            ("Disable fsync:", "PROTON_NO_FSYNC=1 %command%"),
            ("Force Vulkan HUD:", "MANGOHUD=1 %command%"),
            ("Launcher retry:", "PROTON_LOG=1 PROTON_NO_NTSYNC=1 %command%"),
        ):
            playbook_layout.addLayout(self._copy_option_row(label, opt))
        playbook_btns = QHBoxLayout()
        playbook_btns.setSpacing(8)
        protondb_btn = QPushButton("Open ProtonDB")
        protondb_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://www.protondb.com")))
        playbook_btns.addWidget(protondb_btn)
        anticheat_btn = QPushButton("Open Anti-Cheat Status")
        anticheat_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://areweanticheatyet.com")))
        playbook_btns.addWidget(anticheat_btn)
        playbook_btns.addStretch()
        playbook_layout.addLayout(playbook_btns)
        self._add(playbook_card)

        # ── Fix my game ──────────────────────────────────────────────────────
        fix_card, fix_layout = _make_card()
        fix_title = QLabel("Fix My Game")
        fix_title.setObjectName("card-title")
        fix_layout.addWidget(fix_title)
        fix_desc = QLabel(
            "Fast non-destructive support actions: open the folders players need, "
            "copy safe launch tests, and generate diagnostics."
        )
        fix_desc.setObjectName("card-copy")
        fix_desc.setWordWrap(True)
        fix_layout.addWidget(fix_desc)
        fix_actions = ActionRow("", "idle")
        for label, action in (
            ("Open Steam compatdata", lambda: self._open_user_path("~/.local/share/Steam/steamapps/compatdata")),
            ("Open shadercache", lambda: self._open_user_path("~/.local/share/Steam/steamapps/shadercache")),
            ("Copy reset-prefix command", self._copy_prefix_reset_hint),
            ("Copy support snapshot", self._copy_support_snapshot_command),
        ):
            fix_actions.add_button(label, action)
        fix_actions.finish()
        self._fix_status_lbl = fix_actions.status
        self._fix_status_lbl.hide()
        fix_layout.addWidget(fix_actions)
        self._add(fix_card)

        self._active_gaming_section = "setup"
        # ── Gaming Tools ──────────────────────────────────────────────────────
        tools_head = QLabel("Gaming Tools")
        tools_head.setObjectName("heading")
        tools_head.setStyleSheet("font-size: 18px; font-weight: 700; color: #ffffff;")
        self._add(tools_head)
        tools_sub = QLabel(
            "Install the launchers and tools you want. "
            "Bottles is the easiest option for standalone `.exe` and `.msi` installers. "
            "Additional launchers and device tools are available here or via the corresponding ujust recipe."
        )
        tools_sub.setObjectName("card-copy")
        tools_sub.setWordWrap(True)
        self._add(tools_sub)

        self._TOOLS = [
            {
                "flatpak": "com.valvesoftware.Steam",
                "name": "Steam",
                "desc": "Valve's gaming platform plus PC games through Proton.",
                "ujust": "install-steam",
                "launch": ["flatpak", "run", "com.valvesoftware.Steam"],
            },
            {
                "flatpak": "net.lutris.Lutris",
                "name": "Lutris",
                "desc": "Battle.net, EA App, Ubisoft Connect, and other compatibility launchers.",
                "ujust": "install-lutris",
                "launch": ["flatpak", "run", "net.lutris.Lutris"],
            },
            {
                "flatpak": "com.heroicgameslauncher.hgl",
                "name": "Heroic Games Launcher",
                "desc": "Epic Games, GOG, and Amazon Games library in one place.",
                "ujust": "install-heroic",
                "launch": ["flatpak", "run", "com.heroicgameslauncher.hgl"],
            },
            {
                "flatpak": "com.usebottles.bottles",
                "name": "Bottles",
                "desc": "Best for running standalone .exe and .msi installers in isolated app environments.",
                "ujust": "install-bottles",
                "launch": ["flatpak", "run", "com.usebottles.bottles"],
            },
            {
                "flatpak": "com.github.mtkennerly.ludusavi",
                "name": "Ludusavi",
                "desc": "Back up and restore game saves across Steam, Heroic, Lutris, and PC migrations.",
                "ujust": "install-ludusavi",
                "launch": ["flatpak", "run", "com.github.mtkennerly.ludusavi"],
            },
            {
                "flatpak": "org.prismlauncher.PrismLauncher",
                "name": "Prism Launcher",
                "desc": "Minecraft launcher with modpacks, multiple instances, and Java version control.",
                "ujust": "install-prismlauncher",
                "launch": ["flatpak", "run", "org.prismlauncher.PrismLauncher"],
            },
            {
                "flatpak": "io.itch.itch",
                "name": "Itch.io",
                "desc": "Indie game store and library manager.",
                "ujust": "install-itch",
                "launch": ["flatpak", "run", "io.itch.itch"],
            },
            {
                "flatpak": "org.libretro.RetroArch",
                "name": "RetroArch",
                "desc": "Multi-system emulator frontend (NES, SNES, PS1, N64, …).",
                "ujust": "install-retroarch",
                "launch": ["flatpak", "run", "org.libretro.RetroArch"],
            },
            {
                "flatpak": "org.freedesktop.Piper",
                "name": "Piper",
                "desc": "GUI for configuring gaming mice — DPI, buttons, and LEDs.",
                "ujust": "install-piper",
                "launch": ["flatpak", "run", "org.freedesktop.Piper"],
            },
            {
                "flatpak": "org.openrgb.OpenRGB",
                "name": "OpenRGB",
                "desc": "Unified RGB lighting control for motherboards, RAM, GPUs, and peripherals. Pre-installed — RGB profiles are applied automatically at login.",
                "ujust": "install-openrgb",
                "launch": ["openrgb"],
            },
            {
                "flatpak": "io.github.benjamimgois.goverlay",
                "name": "GOverlay",
                "desc": "Graphical tuning for MangoHud and vkBasalt overlays — adjust metrics, colors, and presets without editing config files.",
                "ujust": "install-goverlay",
                "launch": ["flatpak", "run", "io.github.benjamimgois.goverlay"],
            },
            {
                "flatpak": "io.github.radiolamp.mangojuice",
                "name": "MangoJuice",
                "desc": "Lightweight MangoHud configuration editor for overlay layout and metrics.",
                "ujust": "install-mangojuice",
                "launch": ["flatpak", "run", "io.github.radiolamp.mangojuice"],
            },
            {
                "flatpak": "com.dec05eba.gpu_screen_recorder",
                "name": "GPU Screen Recorder",
                "desc": "Near-zero overhead gameplay capture and instant replay using AMD/NVIDIA GPU encoding.",
                "ujust": "install-gpu-screen-recorder",
                "launch": ["flatpak", "run", "com.dec05eba.gpu_screen_recorder"],
            },
            {
                "flatpak": "dev.vencord.Vesktop",
                "name": "Vesktop",
                "desc": "Discord client with native Wayland support, better screenshare, and no telemetry.",
                "ujust": "install-vesktop",
                "launch": ["flatpak", "run", "dev.vencord.Vesktop"],
            },
        ]

        # Build tiles in a 2-column grid
        self._tool_refs: list[dict] = []
        for i in range(0, len(self._TOOLS), 2):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(16)
            for tool in self._TOOLS[i:i + 2]:
                tile, refs = self._make_tool_tile(tool)
                row_layout.addWidget(tile, 1)
                self._tool_refs.append(refs)
            # Pad the last row if odd number of tools
            if len(self._TOOLS[i:i + 2]) == 1:
                row_layout.addStretch(1)
            self._add_layout(row_layout)

        tuning_card, tuning_layout = _make_card()
        tuning_title = QLabel("Advanced GPU and Capture Tools")
        tuning_title.setObjectName("card-title")
        tuning_layout.addWidget(tuning_title)
        tuning_desc = QLabel(
            "LACT and CoreCtrl cover AMD GPU tuning, while OBS uses the built-in "
            "obs-vkcapture and v4l2loopback support for game capture and virtual camera workflows."
        )
        tuning_desc.setObjectName("card-copy")
        tuning_desc.setWordWrap(True)
        tuning_layout.addWidget(tuning_desc)
        tuning_btns = QHBoxLayout()
        tuning_btns.setSpacing(8)
        lact_btn = QPushButton("Install LACT")
        lact_btn.clicked.connect(lambda _=False, b=lact_btn: _install_flatpak_inline(
            self, b, "io.github.ilya_zlobintsev.LACT", "LACT"))
        tuning_btns.addWidget(lact_btn)
        corectrl_btn = QPushButton("Open CoreCtrl")
        corectrl_btn.clicked.connect(lambda _=False: self._open_corectrl())
        tuning_btns.addWidget(corectrl_btn)
        obs_btn = QPushButton("Install OBS")
        obs_btn.clicked.connect(lambda _=False, b=obs_btn: self._install_obs_inline(b))
        tuning_btns.addWidget(obs_btn)
        tuning_btns.addStretch()
        tuning_layout.addLayout(tuning_btns)
        self._add(tuning_card)

        # ── OptiScaler card ──────────────────────────────────────────────────
        opti_card, opti_layout = _make_card()
        opti_title = QLabel("OptiScaler — Universal Upscaling")
        opti_title.setObjectName("card-title")
        opti_layout.addWidget(opti_title)
        opti_desc = QLabel(
            "Enables FSR2/3, XeSS, and DLSS-translation in any DirectX 11/12 game through "
            "Proton's DLL override — including games that ship without upscaling support. "
            "Works on all AMD and Intel GPUs. Deploy to a game folder, then set the Steam "
            "launch option: <code>WINEDLLOVERRIDES=\"nvngx=n,b\" %command%</code>"
        )
        opti_desc.setObjectName("card-copy")
        opti_desc.setWordWrap(True)
        opti_desc.setTextFormat(Qt.TextFormat.RichText)
        opti_layout.addWidget(opti_desc)
        opti_btns = QHBoxLayout()
        opti_btns.setSpacing(8)
        opti_deploy_btn = QPushButton("Deploy to Game Folder…")
        opti_deploy_btn.clicked.connect(
            lambda _=False, b=opti_deploy_btn: self._deploy_opticscaler(b)
        )
        opti_btns.addWidget(opti_deploy_btn)
        self._opti_deploy_btn = opti_deploy_btn
        opti_copy_btn = QPushButton("Copy Launch Option")
        opti_copy_btn.setToolTip('Copies: WINEDLLOVERRIDES="nvngx=n,b" %command%')
        opti_copy_btn.clicked.connect(lambda _=False: self._copy_opticscaler_launch_opt(opti_copy_btn))
        opti_btns.addWidget(opti_copy_btn)
        self._opti_copy_btn = opti_copy_btn
        opti_btns.addStretch()
        opti_layout.addLayout(opti_btns)
        self._opti_status_lbl = QLabel("")
        self._opti_status_lbl.setObjectName("subheading")
        self._opti_status_lbl.hide()
        opti_layout.addWidget(self._opti_status_lbl)
        self._opti_log = QTextEdit()
        self._opti_log.setReadOnly(True)
        self._opti_log.setMaximumHeight(140)
        self._opti_log.hide()
        opti_layout.addWidget(self._opti_log)
        self._opticscaler_worker: Worker | None = None
        self._add(opti_card)

        streaming_card, streaming_layout = _make_card()
        streaming_top = QHBoxLayout()
        streaming_title = QLabel("Streaming and Discord Readiness")
        streaming_title.setObjectName("card-title")
        streaming_top.addWidget(streaming_title)
        streaming_top.addStretch()
        streaming_refresh = QPushButton("Refresh")
        streaming_refresh.clicked.connect(self._refresh_gaming_dashboard)
        streaming_top.addWidget(streaming_refresh)
        streaming_layout.addLayout(streaming_top)
        streaming_desc = QLabel(
            "PC gamers bring Discord, OBS, capture, microphones, and screen share "
            "expectations with them. This checks the pieces that make that feel normal."
        )
        streaming_desc.setObjectName("card-copy")
        streaming_desc.setWordWrap(True)
        streaming_layout.addWidget(streaming_desc)
        self._streaming_rows_layout = QVBoxLayout()
        self._streaming_rows_layout.setSpacing(8)
        streaming_layout.addLayout(self._streaming_rows_layout)
        streaming_btns = QHBoxLayout()
        streaming_btns.setSpacing(8)
        install_discord = QPushButton("Install Discord")
        install_discord.clicked.connect(lambda _=False, b=install_discord: _install_flatpak_inline(
            self, b, "com.discordapp.Discord", "Discord"))
        streaming_btns.addWidget(install_discord)
        install_obs = QPushButton("Install OBS")
        install_obs.clicked.connect(lambda _=False, b=install_obs: self._install_obs_inline(b))
        streaming_btns.addWidget(install_obs)
        streaming_btns.addStretch()
        streaming_layout.addLayout(streaming_btns)

        # Discord screen share fix card
        discord_fix_card, discord_fix_layout = _make_card()
        discord_fix_title = QLabel("Fix Discord screen share on Wayland")
        discord_fix_title.setObjectName("card-title")
        discord_fix_layout.addWidget(discord_fix_title)
        discord_fix_body = QLabel(
            "Discord screen share is broken by default under Wayland. "
            "This applies the correct Flatpak environment flags and enables PipeWire capture. "
            "Restart Discord after applying. Alternatively, Vesktop (in Gaming Tools above) "
            "has screen share working out of the box."
        )
        discord_fix_body.setObjectName("card-copy")
        discord_fix_body.setWordWrap(True)
        discord_fix_layout.addWidget(discord_fix_body)
        discord_fix_actions = ActionRow("", "idle")
        self._discord_fix_btn = discord_fix_actions.add_button(
            "Fix Discord Screen Share", self._fix_discord_screenshare, primary=True
        )
        discord_fix_actions.finish()
        self._discord_fix_status = discord_fix_actions.status
        self._discord_fix_status.hide()
        discord_fix_layout.addWidget(discord_fix_actions)
        self._discord_fix_result = CommandResultPanel()
        self._discord_fix_result.hide()
        discord_fix_layout.addWidget(self._discord_fix_result)

        # OBS PipeWire setup
        obs_fix_note = QLabel("Fix OBS audio capture (apply PipeWire/Wayland Flatpak permissions)")
        obs_fix_note.setObjectName("card-title")
        obs_fix_note.setStyleSheet("margin-top:8px;")
        discord_fix_layout.addWidget(obs_fix_note)
        obs_fix_body = QLabel(
            "OBS installed from Flathub may not capture audio or display correctly under Wayland. "
            "This grants the required Flatpak socket permissions for PipeWire and Wayland output."
        )
        obs_fix_body.setObjectName("card-copy")
        obs_fix_body.setWordWrap(True)
        discord_fix_layout.addWidget(obs_fix_body)
        obs_fix_actions = ActionRow("", "idle")
        self._obs_fix_btn = obs_fix_actions.add_button("Fix OBS Audio + Display", self._fix_obs_pipewire)
        obs_fix_actions.finish()
        self._obs_fix_status = obs_fix_actions.status
        self._obs_fix_status.hide()
        discord_fix_layout.addWidget(obs_fix_actions)
        self._obs_fix_result = CommandResultPanel()
        self._obs_fix_result.hide()
        discord_fix_layout.addWidget(self._obs_fix_result)
        self._add(discord_fix_card)

        self._add(streaming_card)

        self._divider()
        launcher_head = QLabel("Launcher setup")
        launcher_head.setObjectName("card-title")
        self._add(launcher_head)
        launcher_sub = QLabel(
            "Heroic is the recommended default for Epic and GOG. "
            "Install Lutris above, then use the buttons below to start Lutris installers for Battle.net, EA App, and Ubisoft Connect."
        )
        launcher_sub.setObjectName("card-copy")
        launcher_sub.setWordWrap(True)
        self._add(launcher_sub)

        launcher_card, launcher_layout = _make_card()
        launcher_note = QLabel(
            "Recommended pairing: Heroic for Epic/GOG/Amazon libraries, Lutris (install above) for Battle.net, EA App, and Ubisoft Connect, and Bottles for standalone .exe / .msi installers."
        )
        launcher_note.setObjectName("card-copy")
        launcher_note.setWordWrap(True)
        launcher_layout.addWidget(launcher_note)

        launcher_btns = QHBoxLayout()
        launcher_btns.setSpacing(8)

        epic_btn = QPushButton("Open Heroic for Epic")
        epic_btn.clicked.connect(lambda _=False: self._open_heroic_for_epic())
        launcher_btns.addWidget(epic_btn)

        battlenet_btn = QPushButton("Install Battle.net")
        battlenet_btn.clicked.connect(
            lambda _=False: self._launch_lutris_installer("battlenet", "Battle.net")
        )
        launcher_btns.addWidget(battlenet_btn)

        ea_btn = QPushButton("Install EA App")
        ea_btn.clicked.connect(
            lambda _=False: self._launch_lutris_installer("lutris:ea-app-standard", "EA App")
        )
        launcher_btns.addWidget(ea_btn)

        ubisoft_btn = QPushButton("Install Ubisoft Connect")
        ubisoft_btn.clicked.connect(
            lambda _=False: self._launch_lutris_installer("lutris:ubisoft-connect-latest", "Ubisoft Connect")
        )
        launcher_btns.addWidget(ubisoft_btn)

        launcher_btns.addStretch()
        launcher_layout.addLayout(launcher_btns)

        # Launcher status / log (used by Open Heroic / Lutris installer buttons)
        self._tool_op_status = QLabel()
        self._tool_op_status.setObjectName("subheading")
        self._tool_op_status.hide()
        launcher_layout.addWidget(self._tool_op_status)
        self._tool_progress = QProgressBar()
        self._tool_progress.setRange(0, 0)
        self._tool_progress.hide()
        launcher_layout.addWidget(self._tool_progress)
        self._tool_cancel_btn = QPushButton("Cancel")
        self._tool_cancel_btn.clicked.connect(self._cancel_launcher_tool_operation)
        self._tool_cancel_btn.hide()
        launcher_layout.addWidget(self._tool_cancel_btn)
        self._tool_log_toggle = QPushButton("Show details")
        self._tool_log_toggle.setCheckable(True)
        self._tool_log_toggle.clicked.connect(lambda checked: _set_log_panel(self._tool_log_toggle, self._tool_log, checked))
        self._tool_log_toggle.hide()
        launcher_layout.addWidget(self._tool_log_toggle)
        self._tool_log = QTextEdit()
        self._tool_log.setReadOnly(True)
        self._tool_log.setMaximumHeight(120)
        self._tool_log.hide()
        launcher_layout.addWidget(self._tool_log)
        self._add(launcher_card)

        self._tool_worker = None
        self._active_tool_refs = None

        self._active_gaming_section = "tuning"
        self._divider()

        # ── MangoHud ──────────────────────────────────────────────────────────
        mh_card, mh_layout = _make_card()
        mh_top = QHBoxLayout()
        mh_title = QLabel("MangoHud — Performance Overlay")
        mh_title.setObjectName("card-title")
        mh_top.addWidget(mh_title)
        mh_top.addStretch()
        self._mh_badge = QLabel()
        self._mh_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mh_top.addWidget(self._mh_badge)
        mh_layout.addLayout(mh_top)
        mh_desc = QLabel(
            "Shows FPS, frame time, GPU/CPU load and temperature as an in-game overlay. "
            "Toggle on/off at any time with Right Shift + F12."
        )
        mh_desc.setObjectName("card-copy")
        mh_desc.setWordWrap(True)
        mh_layout.addWidget(mh_desc)
        mh_opts = QHBoxLayout()
        mh_opts.setSpacing(10)
        mh_opts.addWidget(_launch_opt_label("Steam launch option:"))
        mh_opts.addWidget(_launch_opt_value("MANGOHUD=1 %command%"))
        mh_copy = QPushButton("Copy")
        mh_copy.clicked.connect(lambda: _copy_text("MANGOHUD=1 %command%"))
        mh_opts.addWidget(mh_copy)
        mh_opts.addStretch()
        mh_layout.addLayout(mh_opts)
        mh_cfg_row = QHBoxLayout()
        mh_cfg_row.setSpacing(10)
        mh_cfg_lbl = QLabel("Config: /etc/MangoHud/MangoHud.conf  ·  override: ~/.config/MangoHud/MangoHud.conf")
        mh_cfg_lbl.setObjectName("card-copy")
        mh_cfg_row.addWidget(mh_cfg_lbl)
        mh_cfg_row.addStretch()
        mh_layout.addLayout(mh_cfg_row)
        self._add(mh_card)

        if not wizard_mode:
            # ── Gamescope ─────────────────────────────────────────────────────
            gs_card, gs_layout = _make_card()
            gs_top = QHBoxLayout()
            gs_title = QLabel("Gamescope — Game Compositor")
            gs_title.setObjectName("card-title")
            gs_top.addWidget(gs_title)
            gs_top.addStretch()
            self._gs_badge = QLabel()
            self._gs_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            gs_top.addWidget(self._gs_badge)
            gs_layout.addLayout(gs_top)
            gs_desc = QLabel(
                "Valve's micro-compositor for games: better frame pacing, VRR/adaptive sync, "
                "FSR upscaling, and HDR. Runs the game inside its own compositor so the "
                "desktop is unaffected. Using -e keeps Steam Input and overlay working."
            )
            gs_desc.setObjectName("card-copy")
            gs_desc.setWordWrap(True)
            gs_layout.addWidget(gs_desc)

            for label, opt in (
                ("Quality preset:", "kyth-gamescope quality -- %command%"),
                ("HDR display:", "kyth-gamescope hdr --fps 120 -- %command%"),
                ("Sharp upscaling:", "kyth-gamescope sharp --fsr --nested 1920x1080 --output 2560x1440 -- %command%"),
                ("ujust recipe:", "ujust game-scope quality -- %command%"),
            ):
                row = QHBoxLayout()
                row.setSpacing(10)
                row.addWidget(_launch_opt_label(label))
                row.addWidget(_launch_opt_value(opt))
                cp = QPushButton("Copy")
                captured = opt
                cp.clicked.connect(lambda _=False, t=captured: _copy_text(t))
                row.addWidget(cp)
                row.addStretch()
                gs_layout.addLayout(row)
            self._add(gs_card)

        # ── Per-game profile builder ─────────────────────────────────────────
        profile_card, profile_layout = _make_card()
        profile_title = QLabel("Per-Game Profile Builder")
        profile_title.setObjectName("card-title")
        profile_layout.addWidget(profile_title)
        profile_desc = QLabel(
            "Pick a common goal and copy the Steam launch option. Use this before "
            "manual tuning so players get a known-good KythOS baseline first."
        )
        profile_desc.setObjectName("card-copy")
        profile_desc.setWordWrap(True)
        profile_layout.addWidget(profile_desc)

        profile_row = QHBoxLayout()
        profile_row.setSpacing(8)
        self._profile_goal_combo = QComboBox()
        self._profile_goal_combo.addItem("Balanced quality", "quality")
        self._profile_goal_combo.addItem("HDR display", "hdr")
        self._profile_goal_combo.addItem("Sharp upscaling", "sharp")
        self._profile_goal_combo.addItem("Low latency", "latency")
        self._profile_goal_combo.addItem("Troubleshoot launch", "troubleshoot")
        profile_row.addWidget(self._profile_goal_combo)
        self._profile_fps_combo = QComboBox()
        for label, value in (("No FPS cap", ""), ("60 FPS", "60"), ("90 FPS", "90"), ("120 FPS", "120"), ("144 FPS", "144"), ("165 FPS", "165")):
            self._profile_fps_combo.addItem(label, value)
        profile_row.addWidget(self._profile_fps_combo)
        profile_row.addStretch()
        profile_layout.addLayout(profile_row)

        profile_opt_row = QHBoxLayout()
        profile_opt_row.setSpacing(10)
        profile_opt_row.addWidget(_launch_opt_label("Steam launch option:"))
        self._profile_launch_value = _launch_opt_value("")
        profile_opt_row.addWidget(self._profile_launch_value, 1)
        profile_copy = QPushButton("Copy")
        profile_copy.clicked.connect(lambda: _copy_text(self._profile_launch_value.text()))
        profile_opt_row.addWidget(profile_copy)
        profile_layout.addLayout(profile_opt_row)

        self._profile_goal_combo.currentIndexChanged.connect(self._update_profile_builder)
        self._profile_fps_combo.currentIndexChanged.connect(self._update_profile_builder)
        self._add(profile_card)

        if not wizard_mode:
            # ── sched-ext ─────────────────────────────────────────────────────
            scx_card, scx_layout = _make_card()
            scx_top = QHBoxLayout()
            scx_title = QLabel("sched-ext — CPU Scheduler")
            scx_title.setObjectName("card-title")
            scx_top.addWidget(scx_title)
            scx_top.addStretch()
            self._scx_badge = QLabel()
            self._scx_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            scx_top.addWidget(self._scx_badge)
            scx_layout.addLayout(scx_top)
            scx_desc = QLabel(
                "KythOS uses CachyOS sched-ext support for latency-focused gaming. "
                "lavd is the default all-rounder; rusty and bpfland are useful alternates for testing."
            )
            scx_desc.setObjectName("card-copy")
            scx_desc.setWordWrap(True)
            scx_layout.addWidget(scx_desc)
            self._scx_status_lbl = QLabel()
            self._scx_status_lbl.setObjectName("card-copy")
            scx_layout.addWidget(self._scx_status_lbl)
            scx_btns = QHBoxLayout()
            scx_btns.setSpacing(8)
            for label, scheduler in (
                ("Use lavd", "lavd"),
                ("Use rusty", "rusty"),
                ("Use bpfland", "bpfland"),
            ):
                btn = QPushButton(label)
                btn.clicked.connect(lambda _=False, sched=scheduler: self._set_scx_scheduler(sched))
                scx_btns.addWidget(btn)
            self._scx_stop_btn = QPushButton("Stop scx")
            self._scx_stop_btn.clicked.connect(lambda _=False: self._set_scx_scheduler("stop"))
            scx_btns.addWidget(self._scx_stop_btn)
            scx_btns.addStretch()
            scx_layout.addLayout(scx_btns)
            self._scx_progress = QProgressBar()
            self._scx_progress.setRange(0, 0)
            self._scx_progress.hide()
            scx_layout.addWidget(self._scx_progress)
            self._scx_log_toggle = QPushButton("Show details")
            self._scx_log_toggle.setCheckable(True)
            self._scx_log_toggle.clicked.connect(lambda checked: _set_log_panel(self._scx_log_toggle, self._scx_log, checked))
            self._scx_log_toggle.hide()
            scx_layout.addWidget(self._scx_log_toggle)
            self._scx_log = QTextEdit()
            self._scx_log.setReadOnly(True)
            self._scx_log.setMaximumHeight(100)
            self._scx_log.hide()
            scx_layout.addWidget(self._scx_log)
            self._scx_worker = None
            self._add(scx_card)

        # ── GE-Proton ─────────────────────────────────────────────────────────
        gp_card, gp_layout = _make_card()
        gp_top = QHBoxLayout()
        gp_title = QLabel("GE-Proton")
        gp_title.setObjectName("card-title")
        gp_top.addWidget(gp_title)
        gp_top.addStretch()
        self._gp_badge = QLabel()
        self._gp_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gp_top.addWidget(self._gp_badge)
        gp_layout.addLayout(gp_top)
        gp_desc = QLabel(
            "Community Proton build with extra game patches, codec support, and "
            "bleeding-edge Wine. Select it per-game in Steam → Properties → "
            "Compatibility → Force the use of a specific Steam Play compatibility tool."
        )
        gp_desc.setObjectName("card-copy")
        gp_desc.setWordWrap(True)
        gp_layout.addWidget(gp_desc)
        self._gp_version_lbl = QLabel()
        self._gp_version_lbl.setObjectName("card-copy")
        gp_layout.addWidget(self._gp_version_lbl)
        gp_btns = QHBoxLayout()
        gp_btns.setSpacing(10)
        self._gp_update_btn = QPushButton("Update GE-Proton")
        self._gp_update_btn.clicked.connect(self._update_ge_proton)
        gp_btns.addWidget(self._gp_update_btn)
        gp_btns.addStretch()
        gp_layout.addLayout(gp_btns)
        self._gp_op_status = QLabel()
        self._gp_op_status.hide()
        gp_layout.addWidget(self._gp_op_status)
        self._gp_progress = QProgressBar()
        self._gp_progress.setRange(0, 0)
        self._gp_progress.hide()
        gp_layout.addWidget(self._gp_progress)
        self._gp_log_toggle = QPushButton("Show details")
        self._gp_log_toggle.setCheckable(True)
        self._gp_log_toggle.clicked.connect(lambda checked: _set_log_panel(self._gp_log_toggle, self._gp_log, checked))
        self._gp_log_toggle.hide()
        gp_layout.addWidget(self._gp_log_toggle)
        self._gp_log = QTextEdit()
        self._gp_log.setReadOnly(True)
        self._gp_log.setMaximumHeight(120)
        self._gp_log.hide()
        gp_layout.addWidget(self._gp_log)
        self._gp_worker = None
        self._add(gp_card)

        if not wizard_mode:
            # ── Optional Proton-CachyOS SLR ───────────────────────────────────
            pc_card, pc_layout = _make_card()
            pc_top = QHBoxLayout()
            pc_title = QLabel("Optional Proton-CachyOS SLR")
            pc_title.setObjectName("card-title")
            pc_top.addWidget(pc_title)
            pc_top.addStretch()
            self._pc_badge = QLabel()
            self._pc_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pc_top.addWidget(self._pc_badge)
            pc_layout.addLayout(pc_top)
            pc_desc = QLabel(
                "Keep GE-Proton as the default. Proton-CachyOS SLR is worth having as "
                "a second per-game runner for stubborn launchers, anti-cheat edge cases, "
                "and games where ProtonDB reports Cachy-specific success."
            )
            pc_desc.setObjectName("card-copy")
            pc_desc.setWordWrap(True)
            pc_layout.addWidget(pc_desc)
            self._pc_version_lbl = QLabel()
            self._pc_version_lbl.setObjectName("card-copy")
            pc_layout.addWidget(self._pc_version_lbl)
            pc_btns = QHBoxLayout()
            pc_btns.setSpacing(10)
            pc_open = QPushButton("Open ProtonUp-Qt")
            pc_open.clicked.connect(lambda _=False: self._open_protonupqt())
            pc_btns.addWidget(pc_open)
            pc_docs = QPushButton("Open CachyOS Guide")
            pc_docs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://wiki.cachyos.org/configuration/gaming/")))
            pc_btns.addWidget(pc_docs)
            pc_btns.addStretch()
            pc_layout.addLayout(pc_btns)
            pc_note = QLabel(
                "In ProtonUp-Qt, add a Steam compatibility tool and choose Proton-CachyOS SLR. "
                "Restart Steam, then select it per-game under Properties -> Compatibility."
            )
            pc_note.setObjectName("card-copy")
            pc_note.setWordWrap(True)
            pc_layout.addWidget(pc_note)
            self._add(pc_card)

            # ── vkBasalt ──────────────────────────────────────────────────────
            vk_card, vk_layout = _make_card()
            vk_top = QHBoxLayout()
            vk_title = QLabel("vkBasalt — Vulkan Post-Processing")
            vk_title.setObjectName("card-title")
            vk_top.addWidget(vk_title)
            vk_top.addStretch()
            self._vk_badge = QLabel()
            self._vk_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vk_top.addWidget(self._vk_badge)
            vk_layout.addLayout(vk_top)
            vk_desc = QLabel(
                "Adds post-processing to any Vulkan game: CAS sharpening (default), SMAA, "
                "FXAA, or debanding. Only active when explicitly enabled per-game. "
                "Config: /etc/vkBasalt.conf  ·  toggle key: Home."
            )
            vk_desc.setObjectName("card-copy")
            vk_desc.setWordWrap(True)
            vk_layout.addWidget(vk_desc)
            vk_opts = QHBoxLayout()
            vk_opts.setSpacing(10)
            vk_opts.addWidget(_launch_opt_label("Steam launch option:"))
            vk_opts.addWidget(_launch_opt_value("ENABLE_VKBASALT=1 %command%"))
            vk_copy = QPushButton("Copy")
            vk_copy.clicked.connect(lambda: _copy_text("ENABLE_VKBASALT=1 %command%"))
            vk_opts.addWidget(vk_copy)
            vk_opts.addStretch()
            vk_layout.addLayout(vk_opts)
            self._add(vk_card)

            # ── Combos quick reference ─────────────────────────────────────────
            self._divider()
            combo_head = QLabel("Combining tools")
            combo_head.setObjectName("card-title")
            self._add(combo_head)
            combo_sub = QLabel(
                "These launch options can be stacked freely. "
                "A good all-rounder for most games:"
            )
            combo_sub.setObjectName("card-copy")
            combo_sub.setWordWrap(True)
            self._add(combo_sub)
            combo_txt = QTextEdit()
            combo_txt.setReadOnly(True)
            combo_txt.setMinimumHeight(160)
            combo_txt.setPlainText(
                "# All-rounder: MangoHud overlay + Gamescope compositor\n"
                "kyth-gamescope quality -- %command%\n\n"
                "# Same but with HDR (requires HDR display)\n"
                "kyth-gamescope hdr -- %command%\n\n"
                "# Add CAS sharpening via vkBasalt\n"
                "kyth-gamescope sharp -- %command%\n\n"
                "# GameMode + performance profile (CPU/GPU governors, renice)\n"
                "ujust game-performance -- %command%"
            )
            self._add(combo_txt)

        self._active_gaming_section = "migration"
        # ── Steam Library Migration ────────────────────────────────────────────
        self._divider()
        migrate_head = QLabel("Steam Library — Migrate from another system")
        migrate_head.setObjectName("heading")
        migrate_head.setStyleSheet("font-size: 18px; font-weight: 700; color: #ffffff;")
        self._add(migrate_head)
        migrate_sub = QLabel(
            "Dual-booting? Use this tool to copy your Steam library from a other system "
            "NTFS partition directly into Steam on KythOS. The drive is mounted "
            "read-only — your original install is never modified."
        )
        migrate_sub.setObjectName("card-copy")
        migrate_sub.setWordWrap(True)
        self._add(migrate_sub)

        hibernate_warn = QLabel(
            "⚠  Before scanning: boot the other system and do a full Shut Down (not Restart). "
            "other system Fast Startup leaves NTFS volumes in a hibernated state — Linux "
            "can read them safely read-only, but other system may report errors on resume "
            "if any other tool writes to the partition. This tool never writes to it."
        )
        hibernate_warn.setObjectName("card-copy")
        hibernate_warn.setWordWrap(True)
        hibernate_warn.setStyleSheet("color: #f0a500; padding: 6px 0;")
        self._add(hibernate_warn)

        migrate_card, migrate_layout = _make_card()

        # Drive selection
        drive_row = QHBoxLayout()
        drive_row.setSpacing(8)
        drive_lbl = QLabel("PC drive:")
        drive_lbl.setObjectName("card-copy")
        drive_row.addWidget(drive_lbl)
        self._drive_combo = QComboBox()
        self._drive_combo.setMinimumWidth(280)
        drive_row.addWidget(self._drive_combo)
        migrate_refresh_btn = QPushButton("Refresh")
        migrate_refresh_btn.clicked.connect(self._refresh_ntfs_drives)
        drive_row.addWidget(migrate_refresh_btn)
        migrate_scan_btn = QPushButton("Scan for Steam")
        migrate_scan_btn.setObjectName("primary")
        migrate_scan_btn.clicked.connect(self._scan_steam_on_drive)
        drive_row.addWidget(migrate_scan_btn)
        drive_row.addStretch()
        migrate_layout.addLayout(drive_row)

        self._migrate_found_lbl = QLabel("Select a drive above and click Scan for Steam.")
        self._migrate_found_lbl.setObjectName("card-copy")
        self._migrate_found_lbl.setWordWrap(True)
        migrate_layout.addWidget(self._migrate_found_lbl)

        self._lib_combo = QComboBox()
        self._lib_combo.setMinimumWidth(400)
        self._lib_combo.hide()
        migrate_layout.addWidget(self._lib_combo)

        # Per-game readiness for the scanned game library — answers
        # "can I play *my* games?" before any copying happens.
        check_row = QHBoxLayout()
        check_row.setSpacing(8)
        self._winlib_check_btn = QPushButton("Check My Games")
        self._winlib_check_btn.hide()
        self._winlib_check_btn.clicked.connect(self._check_windows_library_compat)
        check_row.addWidget(self._winlib_check_btn)
        check_row.addStretch()
        migrate_layout.addLayout(check_row)
        self._winlib_summary_lbl = QLabel()
        self._winlib_summary_lbl.setObjectName("card-copy")
        self._winlib_summary_lbl.setWordWrap(True)
        self._winlib_summary_lbl.hide()
        migrate_layout.addWidget(self._winlib_summary_lbl)
        self._winlib_rows = QVBoxLayout()
        self._winlib_rows.setSpacing(6)
        migrate_layout.addLayout(self._winlib_rows)
        self._winlib_games: list[dict] = []
        self._winlib_protondb_worker: _ProtonDbBatchWorker | None = None

        # Destination
        dst_row = QHBoxLayout()
        dst_row.setSpacing(8)
        dst_lbl = QLabel("Copy to:")
        dst_lbl.setObjectName("card-copy")
        dst_row.addWidget(dst_lbl)
        self._migrate_dst_edit = QLineEdit(
            os.path.expanduser("~/.local/share/Steam/steamapps")
        )
        dst_row.addWidget(self._migrate_dst_edit, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_migrate_dst)
        dst_row.addWidget(browse_btn)
        migrate_layout.addLayout(dst_row)

        # Copy controls
        copy_btn_row = QHBoxLayout()
        copy_btn_row.setSpacing(8)
        self._copy_btn = QPushButton("Copy Library")
        self._copy_btn.setObjectName("primary")
        self._copy_btn.setEnabled(False)
        self._copy_btn.clicked.connect(self._start_steam_copy)
        copy_btn_row.addWidget(self._copy_btn)
        self._copy_cancel_btn = QPushButton("Cancel")
        self._copy_cancel_btn.hide()
        self._copy_cancel_btn.clicked.connect(self._cancel_steam_copy)
        copy_btn_row.addWidget(self._copy_cancel_btn)
        copy_btn_row.addStretch()
        migrate_layout.addLayout(copy_btn_row)

        self._migrate_status = QLabel()
        self._migrate_status.setObjectName("subheading")
        self._migrate_status.hide()
        migrate_layout.addWidget(self._migrate_status)

        self._migrate_progress = QProgressBar()
        self._migrate_progress.setRange(0, 0)
        self._migrate_progress.hide()
        migrate_layout.addWidget(self._migrate_progress)

        self._migrate_log_toggle = QPushButton("Show details")
        self._migrate_log_toggle.setCheckable(True)
        self._migrate_log_toggle.hide()
        self._migrate_log_toggle.clicked.connect(
            lambda checked: _set_log_panel(self._migrate_log_toggle, self._migrate_log, checked)
        )
        migrate_layout.addWidget(self._migrate_log_toggle)

        self._migrate_log = QTextEdit()
        self._migrate_log.setReadOnly(True)
        self._migrate_log.setMaximumHeight(140)
        self._migrate_log.hide()
        migrate_layout.addWidget(self._migrate_log)

        self._add(migrate_card)
        self._migrate_worker = None
        self._scanned_mount = None

        # ── Save backup / restore ─────────────────────────────────────────────
        self._divider()
        saves_card, saves_layout = _make_card("card-accent-ok")
        saves_title = QLabel("Game Saves — Back Up Before You Switch")
        saves_title.setObjectName("card-title")
        saves_layout.addWidget(saves_title)
        saves_desc = QLabel(
            "KythOS recommends Ludusavi for game save backup and restore. Run it "
            "before a other system migration, after importing a library, and before "
            "large modding sessions."
        )
        saves_desc.setObjectName("card-copy")
        saves_desc.setWordWrap(True)
        saves_layout.addWidget(saves_desc)
        self._saves_status_lbl = QLabel("")
        self._saves_status_lbl.setObjectName("card-copy")
        self._saves_status_lbl.setWordWrap(True)
        saves_layout.addWidget(self._saves_status_lbl)
        saves_btns = QHBoxLayout()
        saves_btns.setSpacing(8)
        ludusavi_btn = QPushButton("Install Ludusavi")
        ludusavi_btn.clicked.connect(lambda _=False, b=ludusavi_btn: _install_flatpak_inline(
            self, b, "com.github.mtkennerly.ludusavi", "Ludusavi"))
        saves_btns.addWidget(ludusavi_btn)
        ludusavi_open_btn = QPushButton("Open Ludusavi")
        ludusavi_open_btn.clicked.connect(lambda _=False: subprocess.Popen(["flatpak", "run", "com.github.mtkennerly.ludusavi"]))
        saves_btns.addWidget(ludusavi_open_btn)
        saves_refresh_btn = QPushButton("Refresh Status")
        saves_refresh_btn.clicked.connect(self._refresh_gaming_dashboard)
        saves_btns.addWidget(saves_refresh_btn)
        saves_doc_btn = QPushButton("Save Migration Checklist")
        saves_doc_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/mrtrick37/kyth/blob/main/docs/game-save-migration.md")))
        saves_btns.addWidget(saves_doc_btn)
        saves_btns.addStretch()
        saves_layout.addLayout(saves_btns)
        self._add(saves_card)

        # ── Modding migration ────────────────────────────────────────────────
        mods_card, mods_layout = _make_card()
        mods_title = QLabel("Mods — Nexus, MO2, SteamTinkerLaunch")
        mods_title.setObjectName("card-title")
        mods_layout.addWidget(mods_title)
        mods_desc = QLabel(
            "Start with Steam Workshop and native mod managers when a game provides "
            "them. For Bethesda-style load orders, use SteamTinkerLaunch to install "
            "Mod Organizer 2 per game; use Bottles for standalone patchers and tools."
        )
        mods_desc.setObjectName("card-copy")
        mods_desc.setWordWrap(True)
        mods_layout.addWidget(mods_desc)
        mods_btns = QHBoxLayout()
        mods_btns.setSpacing(8)
        protonup_btn = QPushButton("Open ProtonUp-Qt")
        protonup_btn.clicked.connect(lambda _=False: self._open_protonupqt())
        mods_btns.addWidget(protonup_btn)
        bottles_btn = QPushButton("Install Bottles")
        bottles_btn.clicked.connect(lambda _=False, b=bottles_btn: _install_flatpak_inline(
            self, b, "com.usebottles.bottles", "Bottles"))
        mods_btns.addWidget(bottles_btn)
        mods_doc_btn = QPushButton("Modding Guide")
        mods_doc_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/mrtrick37/kyth/blob/main/docs/modding-on-kythos.md")))
        mods_btns.addWidget(mods_doc_btn)
        mods_btns.addStretch()
        mods_layout.addLayout(mods_btns)
        self._add(mods_card)

        self._active_gaming_section = None
        self._stretch()
        self._switch_gaming_section(self._current_gaming_section)
        self._update_profile_builder()
        self._set_rows_loading(self._checklist_rows_layout, "Checking first-week setup items…")
        self._set_rows_loading(self._health_rows_layout, "Checking launchers, Vulkan, Proton, controllers, and game drives…")
        self._set_rows_loading(self._streaming_rows_layout, "Checking Discord, OBS, capture, audio, and camera tools…")
        self._saves_status_lbl.setText("Scanning save backup tools…")
        QTimer.singleShot(0, self._refresh_gaming_dashboard)
        QTimer.singleShot(80, self._refresh_status)
        self._refresh_ntfs_drives()

    # ── Tool tile builder ──────────────────────────────────────────────────────

    def _copy_option_row(self, label: str, opt: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(_launch_opt_label(label))
        row.addWidget(_launch_opt_value(opt))
        cp = QPushButton("Copy")
        cp.clicked.connect(lambda _=False, t=opt: _copy_text(t))
        row.addWidget(cp)
        row.addStretch()
        return row

    def _start_game_night(self):
        if self._game_night_inhibit and self._game_night_inhibit.poll() is None:
            return
        subprocess.Popen(["kyth-performance-mode", "save"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(["kyth-performance-mode", "gaming"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if shutil.which("systemd-inhibit"):
            self._game_night_inhibit = subprocess.Popen(
                ["systemd-inhibit", "--what=idle:sleep", "--why=KythOS Game Night Mode", "sleep", "14400"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
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
        if self._game_night_inhibit and self._game_night_inhibit.poll() is None:
            self._game_night_inhibit.terminate()
        subprocess.Popen(["kyth-performance-mode", "restore"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

    def _update_profile_builder(self):
        if not hasattr(self, "_profile_launch_value"):
            return
        goal = self._profile_goal_combo.currentData() or "quality"
        fps = self._profile_fps_combo.currentData() or ""
        fps_arg = f" --fps {fps}" if fps else ""
        launch_options = {
            "quality": f"kyth-gamescope quality{fps_arg} -- %command%",
            "hdr": f"kyth-gamescope hdr{fps_arg} -- %command%",
            "sharp": f"kyth-gamescope sharp --fsr{fps_arg} -- %command%",
            "latency": f"game-performance --profile gaming -- kyth-gamescope latency{fps_arg} -- %command%",
            "troubleshoot": "PROTON_LOG=1 PROTON_NO_NTSYNC=1 %command%",
        }
        self._profile_launch_value.setText(launch_options.get(goal, launch_options["quality"]))

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

    def _migration_checklist_items(self) -> list[tuple[str, str, str]]:
        return _gaming_migration_checklist_items()

    def _refresh_migration_checklist(self):
        self._set_rows_loading(self._checklist_rows_layout, "Checking first-week setup items…")
        self._start_data_worker("checklist", _gaming_migration_checklist_items)

    def _render_migration_checklist(self, items: list[tuple[str, str, str]]):
        self._clear_rows(self._checklist_rows_layout)
        for status, title, summary in items:
            self._checklist_rows_layout.addWidget(self._make_health_row(status, title, summary))

    def _refresh_streaming_health(self):
        self._set_rows_loading(self._streaming_rows_layout, "Checking Discord, OBS, capture, audio, and camera tools…")
        self._start_data_worker("streaming", _streaming_health_items)

    def _render_streaming_health(self, items: list[tuple[str, str, str]]):
        self._clear_rows(self._streaming_rows_layout)
        for status, title, summary in items:
            self._streaming_rows_layout.addWidget(self._make_health_row(status, title, summary))

    def _fix_discord_screenshare(self):
        self._discord_fix_btn.setEnabled(False)
        cmd = [
            "bash", "-c",
            "flatpak override --user com.discordapp.Discord "
            "--env=ELECTRON_OZONE_PLATFORM_HINT=auto "
            "--socket=wayland --socket=fallback-x11 --device=dri "
            "--talk-name=org.freedesktop.portal.Desktop "
            "--talk-name=org.kde.StatusNotifierWatcher",
        ]
        self._discord_fix_status.hide()
        self._discord_fix_result.set_running("Applying Discord screen share repair…", self._command_details(cmd))
        try:
            result = subprocess.run(cmd, timeout=10, capture_output=True)
            if result.returncode == 0:
                self._discord_fix_result.set_result(
                    "ok",
                    "Applied. Restart Discord to take effect.",
                    self._command_details(cmd, result),
                )
            else:
                err = result.stderr.decode("utf-8", errors="replace").strip()
                self._discord_fix_result.set_result(
                    "err",
                    f"Could not repair Discord screen share: {err or 'unknown error'}.",
                    self._command_details(cmd, result),
                )
        except Exception as exc:
            self._discord_fix_result.set_result(
                "err",
                f"Could not repair Discord screen share: {exc}.",
                self._command_details(cmd, exc=exc),
            )
        finally:
            self._discord_fix_btn.setEnabled(True)

    def _fix_obs_pipewire(self):
        self._obs_fix_btn.setEnabled(False)
        cmd = [
            "bash", "-c",
            "flatpak override --user com.obsproject.Studio "
            "--socket=wayland --socket=pulseaudio --device=dri "
            "--talk-name=org.freedesktop.portal.Desktop",
        ]
        self._obs_fix_status.hide()
        self._obs_fix_result.set_running("Applying OBS capture repair…", self._command_details(cmd))
        try:
            result = subprocess.run(cmd, timeout=10, capture_output=True)
            if result.returncode == 0:
                self._obs_fix_result.set_result(
                    "ok",
                    "Applied. Restart OBS to take effect.",
                    self._command_details(cmd, result),
                )
            else:
                err = result.stderr.decode("utf-8", errors="replace").strip()
                self._obs_fix_result.set_result(
                    "err",
                    f"Could not repair OBS capture: {err or 'unknown error'}.",
                    self._command_details(cmd, result),
                )
        except Exception as exc:
            self._obs_fix_result.set_result(
                "err",
                f"Could not repair OBS capture: {exc}.",
                self._command_details(cmd, exc=exc),
            )
        finally:
            self._obs_fix_btn.setEnabled(True)

    def _refresh_save_status(self):
        if not hasattr(self, "_saves_status_lbl"):
            return
        self._saves_status_lbl.setText("Scanning save backup tools…")
        self._start_data_worker("saves", _ludusavi_backup_summary)

    def _render_save_status(self, data):
        if not hasattr(self, "_saves_status_lbl") or not data:
            return
        status, title, summary = data
        prefix = {
            "ok": "Ready",
            "warn": "Needs setup",
            "err": "Needs fix",
            "dim": "Optional",
        }.get(status, "Optional")
        self._saves_status_lbl.setText(f"{prefix}: {title} - {summary}")

    def _make_my_game_row(self, game_info: dict, protondb_tier: str = "") -> QFrame:
        compat = self._find_compat_game(game_info.get("name", ""))
        if compat is None:
            status = "dim"
            status_text = "Unknown"
            summary = "Not in curated list. ProtonDB rating shown when available."
            profile = "kyth-gamescope quality -- %command%"
        else:
            status = "ok" if compat.status in ("native", "proton") else "warn" if compat.status == "tweaks" else "err"
            status_text = {
                "native": "Native",
                "proton": "Works",
                "tweaks": "Tweaks",
                "blocked": "Blocked",
            }.get(compat.status, compat.status)
            summary = f"{compat.note} Checked {compat.checked} via {compat.source}."
            profile = self._recommended_profile_for_game(compat)

        row = QFrame()
        row.setObjectName("hw-card-dim")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        name_lbl = QLabel(game_info.get("name", "Unknown game"))
        name_lbl.setObjectName("card-summary")
        name_lbl.setStyleSheet("font-size:13px; font-weight:700;")
        top.addWidget(name_lbl, 1)
        launcher_lbl = QLabel(f"  {game_info.get('launcher', 'Unknown')}  ")
        launcher_lbl.setStyleSheet("font-size:10px; font-weight:600; border-radius:3px; padding:1px 6px; background:#252526; color:#cccccc; border:1px solid #3c3c3c;")
        top.addWidget(launcher_lbl)
        badge = QLabel(f"  {status_text}  ")
        badge_bg, badge_fg = {
            "ok": ("#121e2d", "#4fc1ff"),
            "warn": ("#241808", "#fbbf24"),
            "err": ("#3a1010", "#f48771"),
            "dim": ("#252526", "#858585"),
        }.get(status, ("#252526", "#858585"))
        badge.setStyleSheet(f"background:{badge_bg}; color:{badge_fg}; border:1px solid {badge_fg}; border-radius:3px; padding:2px 8px; font-size:11px; font-weight:700;")
        top.addWidget(badge)
        if compat is not None and compat.status == "blocked" and compat.anticheat and compat.anticheat.lower() not in ("none", ""):
            ac_badge = QLabel(f"  ⛔ {compat.anticheat}  ")
            ac_badge.setToolTip(
                f"Blocked by {compat.anticheat} anti-cheat — not supported on Linux. "
                "No workaround exists; this game requires other system."
            )
            ac_badge.setStyleSheet(
                "background:#3a1010; color:#f48771; border:1px solid #f48771;"
                " border-radius:3px; padding:2px 8px; font-size:11px; font-weight:700;"
            )
            top.addWidget(ac_badge)
        tier = protondb_tier.lower().strip()
        if tier and game_info.get("launcher") == "Steam":
            tier_bg, tier_fg = _PROTONDB_TIER_STYLE.get(tier, ("#252526", "#858585"))
            pdb_badge = QLabel(f"  PDB: {tier.capitalize()}  ")
            pdb_badge.setToolTip(f"ProtonDB community rating: {tier.capitalize()}")
            pdb_badge.setStyleSheet(
                f"background:{tier_bg}; color:{tier_fg}; border:1px solid {tier_fg};"
                " border-radius:3px; padding:2px 8px; font-size:11px; font-weight:700;"
            )
            top.addWidget(pdb_badge)
        layout.addLayout(top)

        detail = QLabel(
            f"{summary}\n"
            f"Profile: {profile}\n"
            f"Path: {game_info.get('path') or 'unknown'}"
        )
        detail.setObjectName("card-copy")
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(detail)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        copy_profile = QPushButton("Copy Profile")
        copy_profile.clicked.connect(lambda _=False, text=profile: _copy_text(text))
        btns.addWidget(copy_profile)
        path = game_info.get("path", "")
        if path:
            open_path = QPushButton("Open Folder")
            open_path.clicked.connect(lambda _=False, p=path: self._open_user_path(p))
            btns.addWidget(open_path)
        btns.addStretch()
        layout.addLayout(btns)
        return row

    def _refresh_my_games(self, async_scan: bool = False):
        self._clear_rows(self._my_games_rows_layout)
        self._my_games_summary_lbl.setText("Scanning installed game libraries…")
        if async_scan:
            self._start_data_worker("games", _detect_installed_games)
            return
        self._render_my_games(_detect_installed_games())

    def _render_my_games(self, games: list[dict], cache: dict[str, str] | None = None):
        self._last_detected_games = games
        self._clear_rows(self._my_games_rows_layout)
        if not games:
            self._my_games_summary_lbl.setText(
                "No installed games detected yet. Install a game in Steam, Heroic, Lutris, or Bottles, then scan again."
            )
            return

        if cache is None:
            cache = _load_protondb_cache()

        matched = sum(1 for game in games if self._find_compat_game(game.get("name", "")))
        by_launcher: dict[str, int] = {}
        for game in games:
            launcher = game.get("launcher", "Unknown")
            by_launcher[launcher] = by_launcher.get(launcher, 0) + 1
        launcher_summary = ", ".join(f"{name}: {count}" for name, count in sorted(by_launcher.items()))
        self._my_games_summary_lbl.setText(
            f"Detected {len(games)} installed item(s); {matched} matched KythOS compatibility data. {launcher_summary}"
        )

        for game in games[:20]:
            appid = game.get("appid", "")
            tier = cache.get(appid, "") if appid else ""
            self._my_games_rows_layout.addWidget(self._make_my_game_row(game, tier))
        if len(games) > 20:
            more = QLabel(f"{len(games) - 20} more detected. Showing the first 20 to keep the dashboard fast.")
            more.setObjectName("card-copy")
            self._my_games_rows_layout.addWidget(more)

        uncached = [
            g.get("appid", "") for g in games
            if g.get("launcher") == "Steam" and g.get("appid") and g.get("appid") not in cache
        ]
        if uncached and (self._protondb_worker is None or not self._protondb_worker.isRunning()):
            self._protondb_worker = _ProtonDbBatchWorker(uncached, cache)
            self._protondb_worker.finished_all.connect(self._on_protondb_done)
            _release_worker_when_finished(self, "_protondb_worker", self._protondb_worker)
            self._protondb_worker.start()

    def _on_protondb_done(self, full_cache: dict):
        _save_protondb_cache(full_cache)
        if self._last_detected_games:
            self._render_my_games(self._last_detected_games, full_cache)

    def _find_compat_game(self, query: str):
        needle = query.strip().lower()
        if not needle:
            return None
        for game in _COMPAT_GAMES:
            if game.name.lower() == needle:
                return game
        for game in _COMPAT_GAMES:
            if needle in game.name.lower() or game.name.lower() in needle:
                return game
        return None

    def _recommended_launcher_for_game(self, game) -> str:
        name = game.name.lower()
        if "overwatch" in name:
            return "Lutris with Battle.net via umu-run"
        if any(token in name for token in ("red dead", "gta")):
            return "Steam when owned there; otherwise Lutris/Heroic plus the Rockstar launcher"
        if game.status == "blocked":
            return "None on Linux until the publisher enables support"
        if game.status == "native":
            return "Steam native Linux build"
        return "Steam with Proton Experimental first, then GE-Proton"

    def _recommended_profile_for_game(self, game) -> str:
        if game.status == "blocked":
            return "Do not try bypass launch options; use other system or wait for publisher support."
        if any(token in game.name.lower() for token in ("cyberpunk", "red dead", "hogwarts")):
            return "kyth-gamescope quality -- %command%"
        if game.anticheat in ("EAC", "BattlEye", "VAC", "Warden"):
            return "game-performance --profile gaming -- %command%"
        return "kyth-gamescope quality -- %command%"

    def _check_game_readiness(self):
        query = self._readiness_combo.currentText()
        game = self._find_compat_game(query)
        if game is None:
            encoded = urlencode({"q": query.strip() or "game"})
            self._readiness_result.setText(
                "Not in the KythOS curated list yet. Check ProtonDB and Are We Anti-Cheat Yet, "
                f"then record the result in docs/gaming-results/. Search: https://www.protondb.com/search?{encoded}"
            )
            return

        status_label = {
            "native": "Native Linux",
            "proton": "Works via Proton",
            "tweaks": "Works with tweaks",
            "blocked": "Blocked by publisher/anti-cheat",
        }.get(game.status, game.status)
        save_note = (
            "Back up saves with Ludusavi before migrating or modding."
            if game.status != "blocked"
            else "Do not migrate saves until the game has a supported Linux path."
        )
        mod_note = (
            "Use the Modding guide before applying other system mod managers."
            if game.status != "blocked"
            else "Modding is irrelevant while the game is blocked."
        )
        self._readiness_result.setText(
            f"{game.name}: {status_label}\n"
            f"Anti-cheat/middleware: {game.anticheat}\n"
            f"Launcher: {self._recommended_launcher_for_game(game)}\n"
            f"Runner/profile: {self._recommended_profile_for_game(game)}\n"
            f"Saves: {save_note}\n"
            f"Mods: {mod_note}\n"
            f"Checked: {game.checked} via {game.source}\n"
            f"{game.note}"
        )

    def _open_readiness_protondb(self):
        query = self._readiness_combo.currentText().strip()
        if query:
            QDesktopServices.openUrl(QUrl(f"https://www.protondb.com/search?{urlencode({'q': query})}"))
        else:
            QDesktopServices.openUrl(QUrl("https://www.protondb.com"))

    def _open_user_path(self, path: str):
        expanded = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(expanded):
            self._set_status_badge(self._fix_status_lbl, "warn", f"Folder not found yet: {expanded}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(expanded))
        self._set_status_badge(self._fix_status_lbl, "ok", f"Opened {expanded}")

    def _copy_prefix_reset_hint(self):
        text = (
            "# Replace APPID with the Steam app id. This moves the Proton prefix aside as a backup.\n"
            "mv ~/.local/share/Steam/steamapps/compatdata/APPID "
            "~/.local/share/Steam/steamapps/compatdata/APPID.bak-$(date +%Y%m%d-%H%M%S)"
        )
        _copy_text(text)
        self._set_status_badge(
            self._fix_status_lbl,
            "ok",
            "Copied a safe Proton prefix reset command with an APPID placeholder.",
        )

    def _copy_support_snapshot_command(self):
        text = "kyth-device-info | tee ~/kyth-device-info.txt"
        _copy_text(text)
        self._set_status_badge(self._fix_status_lbl, "ok", "Copied support snapshot command.")

    def _install_obs_inline(self, btn: QPushButton):
        # ujust install-obs also enables obs-vkcapture; mirror that here.
        _install_flatpak_inline(
            self, btn, "com.obsproject.Studio", "OBS Studio",
            extra_cmd="flatpak override --user --env=OBS_VKCAPTURE=1 com.obsproject.Studio || true",
        )

    def _make_tool_tile(self, tool: dict) -> tuple[QFrame, dict]:
        card, layout = _make_card()
        layout.setSpacing(8)

        name_lbl = QLabel(tool["name"])
        name_lbl.setObjectName("card-title")
        layout.addWidget(name_lbl)

        desc_lbl = QLabel(tool["desc"])
        desc_lbl.setObjectName("card-copy")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        install_btn = QPushButton("Install")
        install_btn.clicked.connect(
            lambda _=False, t=tool: self._install_tool(t)
        )
        btn_row.addWidget(install_btn)
        launch_btn = QPushButton("Launch")
        launch_btn.hide()
        launch_btn.clicked.connect(
            lambda _=False, cmd=tool["launch"]: subprocess.Popen(cmd)
        )
        btn_row.addWidget(launch_btn)
        uninstall_btn = QPushButton("Uninstall")
        uninstall_btn.setObjectName("danger")
        uninstall_btn.hide()
        uninstall_btn.clicked.connect(
            lambda _=False, t=tool: self._uninstall_tool(t)
        )
        btn_row.addWidget(uninstall_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.hide()
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        status_lbl = QLabel()
        status_lbl.setObjectName("subheading")
        status_lbl.hide()
        layout.addWidget(status_lbl)

        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.hide()
        layout.addWidget(progress)

        log_toggle = QPushButton("Show details")
        log_toggle.setCheckable(True)
        log_toggle.hide()
        layout.addWidget(log_toggle)

        log = QTextEdit()
        log.setReadOnly(True)
        log.setMaximumHeight(100)
        log.hide()
        layout.addWidget(log)

        log_toggle.clicked.connect(lambda checked, lt=log_toggle, lg=log: _set_log_panel(lt, lg, checked))

        refs = {
            "tool": tool, "install": install_btn, "launch": launch_btn, "uninstall": uninstall_btn,
            "cancel": cancel_btn, "status": status_lbl, "progress": progress,
            "log_toggle": log_toggle, "log": log,
        }
        cancel_btn.clicked.connect(lambda _=False, r=refs: self._cancel_tool_operation(r))
        return card, refs

    # ── Status ─────────────────────────────────────────────────────────────────

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

        gp_ver = _ge_proton_version()
        _apply_install_badge(self._gp_badge, bool(gp_ver), ok_text=gp_ver or "Installed")
        self._gp_version_lbl.setText(
            f"Installed: {gp_ver}" if gp_ver
            else "GE-Proton not found in compatibilitytools.d"
        )

        if hasattr(self, "_pc_badge"):
            pc_ver = _compat_tool_version("proton-cachyos")
            _apply_install_badge(self._pc_badge, bool(pc_ver), ok_text=pc_ver or "Installed", warn_text="Optional")
            self._pc_version_lbl.setText(
                f"Installed: {pc_ver}" if pc_ver
                else "Not installed. Optional fallback runner; GE-Proton remains the recommended default."
            )

        for refs in self._tool_refs:
            installed = _is_flatpak_installed(refs["tool"]["flatpak"])
            refs["install"].setVisible(not installed)
            refs["launch"].setVisible(installed)
            refs["uninstall"].setVisible(installed)

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if not self._dashboard_loaded and "dashboard" not in self._data_workers:
            self._refresh_gaming_dashboard()
        QTimer.singleShot(80, self._refresh_status)
        if not self._win_lib_probed:
            self._win_lib_probed = True
            worker = WindowsLibraryWorker()
            self._win_lib_worker = worker
            worker.result.connect(self._on_win_lib_result)
            _release_worker_when_finished(self, "_win_lib_worker", worker)
            worker.start()

    def _on_win_lib_result(self, partitions: list) -> None:
        if not partitions:
            return

        # Clear any previous content
        while self._win_lib_layout.count():
            item = self._win_lib_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        any_dirty = any(p["is_dirty"] or p["is_hibernated"] for p in partitions)
        any_clean = any(not p["is_dirty"] and not p["is_hibernated"] for p in partitions)

        title_lbl = QLabel("other system Drive Detected")
        title_lbl.setObjectName("card-title")
        self._win_lib_layout.addWidget(title_lbl)

        if any_dirty:
            self._win_lib_card.setObjectName("card-accent-err")
            _restyle(self._win_lib_card)
            warn = QLabel(
                "⚠  Your system partition is in a hibernated or dirty state — "
                "this means other system used Fast Startup or wasn't shut down cleanly.\n\n"
                "To safely import your games:\n"
                "  1.  Boot into other system\n"
                "  2.  Open Start → Settings → System → Power & Sleep → Additional power settings\n"
                "  3.  Click \"Choose what the power buttons do\" → \"Turn on fast startup\" — disable it\n"
                "  4.  Do a full Shut Down (not Restart)\n"
                "  5.  Come back to KythOS and use the Steam Library tool below"
            )
            warn.setObjectName("card-copy")
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #d4a843;")
            self._win_lib_layout.addWidget(warn)

        if any_clean:
            self._win_lib_card.setObjectName("card-accent-ok")
            _restyle(self._win_lib_card)
            found_any_steam = any(p["steam_paths"] for p in partitions if not p["is_dirty"])
            if found_any_steam:
                msg = QLabel(
                    "✓  Your Steam library was found on this drive.\n"
                    "Use the Steam Library tool below to copy your games to KythOS — "
                    "the drive is accessed read-only, your original install is never touched."
                )
            else:
                msg = QLabel(
                    "✓  A clean PC drive is available.\n"
                    "Use the Steam Library tool below to scan it and copy games to KythOS."
                )
            msg.setObjectName("card-copy")
            msg.setWordWrap(True)
            self._win_lib_layout.addWidget(msg)

        self._win_lib_card.show()

    # ── Tool install ───────────────────────────────────────────────────────────

    def _open_protonupqt(self):
        if _is_flatpak_installed("net.davidotek.pupgui2"):
            subprocess.Popen(["flatpak", "run", "net.davidotek.pupgui2"])
            return
        btn = self.sender()
        if not isinstance(btn, QPushButton):
            btn = QPushButton()

        def _launch_when_done(code: int):
            if code == 0:
                subprocess.Popen(["flatpak", "run", "net.davidotek.pupgui2"])

        _install_flatpak_inline(
            self, btn, "net.davidotek.pupgui2", "ProtonUp-Qt", done_cb=_launch_when_done,
        )

    def _open_corectrl(self):
        if shutil.which("corectrl"):
            subprocess.Popen(["corectrl"])
            return
        QMessageBox.information(
            self,
            "CoreCtrl",
            "CoreCtrl is not installed in this image. Use LACT for AMD GPU tuning, or rebuild with CoreCtrl available in the package repos.",
        )

    def _copy_opticscaler_launch_opt(self, btn: QPushButton):
        _copy_text('WINEDLLOVERRIDES="nvngx=n,b" %command%')
        btn.setText("Copied!")
        QTimer.singleShot(2000, lambda: btn.setText("Copy Launch Option"))

    def _deploy_opticscaler(self, btn: QPushButton):
        if self._opticscaler_worker and self._opticscaler_worker.isRunning():
            return
        game_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Game Directory",
            str(Path.home() / ".local/share/Steam/steamapps/common"),
        )
        if not game_dir:
            return
        btn.setEnabled(False)
        self._opti_log.clear()
        self._opti_log.append(f"→ ujust deploy-opticscaler '{game_dir}'\n")
        self._opti_log.show()
        self._opti_status_lbl.setText("Deploying OptiScaler…")
        self._opti_status_lbl.setObjectName("subheading")
        self._opti_status_lbl.show()
        _restyle(self._opti_status_lbl)
        cmd = ["ujust", "deploy-opticscaler", game_dir]
        self._opticscaler_worker = Worker(cmd)
        self._opticscaler_worker.line.connect(lambda ln: (
            self._opti_log.append(ln),
            self._opti_log.ensureCursorVisible(),
        ))
        self._opticscaler_worker.done.connect(lambda code: self._on_opticscaler_done(code, btn))
        self._opticscaler_worker.start()

    def _on_opticscaler_done(self, code: int, btn: QPushButton):
        btn.setEnabled(True)
        _finish_worker(self, attr="_opticscaler_worker")
        if code == 0:
            self._opti_status_lbl.setText(
                "Deployed. Set Steam launch option: WINEDLLOVERRIDES=\"nvngx=n,b\" %command%"
            )
            self._opti_status_lbl.setObjectName("status-ok")
        else:
            self._opti_status_lbl.setText(f"Deploy failed (exit {code}). See output above.")
            self._opti_status_lbl.setObjectName("status-err")
        _restyle(self._opti_status_lbl)

    def _set_scx_scheduler(self, scheduler: str):
        if self._scx_worker and self._scx_worker.isRunning():
            return

        if scheduler == "stop":
            cmd = ["kyth-scx", "stop"]
            label = "Stopping sched-ext loader"
        else:
            cmd = ["kyth-scx", "set", scheduler]
            label = f"Switching sched-ext scheduler to {scheduler}"

        self._scx_log.clear()
        self._scx_log.append(f"→ {' '.join(cmd)}\n")
        self._scx_log_toggle.show()
        _set_log_panel(self._scx_log_toggle, self._scx_log, False)
        self._scx_progress.show()
        self._scx_status_lbl.setText(f"{label}…")
        self._scx_status_lbl.setObjectName("subheading")
        _restyle(self._scx_status_lbl)

        self._scx_worker = Worker(cmd)
        self._scx_worker.line.connect(lambda ln: (
            self._scx_log.append(ln),
            self._scx_log.ensureCursorVisible(),
        ))
        self._scx_worker.done.connect(lambda code: self._on_scx_done(code))
        self._scx_worker.start()

    def _on_scx_done(self, code: int):
        self._scx_progress.hide()
        _finish_worker(self, attr="_scx_worker")
        if code == 0:
            self._scx_status_lbl.setText("sched-ext updated.")
            self._scx_status_lbl.setObjectName("status-ok")
            self._scx_log.append("\nDone.")
        else:
            self._scx_status_lbl.setText(f"sched-ext update failed (exit {code}).")
            self._scx_status_lbl.setObjectName("status-err")
        _restyle(self._scx_status_lbl)
        self._refresh_status()

    def _open_heroic_for_epic(self):
        cmd = ["flatpak", "run", "com.heroicgameslauncher.hgl"]
        self._tool_log.clear()
        self._tool_log.append(f"→ {' '.join(cmd)}\n")
        self._tool_log.append("Heroic should open. Sign in to Epic Games there to install your library.")
        self._tool_log_toggle.show()
        _set_log_panel(self._tool_log_toggle, self._tool_log, False)
        self._tool_progress.hide()
        self._tool_op_status.setText("Opening Heroic Games Launcher…")
        self._tool_op_status.setObjectName("subheading")
        self._tool_op_status.show()
        _restyle(self._tool_op_status)

        try:
            subprocess.Popen(cmd)
            self._tool_op_status.setText("Heroic opened for Epic sign-in.")
            self._tool_op_status.setObjectName("status-ok")
            _restyle(self._tool_op_status)
        except Exception as exc:
            self._tool_log.append(f"\nFailed to start Heroic: {exc}")
            self._tool_op_status.setText("Failed to open Heroic.")
            self._tool_op_status.setObjectName("status-err")
            _restyle(self._tool_op_status)
            QMessageBox.warning(self, "Heroic Games Launcher", str(exc))

    def _prepare_epic_lutris_install(self) -> bool:
        prefix = os.path.expanduser("~/Games/epic-games-store")
        cache = os.path.expanduser("~/.cache/lutris/installer/epic-games-store")
        found_paths = [path for path in (prefix, cache) if os.path.exists(path)]
        if not found_paths:
            return True

        notes = []
        winetricks_log = os.path.join(prefix, "winetricks.log")
        if os.path.isfile(winetricks_log):
            try:
                with open(winetricks_log, "r", encoding="utf-8", errors="ignore") as fh:
                    if "corefonts" in fh.read():
                        notes.append("Winetricks already ran in the old Epic prefix (corefonts found).")
            except OSError:
                pass

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Reset old Epic installer state?")
        box.setText(
            "A previous Epic install attempt was found. Lutris/UMU can fail when it reuses a partial Epic prefix."
        )
        detail_lines = []
        detail_lines.extend(notes)
        detail_lines.extend([f"Found: {path}" for path in found_paths])
        detail_lines.append("")
        detail_lines.append("Choose 'Reset and Retry' to move the old state aside and reopen the installer.")
        box.setInformativeText("\n".join(detail_lines))
        reset_btn = box.addButton("Reset and Retry", QMessageBox.ButtonRole.AcceptRole)
        open_btn = box.addButton("Open Anyway", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(reset_btn)
        box.exec()

        clicked = box.clickedButton()
        if clicked == cancel_btn:
            self._tool_op_status.setText("Epic installer launch cancelled.")
            self._tool_op_status.setObjectName("subheading")
            self._tool_op_status.show()
            _restyle(self._tool_op_status)
            return False
        if clicked == open_btn:
            return True

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._tool_log.clear()
        self._tool_log.append("Preparing a clean Epic installer retry…\n")
        self._tool_log_toggle.show()
        _set_log_panel(self._tool_log_toggle, self._tool_log, False)
        for path in found_paths:
            backup = f"{path}.bak-{timestamp}"
            try:
                shutil.move(path, backup)
                self._tool_log.append(f"Moved {path} → {backup}")
            except Exception as exc:
                self._tool_log.append(f"Failed to move {path}: {exc}")
                self._tool_log_toggle.show()
                _set_log_panel(self._tool_log_toggle, self._tool_log, False)
                self._tool_op_status.setText("Epic installer reset failed.")
                self._tool_op_status.setObjectName("status-err")
                self._tool_op_status.show()
                _restyle(self._tool_op_status)
                QMessageBox.warning(
                    self,
                    "Epic installer reset",
                    f"Could not move {path}:\n{exc}"
                )
                return False

        self._tool_log.append("\nOld installer state was backed up. Relaunching Lutris…")
        self._tool_log_toggle.show()
        _set_log_panel(self._tool_log_toggle, self._tool_log, False)
        self._tool_op_status.setText("Old Epic installer state was backed up. Retrying…")
        self._tool_op_status.setObjectName("subheading")
        self._tool_op_status.show()
        _restyle(self._tool_op_status)
        return True

    def _launch_lutris_installer(self, target: str, name: str):
        if not _is_flatpak_installed("net.lutris.Lutris"):
            self._tool_op_status.setText("Lutris is not installed.")
            self._tool_op_status.setObjectName("status-err")
            self._tool_op_status.show()
            _restyle(self._tool_op_status)
            QMessageBox.warning(
                self,
                "Lutris not found",
                f"Lutris is required to install {name}.\n\nInstall it from the Gaming Tools section above."
            )
            return

        if not shutil.which("umu-run"):
            if self._tool_worker and self._tool_worker.isRunning():
                return
            self._tool_log.clear()
            self._tool_log.append("→ ujust install-umu\n")
            self._tool_log_toggle.show()
            _set_log_panel(self._tool_log_toggle, self._tool_log, False)
            self._tool_progress.show()
            self._tool_cancel_btn.setEnabled(True)
            self._tool_cancel_btn.show()
            self._tool_op_status.setText("umu-launcher not found — installing automatically…")
            self._tool_op_status.setObjectName("subheading")
            self._tool_op_status.show()
            _restyle(self._tool_op_status)
            self._tool_worker = Worker(["ujust", "install-umu"])
            self._tool_worker.line.connect(lambda ln: (
                self._tool_log.append(ln),
                self._tool_log.ensureCursorVisible(),
            ))
            self._tool_worker.done.connect(
                lambda code, t=target, n=name: self._on_umu_install_done(code, t, n)
            )
            self._tool_worker.start()
            return

        self._tool_log.clear()
        if target == "epic-games-store" and not self._prepare_epic_lutris_install():
            return

        lutris_target = target if target.startswith("lutris:") else f"lutris:install/{target}"
        cmd = ["flatpak", "run", "net.lutris.Lutris", lutris_target]
        self._tool_log.append(f"→ {' '.join(cmd)}\n")
        self._tool_log.append("Lutris should open the installer dialog.")
        self._tool_log_toggle.show()
        _set_log_panel(self._tool_log_toggle, self._tool_log, False)
        self._tool_progress.hide()
        self._tool_op_status.setText(f"Opening {name} installer in Lutris…")
        self._tool_op_status.setObjectName("subheading")
        self._tool_op_status.show()
        _restyle(self._tool_op_status)

        try:
            subprocess.Popen(cmd)
            self._tool_op_status.setText(f"{name} installer opened in Lutris.")
            self._tool_op_status.setObjectName("status-ok")
            _restyle(self._tool_op_status)
        except Exception as exc:
            self._tool_log.append(f"\nFailed to start Lutris: {exc}")
            self._tool_op_status.setText(f"Failed to open {name} installer.")
            self._tool_op_status.setObjectName("status-err")
            _restyle(self._tool_op_status)
            QMessageBox.warning(self, f"{name} installer", str(exc))

    def _on_umu_install_done(self, code: int, target: str, name: str):
        self._tool_progress.hide()
        self._tool_cancel_btn.hide()
        _finish_worker(self, attr="_tool_worker")
        if code == Worker.CANCELLED:
            self._tool_op_status.setText("umu-launcher installation cancelled.")
            self._tool_op_status.setObjectName("status-warn")
            _restyle(self._tool_op_status)
            return
        if code != 0:
            self._tool_op_status.setText("umu-launcher installation failed.")
            self._tool_op_status.setObjectName("status-err")
            _restyle(self._tool_op_status)
            return
        self._tool_log.append("\numu-launcher installed. Proceeding with installer…")
        self._launch_lutris_installer(target, name)

    def _cancel_launcher_tool_operation(self):
        reply = QMessageBox.question(
            self,
            "Cancel Tool Install?",
            "Stop installing the launcher support tool? You can retry when you are ready.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        _cancel_worker(
            self,
            attr="_tool_worker",
            status_lbl=self._tool_op_status,
            log=self._tool_log,
            cancel_btn=self._tool_cancel_btn,
            message="Cancelling tool install…",
        )

    def _install_tool(self, tool: dict):
        if self._tool_worker and self._tool_worker.isRunning():
            return
        active_refs = next(r for r in self._tool_refs if r["tool"] is tool)
        self._active_tool_refs = active_refs
        for refs in self._tool_refs:
            refs["install"].setEnabled(False)
            refs["uninstall"].setEnabled(False)
        log = active_refs["log"]
        log_toggle = active_refs["log_toggle"]
        progress = active_refs["progress"]
        status_lbl = active_refs["status"]
        log.clear()
        log.append(f"→ flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo\n→ flatpak install -y flathub {tool['flatpak']}\n")
        log_toggle.show()
        _set_log_panel(log_toggle, log, False)
        progress.show()
        status_lbl.setText(f"Installing {tool['name']}…")
        status_lbl.setObjectName("subheading")
        status_lbl.show()
        _restyle(status_lbl)
        active_refs["cancel"].setEnabled(True)
        active_refs["cancel"].show()
        self._tool_worker = Worker([
            "bash", "-c",
            f"flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
            f" && flatpak install -y flathub {tool['flatpak']}",
        ])
        self._tool_worker.line.connect(lambda ln: (
            log.append(ln),
            log.ensureCursorVisible(),
        ))
        self._tool_worker.done.connect(
            lambda code, name=tool["name"]: self._on_tool_install_done(code, name)
        )
        self._tool_worker.start()

    def _on_tool_install_done(self, code: int, name: str):
        active_refs = self._active_tool_refs
        active_refs["progress"].hide()
        active_refs["cancel"].hide()
        _finish_worker(self, attr="_tool_worker")
        if code == Worker.CANCELLED:
            active_refs["status"].setText(f"{name} installation cancelled.")
            active_refs["status"].setObjectName("status-warn")
            active_refs["log"].append("\nCancelled.")
        elif code == 0:
            active_refs["status"].setText(f"{name} installed.")
            active_refs["status"].setObjectName("status-ok")
            active_refs["log"].append("\nDone.")
        else:
            active_refs["status"].setText(f"Installation failed (exit {code}).")
            active_refs["status"].setObjectName("status-err")
        _restyle(active_refs["status"])
        for refs in self._tool_refs:
            refs["install"].setEnabled(True)
            refs["uninstall"].setEnabled(True)
        self._refresh_status()

    def _cancel_tool_operation(self, refs: dict):
        if refs is not self._active_tool_refs:
            return
        reply = QMessageBox.question(
            self,
            "Cancel App Operation?",
            "Stop the running Flatpak operation? Any apps that already finished changing will keep their current state.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        _cancel_worker(
            self,
            attr="_tool_worker",
            status_lbl=refs["status"],
            log=refs["log"],
            cancel_btn=refs["cancel"],
            message="Cancelling app operation…",
        )

    def _uninstall_tool(self, tool: dict):
        if self._tool_worker and self._tool_worker.isRunning():
            return
        reply = QMessageBox.question(
            self, f"Uninstall {tool['name']}",
            f"Remove {tool['name']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        active_refs = next(r for r in self._tool_refs if r["tool"] is tool)
        self._active_tool_refs = active_refs
        for refs in self._tool_refs:
            refs["install"].setEnabled(False)
            refs["uninstall"].setEnabled(False)
        log = active_refs["log"]
        log_toggle = active_refs["log_toggle"]
        progress = active_refs["progress"]
        status_lbl = active_refs["status"]
        log.clear()
        log.append(f"→ flatpak uninstall -y {tool['flatpak']}\n")
        log_toggle.show()
        _set_log_panel(log_toggle, log, False)
        progress.show()
        status_lbl.setText(f"Uninstalling {tool['name']}…")
        status_lbl.setObjectName("subheading")
        status_lbl.show()
        _restyle(status_lbl)
        active_refs["cancel"].setEnabled(True)
        active_refs["cancel"].show()
        self._tool_worker = Worker(
            ["flatpak", "uninstall", "-y", tool["flatpak"]]
        )
        self._tool_worker.line.connect(lambda ln: (
            log.append(ln),
            log.ensureCursorVisible(),
        ))
        self._tool_worker.done.connect(
            lambda code, name=tool["name"]: self._on_tool_uninstall_done(code, name)
        )
        self._tool_worker.start()

    def _on_tool_uninstall_done(self, code: int, name: str):
        active_refs = self._active_tool_refs
        active_refs["progress"].hide()
        active_refs["cancel"].hide()
        _finish_worker(self, attr="_tool_worker")
        if code == Worker.CANCELLED:
            active_refs["status"].setText(f"{name} uninstall cancelled.")
            active_refs["status"].setObjectName("status-warn")
            active_refs["log"].append("\nCancelled.")
        elif code == 0:
            active_refs["status"].setText(f"{name} uninstalled.")
            active_refs["status"].setObjectName("status-ok")
            active_refs["log"].append("\nDone.")
        else:
            active_refs["status"].setText(f"Uninstall failed (exit {code}).")
            active_refs["status"].setObjectName("status-err")
        _restyle(active_refs["status"])
        for refs in self._tool_refs:
            refs["install"].setEnabled(True)
            refs["uninstall"].setEnabled(True)
        self._refresh_status()

    # ── GE-Proton update ───────────────────────────────────────────────────────

    def _update_ge_proton(self):
        if self._gp_worker and self._gp_worker.isRunning():
            return
        self._gp_update_btn.setEnabled(False)
        self._gp_log.clear()
        self._gp_log.append("→ /usr/bin/kyth-ge-proton-update\n")
        self._gp_log_toggle.show()
        _set_log_panel(self._gp_log_toggle, self._gp_log, False)
        self._gp_progress.show()
        self._gp_op_status.setText("Checking for GE-Proton update…")
        self._gp_op_status.setObjectName("subheading")
        self._gp_op_status.show()
        _restyle(self._gp_op_status)
        self._gp_worker = Worker(["/usr/bin/kyth-ge-proton-update"])
        self._gp_worker.line.connect(lambda ln: (
            self._gp_log.append(ln),
            self._gp_log.ensureCursorVisible(),
        ))
        self._gp_worker.done.connect(self._on_gp_update_done)
        self._gp_worker.start()

    def _on_gp_update_done(self, code: int):
        self._gp_progress.hide()
        _finish_worker(self, attr="_gp_worker")
        self._gp_update_btn.setEnabled(True)
        if code == 0:
            self._gp_op_status.setText("GE-Proton is up to date.")
            self._gp_op_status.setObjectName("status-ok")
            self._gp_log.append("\nDone.")
        else:
            self._gp_op_status.setText(f"Update failed (exit {code}).")
            self._gp_op_status.setObjectName("status-err")
        _restyle(self._gp_op_status)
        self._refresh_status()

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
                subprocess.Popen(["flatpak", "run", app_id])
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

    # ── Steam migration ────────────────────────────────────────────────────────

    def _refresh_ntfs_drives(self):
        self._drive_combo.clear()
        drives = [d for d in _find_ntfs_drives() if not d.get("is_bitlocker")]
        if not drives:
            self._drive_combo.addItem("No NTFS partitions found")
            return
        for d in drives:
            label = f"{d['dev']}  {d['size']}  {d['label'] or '(no label)'}"
            if d["mount"]:
                label += f"  [mounted at {d['mount']}]"
            self._drive_combo.addItem(label, userData=d)

    def _scan_steam_on_drive(self):
        drive = self._drive_combo.currentData()
        if not drive:
            return

        mount = drive["mount"]

        if not mount:
            self._migrate_status.setText(f"Mounting {drive['dev']}…")
            self._migrate_status.setObjectName("subheading")
            self._migrate_status.show()
            _restyle(self._migrate_status)
            QApplication.processEvents()
            try:
                # Prefer the kernel ntfs3 driver: it is dramatically faster than
                # the FUSE ntfs-3g default for the multi-hundred-GB copies this
                # page encourages. Read-only either way; fall back to the stock
                # driver when udisks or the kernel rejects ntfs3.
                r = subprocess.run(
                    ["udisksctl", "mount", "-b", drive["dev"], "-t", "ntfs3",
                     "--options", "ro", "--no-user-interaction"],
                    capture_output=True, text=True, timeout=15,
                )
                if r.returncode != 0:
                    r = subprocess.run(
                        ["udisksctl", "mount", "-b", drive["dev"],
                         "--options", "ro", "--no-user-interaction"],
                        capture_output=True, text=True, timeout=15,
                    )
                if r.returncode != 0:
                    err = r.stderr.strip()
                    if "hibernate" in err.lower() or "windows" in err.lower():
                        self._migrate_status.setText(
                            "Mount blocked: The other system did not shut down cleanly (Fast Startup / hibernate). "
                            "Boot the other system and do a full shut down, then try again."
                        )
                    else:
                        self._migrate_status.setText(f"Mount failed: {err}")
                    self._migrate_status.setObjectName("status-err")
                    _restyle(self._migrate_status)
                    return
                # udisksctl prints: "Mounted /dev/sdX1 at /run/media/user/Label."
                m = re.search(r" at (.+?)\.$", r.stdout.strip())
                mount = m.group(1) if m else None
                if not mount:
                    self._migrate_status.setText("Could not determine mount point from udisksctl output.")
                    self._migrate_status.setObjectName("status-err")
                    _restyle(self._migrate_status)
                    return
            except Exception as exc:
                self._migrate_status.setText(f"Mount error: {exc}")
                self._migrate_status.setObjectName("status-err")
                _restyle(self._migrate_status)
                return

        self._scanned_mount = mount
        self._migrate_status.setText(f"Scanning {mount} for Steam libraries…")
        self._migrate_status.setObjectName("subheading")
        self._migrate_status.show()
        _restyle(self._migrate_status)
        QApplication.processEvents()

        libs = _find_steam_libraries(mount)
        self._lib_combo.clear()
        self._clear_rows(self._winlib_rows)
        self._winlib_summary_lbl.hide()
        if not libs:
            self._migrate_found_lbl.setText(f"No Steam libraries found on {mount}.")
            self._lib_combo.hide()
            self._winlib_check_btn.hide()
            self._copy_btn.setEnabled(False)
            self._migrate_status.setText("No Steam libraries found on this drive.")
            self._migrate_status.setObjectName("status-err")
            _restyle(self._migrate_status)
            return

        for lib in libs:
            self._lib_combo.addItem(lib)
        self._lib_combo.show()
        self._winlib_check_btn.show()
        self._migrate_found_lbl.setText(f"Found {len(libs)} steamapps folder(s) — select one:")
        self._copy_btn.setEnabled(True)
        self._migrate_status.setText(
            f"Found {len(libs)} folder(s). Click Check My Games for a per-game readiness "
            "report, or Copy Library to start migrating."
        )
        self._migrate_status.setObjectName("status-ok")
        _restyle(self._migrate_status)

    _READY_TIERS = ("native", "platinum", "gold", "silver")

    def _blocked_compat_lookup(self) -> tuple[dict[str, str], set[str]]:
        """Blocked Steam appids (from compat source URLs) and lowercase names."""
        appids: dict[str, str] = {}
        names: set[str] = set()
        for game in _COMPAT_GAMES:
            if game.status != "blocked":
                continue
            names.add(game.name.lower())
            m = re.search(r"protondb\.com/app/(\d+)", game.source_url)
            if m:
                appids[m.group(1)] = game.name
        return appids, names

    def _check_windows_library_compat(self):
        steamapps = self._lib_combo.currentText().strip()
        if not steamapps:
            return
        games = _scan_steamapps_manifests(steamapps)
        self._winlib_games = games
        self._winlib_summary_lbl.show()
        if not games:
            self._clear_rows(self._winlib_rows)
            self._winlib_summary_lbl.setText("No game manifests found in this folder.")
            return
        cache = _load_protondb_cache()
        self._render_winlib_compat(games, cache)
        uncached = [g["appid"] for g in games if g["appid"] and g["appid"] not in cache]
        if uncached and (self._winlib_protondb_worker is None or not self._winlib_protondb_worker.isRunning()):
            self._winlib_summary_lbl.setText(
                self._winlib_summary_lbl.text() + "  Fetching ProtonDB ratings…"
            )
            worker = _ProtonDbBatchWorker(uncached, cache)
            worker.finished_all.connect(self._on_winlib_protondb_done)
            self._winlib_protondb_worker = worker
            _release_worker_when_finished(self, "_winlib_protondb_worker", worker)
            worker.start()

    def _on_winlib_protondb_done(self, full_cache: dict):
        _save_protondb_cache(full_cache)
        if self._winlib_games:
            self._render_winlib_compat(self._winlib_games, full_cache)

    def _render_winlib_compat(self, games: list[dict], cache: dict[str, str]):
        self._clear_rows(self._winlib_rows)
        blocked_appids, blocked_names = self._blocked_compat_lookup()
        graded: list[tuple[dict, str, str]] = []  # (game, category, badge text)
        ready = blocked = 0
        for game in games:
            appid = game.get("appid", "")
            name_l = game.get("name", "").lower()
            tier = (cache.get(appid) or "").lower()
            if appid in blocked_appids or name_l in blocked_names:
                blocked += 1
                graded.append((game, "blocked", "Blocked"))
            elif tier in self._READY_TIERS:
                ready += 1
                graded.append((game, "ready", "Native" if tier == "native" else tier.capitalize()))
            elif tier in ("bronze", "borked"):
                graded.append((game, "risky", tier.capitalize()))
            else:
                graded.append((game, "unknown", "Not rated"))
        total = len(games)
        self._winlib_summary_lbl.setText(
            f"{ready} of {total} of your games look ready to play on KythOS. "
            f"{blocked} blocked by anti-cheat, {total - ready - blocked} unrated or with mixed reports. "
            "Based on KythOS compatibility data and ProtonDB community reports."
        )
        # Blocked games first so the bad news is impossible to miss.
        order = {"blocked": 0, "risky": 1, "unknown": 2, "ready": 3}
        graded.sort(key=lambda item: (order[item[1]], item[0]["name"].lower()))
        for game, category, badge_text in graded[:30]:
            self._winlib_rows.addWidget(self._make_winlib_row(game, category, badge_text))
        if len(graded) > 30:
            more = QLabel(f"{len(graded) - 30} more games scanned — the summary above covers all of them.")
            more.setObjectName("card-copy")
            self._winlib_rows.addWidget(more)

    def _make_winlib_row(self, game: dict, category: str, badge_text: str) -> QFrame:
        row = QFrame()
        row.setObjectName({"blocked": "hw-card-err", "risky": "hw-card-warn"}.get(category, "hw-card-dim"))
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)
        name_lbl = QLabel(game["name"])
        name_lbl.setObjectName("card-summary")
        layout.addWidget(name_lbl, 1)
        badge = QLabel(f"  {badge_text}  ")
        if category == "blocked":
            badge.setStyleSheet(
                "background:#3a1010; color:#f48771; border:1px solid #5a1a1a; "
                "border-radius:3px; padding:2px 8px; font-size:11px; font-weight:700;"
            )
        else:
            # Native builds aren't a ProtonDB tier; show them platinum-green.
            tier_key = "platinum" if badge_text == "Native" else badge_text.lower()
            bg, fg = _PROTONDB_TIER_STYLE.get(tier_key, ("#252526", "#cccccc"))
            badge.setStyleSheet(
                f"background:{bg}; color:{fg}; "
                "border-radius:3px; padding:2px 8px; font-size:11px; font-weight:700;"
            )
        layout.addWidget(badge)
        return row

    def _browse_migrate_dst(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select destination steamapps folder", self._migrate_dst_edit.text()
        )
        if path:
            self._migrate_dst_edit.setText(path)

    def _start_steam_copy(self):
        if self._migrate_worker and self._migrate_worker.isRunning():
            return
        src = self._lib_combo.currentText().strip()
        dst = self._migrate_dst_edit.text().strip()
        if not src or not dst:
            return
        self._migrate_log.clear()
        self._migrate_log_toggle.show()
        _set_log_panel(self._migrate_log_toggle, self._migrate_log, False)
        self._migrate_progress.show()
        self._migrate_status.setText(f"Copying {src} → {dst}…")
        self._migrate_status.setObjectName("subheading")
        self._migrate_status.show()
        _restyle(self._migrate_status)
        self._copy_btn.setEnabled(False)
        self._copy_cancel_btn.show()
        self._migrate_worker = SteamCopyWorker(src, dst)
        self._migrate_worker.line.connect(lambda ln: (
            self._migrate_log.append(ln),
            self._migrate_log.ensureCursorVisible(),
        ))
        self._migrate_worker.done.connect(self._on_steam_copy_done)
        self._migrate_worker.start()

    def _cancel_steam_copy(self):
        if self._migrate_worker and self._migrate_worker.isRunning():
            self._migrate_worker.stop()

    def _on_steam_copy_done(self, code: int):
        self._migrate_progress.hide()
        self._copy_cancel_btn.hide()
        self._copy_btn.setEnabled(True)
        if code == 0:
            self._migrate_status.setText("Steam library copied successfully.")
            self._migrate_status.setObjectName("status-ok")
            self._migrate_log.append(
                "\nDone. You may need to add this folder as a Steam library in "
                "Steam → Settings → Storage."
            )
        else:
            self._migrate_status.setText(f"Copy failed (exit {code}). See details.")
            self._migrate_status.setObjectName("status-err")
        _restyle(self._migrate_status)
        _set_log_panel(self._migrate_log_toggle, self._migrate_log, True)

    def _make_gaming_ready_panel(self) -> QFrame:
        steam_ok = _is_flatpak_installed("com.valvesoftware.Steam")
        ge_ver = _ge_proton_version()
        vulkan_hint = bool(glob.glob("/dev/dri/renderD*")) or shutil.which("vulkaninfo") is not None
        ntsync_ok = os.path.exists("/dev/ntsync")
        items = [
            ("ok" if steam_ok else "warn", "Steam", "Installed." if steam_ok else "Install Steam for your library."),
            ("ok" if ge_ver else "err", "GE-Proton", ge_ver or "Update GE-Proton before testing PC games."),
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
