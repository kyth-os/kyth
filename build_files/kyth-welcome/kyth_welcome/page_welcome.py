import os
import time

# __KYTH_GENERATED_IMPORTS__
from .core_base import IS_LIVE, load_profile, restyle, save_profile
from .services.bootc import branch_display_name, current_branch, has_rollback_deployment, has_staged_update
from .services.launch import reboot
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
from .services.flatpak import _is_flatpak_installed as _flatpak_installed
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

        # WelcomePage is built eagerly and synchronously by MainWindow before
        # the app's first window is even shown (see windows.py), so none of
        # the facts below may block on a subprocess call (bootc status,
        # lsblk, lspci, systemctl) — that would freeze the whole app on
        # first boot with no window visible at all. Start from safe
        # defaults and let _refresh_system_status() (triggered after this
        # constructor returns) fetch the real values on a background
        # thread and patch the affected widgets in place; see
        # _on_status_facts_ready().
        uname = os.uname()
        hostname = uname.nodename or "This PC"
        self._hostname = hostname
        self._kernel = uname.release or "unknown"
        self._session = os.environ.get("XDG_SESSION_TYPE", "unknown").capitalize()
        self._status_worker = None
        self._facts = {
            "branch": "Checking…",
            "staged": False,
            "rollback": False,
            "windows_found": False,
            "portal": "checking…",
            "pipewire": "checking…",
            "has_nvidia": False,
        }
        staged = self._facts["staged"]
        rollback = self._facts["rollback"]
        windows_found = self._facts["windows_found"]
        self._hero_view = home_hero_view(staged, rollback, windows_found)
        hero_view = self._hero_view

        self._add(self._make_hero_banner(hero_view))

        incomplete = [] if IS_LIVE else incomplete_steps(self._profile)
        if incomplete:
            self._add(self._make_setup_resume_card(incomplete))

        self._add(self._make_vibe_section())
        self._add_layout(self._make_hud_grid())

        self._apply_preset_worker = None

        self._ntfs_library_insert_index = self._layout.count()
        self._ntfs_library_worker = None
        if not IS_LIVE:
            single_shot(self, 0, self._refresh_ntfs_library_warning)

        days = None if IS_LIVE else _first_week_days()
        if days is not None and _FIRST_WEEK_MIN_DAYS <= days <= _FIRST_WEEK_MAX_DAYS:
            self._add(self._make_first_week_card(days))

        self._add(self._make_section_header("Explore Tasks", "Choose a card below to configure launchers, tune displays, or run diagnostics."))
        self._build_category_section()
        self._stretch()

        if not IS_LIVE:
            single_shot(self, 0, self._refresh_system_status)

    def _make_hero_banner(self, hero_view) -> QFrame:
        card = QFrame()
        card.setObjectName("genz-hero")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        hero_text_col = QVBoxLayout()
        hero_text_col.setSpacing(4)

        title = QLabel("KYTHOS WORKSTATION")
        title.setObjectName("genz-hero-title")
        hero_text_col.addWidget(title)

        subtitle = QLabel("Atomic immutable workstation. Zero bloat, maximum performance.")
        subtitle.setObjectName("genz-hero-subtitle")
        hero_text_col.addWidget(subtitle)

        layout.addLayout(hero_text_col, 1)

        status_pill = QLabel()
        status_pill.setText(hero_view.pill_text)
        status_pill.setObjectName(hero_view.pill_object_name)
        layout.addWidget(status_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        self._hero_pill = status_pill
        return card

    def _new_card(self, object_name: str, *, margins=(18, 16, 18, 16), spacing=8) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName(object_name)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        return card, layout

    def _make_card_header(self, title_text: str, layout: QVBoxLayout) -> None:
        title = QLabel(title_text)
        title.setObjectName("hud-title")
        layout.addWidget(title)

    def _make_hud_card(
        self,
        title_text: str,
        body_text: str,
        grid: QGridLayout,
        row: int,
        col: int,
    ) -> QLabel:
        card, card_layout = self._new_card("genz-hud-card")
        self._make_card_header(title_text, card_layout)
        desc = QLabel(body_text)
        desc.setTextFormat(Qt.TextFormat.RichText)
        desc.setObjectName("hud-desc")
        desc.setWordWrap(True)
        card_layout.addWidget(desc)
        grid.addWidget(card, row, col)
        return desc

    def _make_action_hud_card(
        self,
        title_text: str,
        body_text: str,
        button_text: str,
        callback,
        grid: QGridLayout,
        row: int,
        col: int,
    ) -> tuple[QLabel, QPushButton]:
        card, card_layout = self._new_card("genz-hud-card")
        self._make_card_header(title_text, card_layout)
        desc = QLabel(body_text)
        desc.setObjectName("hud-desc")
        desc.setWordWrap(True)
        card_layout.addWidget(desc)
        btn = QPushButton(button_text)
        btn.setObjectName("primary")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _=False: callback())
        card_layout.addWidget(btn)
        grid.addWidget(card, row, col)
        return desc, btn

    def _make_vibe_section(self) -> QWidget:
        section = QWidget()
        section.setObjectName("segmented-tab-row")
        layout = QHBoxLayout(section)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        label = QLabel("WORKSTATION MODE:")
        label.setObjectName("home-kicker")
        layout.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)

        self._focus_buttons = {}
        for key, text, tip in (
            ("everyday", "💻 Everyday Use", "Browser, office, files, and media."),
            ("gaming", "🎮 Gaming Rig", "Steam, launchers, performance, and controls."),
        ):
            button = QPushButton(text)
            button.setObjectName("segmented-tab")
            button.setCheckable(True)
            button.setToolTip(tip)
            button.clicked.connect(lambda _=False, k=key: self._on_focus_chosen(k))
            self._focus_buttons[key] = button
            layout.addWidget(button)

        layout.addSpacing(12)

        self._apply_preset_btn = QPushButton("Apply Settings")
        self._apply_preset_btn.setObjectName("primary")
        self._apply_preset_btn.clicked.connect(lambda _=False: self._apply_role_preset())
        layout.addWidget(self._apply_preset_btn)

        self._preset_status = QLabel("Ready to tune.")
        self._preset_status.setObjectName("status-dim")
        layout.addWidget(self._preset_status, 1)

        self._focus_buttons[self._profile].setChecked(True)
        return section

    def _make_hud_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(12)

        self._hud1_desc = self._make_hud_card(
            "SYSTEM NODE",
            f"<b>Device:</b> {self._hostname}<br>"
            f"<b>Kernel:</b> {self._kernel}<br>"
            f"<b>Channel:</b> {self._facts['branch']}",
            grid,
            0,
            0,
        )
        self._hud2_desc = self._make_hud_card(
            "ENVIRONMENT",
            f"<b>Session Type:</b> {self._session}<br>"
            f"<b>Audio Engine:</b> PipeWire ({self._facts['pipewire'].strip()})<br>"
            f"<b>Desktop Portal:</b> {self._facts['portal'].strip()}",
            grid,
            0,
            1,
        )
        self._hud3_desc = self._make_hud_card(
            "RECOVERY & DUAL-BOOT",
            f"<b>Previous State:</b> {'Available' if self._facts['rollback'] else 'None'}<br>"
            f"<b>Windows Disk:</b> {'Detected' if self._facts['windows_found'] else 'Not Detected'}<br>"
            f"<b>Fallback Theme:</b> Verified",
            grid,
            1,
            0,
        )
        self._hud4_desc, self._hud4_btn = self._make_action_hud_card(
            "RECOMMENDED ACTIONS",
            self._hero_view.rec_text,
            self._hero_view.rec_btn_label,
            self._on_recommended_action,
            grid,
            1,
            1,
        )
        return grid

    def _build_category_section(self) -> None:
        self._nvidia_at_build = self._facts["has_nvidia"]
        categories = home_categories(has_nvidia=self._nvidia_at_build)

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
        from .services.gaming import DataWorker, _steam_libraries_on_ntfs

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

    @staticmethod
    def _gather_status_facts() -> dict:
        """Run off the GUI thread by _refresh_system_status()'s DataWorker.
        Everything here is a subprocess/D-Bus call — see the comment at the
        top of __init__ for why none of it may run synchronously there."""
        from .services.bootc import branch_display_name, current_branch, has_rollback_deployment, has_staged_update
        from .services.gaming import _find_ntfs_drives
        from .services.hardware import _detect_nvidia
        from .services.process import command_stdout

        portal = command_stdout(
            ["bash", "-lc", "systemctl --user is-active xdg-desktop-portal.service 2>/dev/null || true"],
            timeout=3,
        ) or "unknown"
        pipewire = command_stdout(
            ["bash", "-lc", "systemctl --user is-active pipewire.service 2>/dev/null || true"],
            timeout=3,
        ) or "unknown"
        return {
            "branch": branch_display_name(current_branch()),
            "staged": has_staged_update(),
            "rollback": has_rollback_deployment(),
            "windows_found": bool(_find_ntfs_drives()),
            "portal": portal,
            "pipewire": pipewire,
            "has_nvidia": _detect_nvidia(),
        }

    def _refresh_system_status(self):
        if self._status_worker is not None:
            return
        from .services.gaming import DataWorker

        self._status_worker = DataWorker("welcome-status", self._gather_status_facts)
        self._status_worker.result.connect(self._on_status_facts_ready)
        self._status_worker.failed.connect(lambda _key, _message: None)
        self._status_worker.finished.connect(lambda: setattr(self, "_status_worker", None))
        self._status_worker.start()

    def _on_status_facts_ready(self, _key: str, facts: object):
        if not isinstance(facts, dict):
            return
        self._facts.update(facts)
        staged = self._facts["staged"]
        rollback = self._facts["rollback"]
        windows_found = self._facts["windows_found"]

        self._hero_view = home_hero_view(staged, rollback, windows_found)
        self._hero_pill.setText(self._hero_view.pill_text)
        self._hero_pill.setObjectName(self._hero_view.pill_object_name)
        restyle(self._hero_pill)

        self._hud1_desc.setText(
            f"<b>Device:</b> {self._hostname}<br>"
            f"<b>Kernel:</b> {self._kernel}<br>"
            f"<b>Channel:</b> {self._facts['branch']}"
        )
        self._hud2_desc.setText(
            f"<b>Session Type:</b> {self._session}<br>"
            f"<b>Audio Engine:</b> PipeWire ({self._facts['pipewire'].strip()})<br>"
            f"<b>Desktop Portal:</b> {self._facts['portal'].strip()}"
        )
        rollback_status = "Available" if rollback else "None"
        dual_boot_status = "Detected" if windows_found else "Not Detected"
        self._hud3_desc.setText(
            f"<b>Previous State:</b> {rollback_status}<br>"
            f"<b>Windows Disk:</b> {dual_boot_status}<br>"
            f"<b>Fallback Theme:</b> Verified"
        )
        self._hud4_desc.setText(self._hero_view.rec_text)
        self._hud4_btn.setText(self._hero_view.rec_btn_label)

        if bool(self._facts["has_nvidia"]) != self._nvidia_at_build:
            self._rebuild_category_grid()

    def _on_recommended_action(self):
        target = self._hero_view.rec_target
        if target == "reboot":
            reboot()
        else:
            self._navigate(target)

    def _rebuild_category_grid(self):
        """Re-derive the category cards once real GPU detection lands, since
        home_categories()'s "Advanced" card only lists "Manage NVIDIA
        drivers" when has_nvidia is True and the initial build used the
        False placeholder from self._facts (see __init__)."""
        self._nvidia_at_build = self._facts["has_nvidia"]
        for card, _is_games in self._category_cards:
            self._category_grid.removeWidget(card)
            card.deleteLater()
        self._category_cards = []
        for icon_names, glyph, title, tasks in home_categories(has_nvidia=self._nvidia_at_build):
            card = self._make_category_card(icon_names, glyph, title, tasks)
            self._category_cards.append((card, title == "Games"))
        self._relayout_categories(self._profile)

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
        # kyth-apply-role-preset runs with a 20s timeout; every other
        # subprocess call on this page (WelcomePage is built eagerly at
        # app startup — see __init__) was moved to a background worker for
        # exactly this reason, but this button's handler ran the command
        # synchronously and could freeze the whole app for up to 20s.
        if self._apply_preset_worker is not None:
            return
        profile = self._profile
        self._apply_preset_btn.setEnabled(False)
        self._preset_status.setObjectName("status-dim")
        self._preset_status.setText("Applying…")
        restyle(self._preset_status)

        from .services.gaming import DataWorker
        from .services.process import run_command

        worker = DataWorker(
            "apply-role-preset",
            lambda: run_command(["/usr/bin/kyth-apply-role-preset", profile], timeout=20),
        )
        self._apply_preset_worker = worker
        worker.result.connect(lambda _key, result: self._on_role_preset_result(result, profile))
        worker.failed.connect(lambda _key, message: self._on_role_preset_result(None, profile, message))
        worker.finished.connect(lambda: setattr(self, "_apply_preset_worker", None))
        worker.start()

    def _on_role_preset_result(self, result, profile: str, error: str | None = None):
        self._apply_preset_btn.setEnabled(True)
        if result is not None and result.returncode == 0:
            self._preset_status.setObjectName("status-ok")
            self._preset_status.setText(f"{profile.title()} preset applied.")
        else:
            detail = error or ""
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
