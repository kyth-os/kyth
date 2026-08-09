# __KYTH_GENERATED_IMPORTS__
from .core_base import restyle
from .services.gaming import (
    _gamescope_installed, _mangohud_installed, _proton_cachyos_version, _vkbasalt_installed,
)
from .services.flatpak import _is_flatpak_installed
from .qt import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget, Qt
from .widgets import StatusBadge


class _DashboardMixin:
    """The GAMING HUB "all"/Dashboard view: hero banner and HUD status grid."""

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

        hero_sub = QLabel("Your Windows games, tuned — Proton-CachyOS, Gamescope, MangoHud, all wired for one-click launch.")
        hero_sub.setObjectName("genz-hero-subtitle")
        hero_sub.setWordWrap(True)
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

        # Card 5: Steam Compatibility — full width below grid (Windows switcher #3)
        card5 = QFrame()
        card5.setObjectName("genz-hud-card")
        layout5 = QVBoxLayout(card5)
        layout5.setContentsMargins(18, 16, 18, 16)
        layout5.setSpacing(8)
        title5 = QLabel("STEAM COMPATIBILITY — Coming from Windows?")
        title5.setObjectName("hud-title")
        layout5.addWidget(title5)
        self._hud_compat_desc = QLabel("Scan your Windows Steam library — see which games work on Proton, which need anti-cheat, and copy saves safely.")
        self._hud_compat_desc.setTextFormat(Qt.TextFormat.RichText)
        self._hud_compat_desc.setObjectName("hud-desc")
        self._hud_compat_desc.setWordWrap(True)
        layout5.addWidget(self._hud_compat_desc)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        scan_btn2 = QPushButton("Scan My Windows Steam Library →")
        scan_btn2.setObjectName("primary")
        scan_btn2.clicked.connect(lambda _=False: self._switch_gaming_section("migration"))
        btn_row.addWidget(scan_btn2)
        btn_row.addStretch()
        layout5.addLayout(btn_row)
        hud_grid.addWidget(card5, 2, 0, 1, 2)
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
        restyle(self._hero_status_pill)

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

        # 2. Runtime Engine — Windows switchers need to see Windows games translate
        pc_ver = _proton_cachyos_version() or "None"
        # Show version with Windows-games framing: "Windows games via Proton-CachyOS 11"
        pc_label = pc_ver if pc_ver == "None" else f"{pc_ver} — Windows games ready"
        mangohud = "🟢 Active" if _mangohud_installed() else "🔴 Missing — install via Gaming → Tools"
        vkbasalt = "🟢 Active" if _vkbasalt_installed() else "⚪ Optional"
        gamescope = "🟢 Active" if _gamescope_installed() else "🔴 Missing — install via Gaming → Tools"

        self._hud_runtime_desc.setText(
            f"<b>Proton-CachyOS:</b> {pc_label}<br>"
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

        # _update_gaming_hud runs from _on_data_result (page_gaming.py), a
        # DataWorker.result *signal handler* — that executes on the GUI
        # thread, so calling _find_ntfs_drives() here would still be a
        # synchronous lsblk spawn even though the surrounding flow looks
        # async. _collect_gaming_dashboard() already scans drives on the
        # background thread for the health/checklist cards below; reuse it.
        windows_drives = data.get("windows_drives") or []
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

# New #4-6: driver/fwupd auto + Familiar Desktop toggle + OneDrive native mount (see new features 4-6)
