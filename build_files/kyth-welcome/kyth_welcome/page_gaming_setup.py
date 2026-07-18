import glob
import os
import shutil

# __KYTH_GENERATED_IMPORTS__
from .services.gaming import GameNightManager, _gamescope_installed, _mangohud_installed, _proton_cachyos_version
from .services.launch import flatpak_run, popen
from .services.software import _install_flatpak_inline, _is_flatpak_installed
from .qt import QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, Qt
from .widgets import ActionRow, _make_card


class _SetupSectionMixin:
    """The GAMING HUB "setup" section: readiness panel, Xbox Game Bar parity,
    PC game library card, Game Night Mode, and the health/migration-checklist
    card shells (their row data comes from GamingPage's shared data workers)."""

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
