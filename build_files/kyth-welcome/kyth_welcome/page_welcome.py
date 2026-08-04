import os
import time

# __KYTH_GENERATED_IMPORTS__
from .core_base import IS_LIVE, load_profile, restyle, save_profile
from .services.bootc import branch_display_name, current_branch, has_rollback_deployment, has_staged_update
from .services.gaming import (
    DataWorker, _find_ntfs_drives, _steam_libraries_on_ntfs,
)
from .services.hardware import _detect_nvidia
from .services.launch import reboot
from .services.process import command_stdout, run_command
from .services.flatpak import _is_flatpak_installed as _flatpak_installed
from .services.setup_state import STEP_LABELS, STEP_RESUME_PAGE, incomplete_steps
from .services.welcome import (
    FIRST_WEEK_MAX_DAYS as _FIRST_WEEK_MAX_DAYS,
    FIRST_WEEK_MIN_DAYS as _FIRST_WEEK_MIN_DAYS,
    _FIRST_WEEK_DISMISS,
    _browser_integration_native_ready,
    _cloud_storage_configured,
    _controller_seen,
    _first_week_days,
    _kdeconnect_configured,
    _printer_configured,
    home_categories,
    home_hero_view,
    visible_category_indexes,
)
from .qt import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSize, QVBoxLayout, QWidget, Qt, Signal, single_shot,
)
from .widgets import (
    Page, _make_card, _theme_icon,
)

# ── Page: Welcome (Control Panel-style home) ──────────────────────────────────
class WelcomePage(Page):
    profile_changed = Signal(str)

    def __init__(self, navigate=None):
        super().__init__()
        self._navigate = navigate or (lambda _: None)
        self._profile = load_profile()

        # Simplify standard header to let the new Gen Z Hero Banner shine
        self._page_header(
            "System Hub",
            "Dashboard",
            ""
        )

        branch = branch_display_name(current_branch())
        staged = has_staged_update()
        rollback = has_rollback_deployment()
        uname = os.uname()
        kernel = uname.release or "unknown"
        hostname = uname.nodename or "This PC"
        windows_found = bool(_find_ntfs_drives())
        hero_view = home_hero_view(staged, rollback, windows_found)

        # ── 1. The Dynamic Gen Z Hero Banner ──────────────────────────────────
        hero_card = QFrame()
        hero_card.setObjectName("genz-hero")
        hero_layout = QHBoxLayout(hero_card)
        hero_layout.setContentsMargins(24, 20, 24, 20)
        hero_layout.setSpacing(16)

        hero_text_col = QVBoxLayout()
        hero_text_col.setSpacing(4)
        
        hero_title = QLabel("KYTHOS WORKSTATION")
        hero_title.setObjectName("genz-hero-title")
        hero_text_col.addWidget(hero_title)

        hero_sub = QLabel("Atomic immutable workstation. Zero bloat, maximum performance.")
        hero_sub.setObjectName("genz-hero-subtitle")
        hero_text_col.addWidget(hero_sub)
        hero_layout.addLayout(hero_text_col, 1)

        # Status Pill Badge
        status_pill = QLabel()
        status_pill.setText(hero_view.pill_text)
        status_pill.setObjectName(hero_view.pill_object_name)
        hero_layout.addWidget(status_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        self._add(hero_card)

        # ── 1b. Finish setup (resumable first-boot wizard steps) ──────────────
        incomplete = [] if IS_LIVE else incomplete_steps(self._profile)
        if incomplete:
            self._add(self._make_setup_resume_card(incomplete))

        # ── 2. Segmented Focus Vibe Selector ──────────────────────────────────
        vibe_row = QWidget()
        vibe_row.setObjectName("segmented-tab-row")
        vibe_layout = QHBoxLayout(vibe_row)
        vibe_layout.setContentsMargins(16, 10, 16, 10)
        vibe_layout.setSpacing(12)

        vibe_lbl = QLabel("WORKSTATION MODE:")
        vibe_lbl.setObjectName("home-kicker")
        vibe_layout.addWidget(vibe_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        self._focus_buttons = {}
        for key, label, tip in (
            ("everyday", "💻 Everyday Use", "Browser, office, files, and media."),
            ("gaming", "🎮 Gaming Rig", "Steam, launchers, performance, and controls."),
        ):
            btn = QPushButton(label)
            btn.setObjectName("segmented-tab")
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _=False, k=key: self._on_focus_chosen(k))
            self._focus_buttons[key] = btn
            vibe_layout.addWidget(btn)

        vibe_layout.addSpacing(12)

        apply_btn = QPushButton("Apply Settings")
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(lambda _=False: self._apply_role_preset())
        vibe_layout.addWidget(apply_btn)

        self._preset_status = QLabel("Ready to tune.")
        self._preset_status.setObjectName("status-dim")
        vibe_layout.addWidget(self._preset_status, 1)

        self._focus_buttons[self._profile].setChecked(True)
        self._add(vibe_row)

        # ── 3. High-Tech HUD Grid (Merging metadata, readiness, and desktop experience) ──
        hud_grid = QGridLayout()
        hud_grid.setSpacing(12)

        # HUD 1: Core System Vibe
        card1 = QFrame()
        card1.setObjectName("genz-hud-card")
        layout1 = QVBoxLayout(card1)
        layout1.setContentsMargins(18, 16, 18, 16)
        layout1.setSpacing(8)
        title1 = QLabel("SYSTEM NODE")
        title1.setObjectName("hud-title")
        layout1.addWidget(title1)
        desc1 = QLabel(f"<b>Device:</b> {hostname}<br>"
                       f"<b>Kernel:</b> {kernel}<br>"
                       f"<b>Channel:</b> {branch}")
        desc1.setTextFormat(Qt.TextFormat.RichText)
        desc1.setObjectName("hud-desc")
        desc1.setWordWrap(True)
        layout1.addWidget(desc1)
        hud_grid.addWidget(card1, 0, 0)

        # HUD 2: Environment Summary
        card2 = QFrame()
        card2.setObjectName("genz-hud-card")
        layout2 = QVBoxLayout(card2)
        layout2.setContentsMargins(18, 16, 18, 16)
        layout2.setSpacing(8)
        title2 = QLabel("ENVIRONMENT")
        title2.setObjectName("hud-title")
        layout2.addWidget(title2)
        session = os.environ.get("XDG_SESSION_TYPE", "unknown").capitalize()
        portal = command_stdout(["bash", "-lc", "systemctl --user is-active xdg-desktop-portal.service 2>/dev/null || true"], timeout=3) or "unknown"
        pipewire = command_stdout(["bash", "-lc", "systemctl --user is-active pipewire.service 2>/dev/null || true"], timeout=3) or "unknown"
        desc2 = QLabel(f"<b>Session Type:</b> {session}<br>"
                       f"<b>Audio Engine:</b> PipeWire ({pipewire.strip()})<br>"
                       f"<b>Desktop Portal:</b> {portal.strip()}")
        desc2.setTextFormat(Qt.TextFormat.RichText)
        desc2.setObjectName("hud-desc")
        desc2.setWordWrap(True)
        layout2.addWidget(desc2)
        hud_grid.addWidget(card2, 0, 1)

        # HUD 3: Recovery / Dual-Boot
        card3 = QFrame()
        card3.setObjectName("genz-hud-card")
        layout3 = QVBoxLayout(card3)
        layout3.setContentsMargins(18, 16, 18, 16)
        layout3.setSpacing(8)
        title3 = QLabel("RECOVERY & DUAL-BOOT")
        title3.setObjectName("hud-title")
        layout3.addWidget(title3)
        rollback_status = "Available" if rollback else "None"
        dual_boot_status = "Detected" if windows_found else "Not Detected"
        desc3 = QLabel(f"<b>Previous State:</b> {rollback_status}<br>"
                       f"<b>Windows Disk:</b> {dual_boot_status}<br>"
                       f"<b>Fallback Theme:</b> Verified")
        desc3.setTextFormat(Qt.TextFormat.RichText)
        desc3.setObjectName("hud-desc")
        desc3.setWordWrap(True)
        layout3.addWidget(desc3)
        hud_grid.addWidget(card3, 1, 0)

        # HUD 4: Recommended / Quick Vibe Actions
        card4 = QFrame()
        card4.setObjectName("genz-hud-card")
        layout4 = QVBoxLayout(card4)
        layout4.setContentsMargins(18, 16, 18, 16)
        layout4.setSpacing(8)
        title4 = QLabel("RECOMMENDED ACTIONS")
        title4.setObjectName("hud-title")
        layout4.addWidget(title4)

        desc4 = QLabel(hero_view.rec_text)
        desc4.setObjectName("hud-desc")
        desc4.setWordWrap(True)
        layout4.addWidget(desc4)

        btn4 = QPushButton(hero_view.rec_btn_label)
        btn4.setObjectName("primary")
        btn4.setCursor(Qt.CursorShape.PointingHandCursor)
        if hero_view.rec_target == "reboot":
            btn4.clicked.connect(lambda _=False: reboot())
        else:
            btn4.clicked.connect(lambda _=False: self._navigate(hero_view.rec_target))
        layout4.addWidget(btn4)
        hud_grid.addWidget(card4, 1, 1)

        self._add_layout(hud_grid)

        # ── NTFS Steam library warning ────────────────────────────────────────
        self._ntfs_library_insert_index = self._layout.count()
        self._ntfs_library_worker = None
        if not IS_LIVE:
            single_shot(self, 0, self._refresh_ntfs_library_warning)

        # ── First-week tips ───────────────────────────────────────────────────
        days = None if IS_LIVE else _first_week_days()
        if days is not None and _FIRST_WEEK_MIN_DAYS <= days <= _FIRST_WEEK_MAX_DAYS:
            self._add(self._make_first_week_card(days))

        self._add(self._make_section_header("Explore Tasks", "Choose a card below to configure launchers, tune displays, or run diagnostics."))

        # ── Category Grid (Action Cards) ──────────────────────────────────────
        categories = home_categories(has_nvidia=_detect_nvidia())

        self._category_grid = QGridLayout()
        self._category_grid.setSpacing(12)
        self._category_cards = []
        for icon_names, glyph, title, tasks in categories:
            card = self._make_category_card(icon_names, glyph, title, tasks)
            self._category_cards.append((card, title == "Games"))
        self._relayout_categories(self._profile)
        self._category_grid.setColumnStretch(0, 1)
        self._category_grid.setColumnStretch(1, 1)
        self._add_layout(self._category_grid)

        self._stretch()

    def _make_ntfs_library_card(self, libs: list[str]) -> QFrame:
        card, layout = _make_card("card-accent-warn")
        title = QLabel("Steam Library on NTFS Drive Detected")
        title.setObjectName("card-title")
        layout.addWidget(title)
        home = os.path.expanduser("~")
        listed = ",  ".join(lib.replace(home, "~", 1) for lib in libs[:3])
        if len(libs) > 3:
            listed += f"  (+{len(libs) - 3} more)"
        body = QLabel(
            f"Steam is using an NTFS/exFAT library: {listed}. Proton needs a "
            "Linux-formatted disk (ext4 or btrfs). Games on NTFS will fail to launch or corrupt saves. "
            "Copy games to your KythOS system partition to play safely."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        copy_btn = QPushButton("Copy Games to KythOS")
        copy_btn.setObjectName("primary")
        copy_btn.clicked.connect(lambda _=False: self._navigate("Gaming"))
        btns.addWidget(copy_btn)
        learn_btn = QPushButton("Why This Breaks")
        learn_btn.clicked.connect(lambda _=False: self._navigate("Move Files"))
        btns.addWidget(learn_btn)
        btns.addStretch()
        layout.addLayout(btns)
        return card

    def _refresh_ntfs_library_warning(self):
        if self._ntfs_library_worker is not None:
            return
        self._ntfs_library_worker = DataWorker("ntfs-libraries", _steam_libraries_on_ntfs)
        self._ntfs_library_worker.result.connect(self._on_ntfs_library_warning_ready)
        self._ntfs_library_worker.failed.connect(lambda _key, _message: None)
        self._ntfs_library_worker.finished.connect(lambda: setattr(self, "_ntfs_library_worker", None))
        self._ntfs_library_worker.start()

    def _on_ntfs_library_warning_ready(self, _key: str, libs: object):
        if not libs:
            return
        card = self._make_ntfs_library_card(list(libs))
        self._layout.insertWidget(self._ntfs_library_insert_index, card)
        restyle(card)

    def _make_setup_resume_card(self, incomplete: list[tuple[str, str]]) -> QFrame:
        card, layout = _make_card("card-accent-warn")
        title = QLabel("Finish setup")
        title.setObjectName("card-title")
        layout.addWidget(title)

        body = QLabel(
            "A few things from first-boot setup are still open. Pick up where you left off "
            "whenever you're ready."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        for key, status in incomplete:
            row = QHBoxLayout()
            row.setSpacing(10)
            badge = QLabel("Skipped" if status == "skipped" else "Not started")
            badge.setObjectName("task-status-warn" if status == "skipped" else "task-status-idle")
            row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

            label = QLabel(STEP_LABELS.get(key, key))
            label.setObjectName("card-copy")
            row.addWidget(label, 1)

            page_key = STEP_RESUME_PAGE.get(key)
            btn = QPushButton("Resume" if page_key else "Not available yet")
            btn.setEnabled(bool(page_key))
            if page_key:
                btn.clicked.connect(lambda _=False, k=page_key: self._navigate(k))
            row.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
            layout.addLayout(row)
        return card

    def _make_first_week_card(self, days: int) -> QFrame:
        card, layout = _make_card("card-accent-ok")
        title = QLabel(f"Day {days} Checklist — Finalize Your Setup")
        title.setObjectName("card-title")
        layout.addWidget(title)

        body = QLabel("Ensure the following components are fully configured for the best desktop experience.")
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        app_setup_done = os.path.exists("/var/lib/kyth/default-flatpaks-v10-done")
        checklist = [
            (app_setup_done, "Default Apps", "Steam, bottles, and flatpaks installed.", "App Store"),
            (_flatpak_installed("com.brave.Browser"), "Browser", "Brave browser set up.", "App Store"),
            (_browser_integration_native_ready(), "Browser Integration", "Plasma desktop connection enabled.", "App Store"),
            (_flatpak_installed("com.valvesoftware.Steam"), "Steam Integration", "Steam libraries and backups set up.", "Gaming"),
            (_controller_seen(), "Controller Setup", "Game controllers detected.", "Controllers"),
            (_kdeconnect_configured(), "KDE Connect", "Phone pairing and notifications set up.", "Move Files"),
            (_cloud_storage_configured(), "Cloud Sync", "rclone/cloud sync initialized.", "Cloud Storage"),
            (_printer_configured(), "Printers", "Local or network printers configured.", "Hardware"),
            (has_rollback_deployment(), "Rollback Safety", "Previous builds cached for rollback.", "Update"),
        ]

        for done, label, text, page_key in checklist:
            row = QHBoxLayout()
            row.setSpacing(10)
            badge = QLabel("Done" if done else "Pending")
            badge.setObjectName("task-status-ok" if done else "task-status-idle")
            row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            heading = QLabel(label)
            heading.setObjectName("card-subtitle")
            text_col.addWidget(heading)
            lbl = QLabel(text)
            lbl.setObjectName("card-copy")
            lbl.setWordWrap(True)
            text_col.addWidget(lbl)
            row.addLayout(text_col, 1)

            btn = QPushButton("Open" if done else "Set Up")
            btn.clicked.connect(lambda _=False, k=page_key: self._navigate(k))
            row.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
            layout.addLayout(row)

        dismiss_row = QHBoxLayout()
        dismiss_btn = QPushButton("Got it — hide this")
        dismiss_btn.clicked.connect(lambda _=False, c=card: self._dismiss_first_week(c))
        dismiss_row.addWidget(dismiss_btn)
        dismiss_row.addStretch()
        layout.addLayout(dismiss_row)
        return card

    def _dismiss_first_week(self, card: QFrame):
        try:
            os.makedirs(os.path.dirname(_FIRST_WEEK_DISMISS), exist_ok=True)
            with open(_FIRST_WEEK_DISMISS, "w", encoding="utf-8") as fh:
                fh.write(str(int(time.time())))
        except OSError:
            pass
        card.hide()

    def _make_section_header(self, title: str, subtitle: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("home-section")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 12, 0, 4)
        layout.setSpacing(4)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("home-section-title")
        layout.addWidget(title_lbl)

        subtitle_lbl = QLabel(subtitle)
        subtitle_lbl.setObjectName("home-section-copy")
        subtitle_lbl.setWordWrap(True)
        layout.addWidget(subtitle_lbl)
        return frame

    def _on_focus_chosen(self, profile: str):
        self._profile = profile
        for key, btn in self._focus_buttons.items():
            btn.setChecked(key == profile)
        save_profile(profile)
        self._relayout_categories(profile)
        self.profile_changed.emit(profile)

    def _apply_role_preset(self):
        result = run_command(["/usr/bin/kyth-apply-role-preset", self._profile], timeout=20)
        if result is not None and result.returncode == 0:
            self._preset_status.setObjectName("status-ok")
            self._preset_status.setText(f"{self._profile.title()} preset applied.")
        else:
            detail = ""
            if result is not None:
                detail = (result.stderr or result.stdout or "").strip()
            self._preset_status.setObjectName("status-warn")
            self._preset_status.setText(f"Preset error: {detail or 'unknown error'}")
        restyle(self._preset_status)

    def _relayout_categories(self, profile: str):
        visible = []
        visible_indexes = set(visible_category_indexes(
            profile, [is_games for _card, is_games in self._category_cards]
        ))
        for index, (card, _is_games) in enumerate(self._category_cards):
            self._category_grid.removeWidget(card)
            wanted = index in visible_indexes
            card.setVisible(wanted)
            if wanted:
                visible.append(card)
        for i, card in enumerate(visible):
            self._category_grid.addWidget(card, i // 2, i % 2)

    def _make_category_card(
        self,
        icon_names: tuple[str, ...],
        glyph: str,
        title: str,
        tasks: list[tuple[str, str]],
    ) -> QFrame:
        card = QFrame()
        # Color coding left border
        title_lower = title.lower()
        if "games" in title_lower:
            card.setObjectName("genz-category-gaming")
        elif "apps" in title_lower:
            card.setObjectName("genz-category-apps")
        elif "system" in title_lower:
            card.setObjectName("genz-category-system")
        elif "network" in title_lower:
            card.setObjectName("genz-category-network")
        else:
            card.setObjectName("genz-category-advanced")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        icon = _theme_icon(*icon_names)
        icon_lbl = QLabel()
        if icon.isNull():
            icon_lbl.setText(glyph)
            icon_lbl.setObjectName("home-action-icon")
            icon_lbl.setStyleSheet("font-size: 24px;")
        else:
            icon_lbl.setPixmap(icon.pixmap(QSize(32, 32)))
        icon_lbl.setFixedWidth(36)
        layout.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(6)

        first_key = tasks[0][1] if tasks else None
        title_btn = QPushButton(title.replace("&", "&&"))
        title_btn.setObjectName("genz-category-title")
        title_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if first_key:
            title_btn.clicked.connect(lambda _=False, k=first_key: self._navigate(k))
        text_col.addWidget(title_btn, 0, Qt.AlignmentFlag.AlignLeft)

        for label, key in tasks:
            link = QPushButton(f"➔  {label}")
            link.setObjectName("genz-task-link")
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.clicked.connect(lambda _=False, k=key: self._navigate(k))
            text_col.addWidget(link, 0, Qt.AlignmentFlag.AlignLeft)

        text_col.addStretch()
        layout.addLayout(text_col, 1)
        return card
