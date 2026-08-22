"""Pulse destination hubs — overview plus folded child pages as sections."""
from __future__ import annotations

from importlib import import_module

from .core_base import restyle
from .qt import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    Qt,
    Signal,
    single_shot,
)
from .page_registry import PULSE_RAIL
from .services.welcome import (
    MOVE_IN_CHECKLIST,
    MOVE_IN_JOURNEY,
    PLAY_LAUNCHERS,
    move_in_active_step,
    move_in_step,
    play_launcher_states,
    this_pc_timeline,
)
from .widgets import SegmentedTabBar, _make_card


def _hub_card(title: str, copy: str, page_key: str, navigate) -> QFrame:
    card, layout = _make_card("pulse-hub-card")
    heading = QLabel(title)
    heading.setObjectName("card-title")
    layout.addWidget(heading)
    body = QLabel(copy)
    body.setObjectName("card-copy")
    body.setWordWrap(True)
    layout.addWidget(body)
    btn = QPushButton(f"Open {title}")
    btn.setObjectName("primary")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(lambda _=False, k=page_key: navigate(k))
    layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)
    return card


def _hub_link(label: str, page_key: str, navigate) -> QPushButton:
    btn = QPushButton(label)
    btn.setObjectName("pulse-hub-link")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(lambda _=False, k=page_key: navigate(k))
    return btn


def _chip(title: str, value: str, page_key: str, navigate) -> QPushButton:
    btn = QPushButton(f"{title}\n{value}")
    btn.setObjectName("pulse-chip")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setMinimumHeight(72)
    btn.clicked.connect(lambda _=False, k=page_key: navigate(k))
    return btn


def _spawn_page(module_name: str, class_name: str, *, navigate=None, extra: dict | None = None) -> QWidget:
    module = import_module(f".{module_name}", "kyth_welcome")
    page_class = getattr(module, class_name)
    kwargs = dict(extra or {})
    if navigate is not None:
        kwargs["navigate"] = navigate
    page = page_class(**kwargs)
    embed = getattr(page, "set_embedded", None)
    if callable(embed):
        embed(True)
    return page


class SectionedHubPage(QWidget):
    """Destination chrome: title, section tabs, overview or a folded child page."""

    dest_title = ""
    dest_subtitle = ""
    tab_items: tuple[tuple[str, str], ...] = (("overview", "Overview"),)
    child_specs: dict[str, tuple[str, str, bool, dict]] = {}
    gaming_hidden_tabs: tuple[str, ...] = ()
    more_sections: tuple[str, ...] = ()
    section_changed = Signal(str)

    def __init__(self, navigate=None):
        super().__init__()
        self.setObjectName("content-area")
        self._navigate = navigate or (lambda _key: None)
        self._section = "overview"
        self._children: dict[str, QWidget] = {}
        self._profile = "everyday"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("page-header")
        header_l = QVBoxLayout(header)
        header_l.setContentsMargins(48, 24, 56, 8)
        header_l.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        glyph = next((item.glyph for item in PULSE_RAIL if item.dest == self.dest_title), "")
        if glyph:
            glyph_lbl = QLabel(glyph)
            glyph_lbl.setObjectName("pulse-hub-glyph")
            title_row.addWidget(glyph_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        title = QLabel(self.dest_title)
        title.setObjectName("heading")
        title_row.addWidget(title, 1, Qt.AlignmentFlag.AlignVCenter)
        header_l.addLayout(title_row)
        sub = QLabel(self.dest_subtitle)
        sub.setObjectName("subheading")
        sub.setWordWrap(True)
        header_l.addWidget(sub)
        root.addWidget(header)

        tab_host = QWidget()
        tab_host.setObjectName("pulse-hub-tabs")
        tab_l = QHBoxLayout(tab_host)
        tab_l.setContentsMargins(36, 4, 44, 8)
        tab_l.setSpacing(0)
        self._tabs = SegmentedTabBar(list(self.tab_items), active="overview")
        self._tabs.activated.connect(self.show_section)
        tab_l.addWidget(self._tabs)
        root.addWidget(tab_host)

        self._stack = QStackedWidget()
        self._stack.setObjectName("content-area")
        overview_scroll = QScrollArea()
        overview_scroll.setWidgetResizable(True)
        overview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        overview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        overview_host = QWidget()
        overview_host.setObjectName("content-area")
        self._overview_layout = QVBoxLayout(overview_host)
        self._overview_layout.setContentsMargins(48, 24, 56, 36)
        self._overview_layout.setSpacing(16)
        self._fill_overview(self._overview_layout)
        self._overview_layout.addStretch()
        overview_scroll.setWidget(overview_host)
        self._stack.addWidget(overview_scroll)
        self._overview = overview_scroll
        self._more = None
        if self.more_sections:
            more_scroll = QScrollArea()
            more_scroll.setWidgetResizable(True)
            more_scroll.setFrameShape(QFrame.Shape.NoFrame)
            more_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            more_host = QWidget()
            more_host.setObjectName("content-area")
            more_layout = QVBoxLayout(more_host)
            more_layout.setContentsMargins(48, 24, 56, 36)
            more_layout.setSpacing(16)
            self._fill_more(more_layout)
            more_layout.addStretch()
            more_scroll.setWidget(more_host)
            self._stack.addWidget(more_scroll)
            self._more = more_scroll
        root.addWidget(self._stack, 1)

    def _fill_overview(self, layout: QVBoxLayout) -> None:
        raise NotImplementedError

    def _fill_more(self, layout: QVBoxLayout) -> None:
        return

    def current_section(self) -> str:
        return self._section

    def _tab_for_section(self, section: str) -> str:
        if section == "More" or section in self.more_sections:
            return "More"
        return section

    def show_section(self, key: object) -> None:
        section = str(key or "overview")
        if section == "More" and self._more is not None:
            self._section = "More"
            self._tabs.set_active("More")
            self._stack.setCurrentWidget(self._more)
            self.section_changed.emit(self._section)
            return
        if section != "overview" and section not in self.child_specs:
            section = "overview"
        self._section = section
        self._tabs.set_active(self._tab_for_section(section) if section != "overview" else "overview")
        if section == "overview":
            self._stack.setCurrentWidget(self._overview)
            self.section_changed.emit(self._section)
            return
        page = self._children.get(section)
        if page is None:
            module, cls, needs_nav, extra = self.child_specs[section]
            page = _spawn_page(module, cls, navigate=self._navigate if needs_nav else None, extra=extra)
            self._children[section] = page
            self._stack.addWidget(page)
        self._stack.setCurrentWidget(page)
        self.section_changed.emit(self._section)

    def apply_profile(self, profile: str) -> None:
        self._profile = profile
        hidden = set(self.gaming_hidden_tabs if profile == "gaming" else ())
        for key, btn in self._tabs._buttons.items():
            btn.setVisible(str(key) not in hidden)
        if self._section in hidden:
            self.show_section("overview")


class PlayHubPage(SectionedHubPage):
    dest_title = "Play"
    dest_subtitle = "Launchers, boost, controllers, and will-it-run."
    tab_items = (
        ("overview", "Overview"),
        ("Gaming", "Library"),
        ("Performance", "Boost"),
        ("Compatibility", "Will it run?"),
        ("Controllers", "Controllers"),
    )
    child_specs = {
        "Gaming": ("page_gaming", "GamingPage", False, {}),
        "Performance": ("page_performance", "PerformancePage", False, {}),
        "Compatibility": ("page_compatibility", "CompatibilityPage", False, {}),
        "Controllers": ("page_controllers", "ControllerPage", False, {}),
    }

    def _fill_overview(self, layout: QVBoxLayout) -> None:
        self._play_worker = None
        launchers = QFrame()
        launchers.setObjectName("pulse-hub-card")
        launch_col = QVBoxLayout(launchers)
        launch_col.setContentsMargins(20, 16, 20, 16)
        launch_title = QLabel("Launch")
        launch_title.setObjectName("card-title")
        launch_col.addWidget(launch_title)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._launcher_btns: dict[str, QPushButton] = {}
        for name, _app_id in PLAY_LAUNCHERS:
            btn = QPushButton(f"{name}\nChecking…")
            btn.setObjectName("pulse-chip")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(72)
            btn.clicked.connect(lambda _=False: self.show_section("Gaming"))
            self._launcher_btns[name] = btn
            row.addWidget(btn, 1)
        launch_col.addLayout(row)
        layout.addWidget(launchers)

        boost, boost_layout = _make_card("pulse-hub-card")
        boost_title = QLabel("Game Boost")
        boost_title.setObjectName("card-title")
        boost_layout.addWidget(boost_title)
        self._boost_body = QLabel("Latency, scheduler, and MangoHud live on Boost.")
        self._boost_body.setObjectName("card-copy")
        self._boost_body.setWordWrap(True)
        boost_layout.addWidget(self._boost_body)
        boost_btn = QPushButton("Open Boost")
        boost_btn.setObjectName("primary")
        boost_btn.clicked.connect(lambda _=False: self.show_section("Performance"))
        boost_layout.addWidget(boost_btn, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(boost)

        tools = QHBoxLayout()
        tools.setSpacing(12)
        self._controllers_chip = _chip("Controllers", "Checking…", "Controllers", self.show_section)
        self._saves_chip = _chip("Saves", "Checking…", "Gaming", self.show_section)
        self._compat_chip = _chip("Will it run?", "ProtonDB and anti-cheat.", "Compatibility", self.show_section)
        tools.addWidget(self._controllers_chip, 1)
        tools.addWidget(self._saves_chip, 1)
        tools.addWidget(self._compat_chip, 1)
        layout.addLayout(tools)
        single_shot(self, 0, self._refresh_play)

    def _refresh_play(self) -> None:
        if self._play_worker is not None:
            return
        from .services.runtime import DataWorker, guard_disposed

        self._play_worker = DataWorker("pulse-play", self._gather_play_facts)
        self._play_worker.result.connect(guard_disposed(self._on_play_ready))
        self._play_worker.failed.connect(lambda _k, _m: None)
        self._play_worker.finished.connect(lambda: setattr(self, "_play_worker", None))
        self._play_worker.finished.connect(self._play_worker.deleteLater)
        self._play_worker.start()

    @staticmethod
    def _gather_play_facts() -> dict:
        from .services.flatpak import is_installed
        from .services.gaming import _ludusavi_backup_summary, _steam_libraries_on_ntfs
        from .services.hardware import _detect_controllers

        installed = {app_id: bool(is_installed(app_id)) for _name, app_id in PLAY_LAUNCHERS}
        controllers = _detect_controllers()
        connected = 0
        if isinstance(controllers, dict):
            devices = controllers.get("devices") or controllers.get("controllers") or []
            connected = len(devices) if isinstance(devices, (list, tuple)) else sum(
                1 for value in controllers.values() if value
            )
        saves = _ludusavi_backup_summary()
        return {
            "installed": installed,
            "controllers": connected,
            "saves": saves[2] if isinstance(saves, tuple) and len(saves) > 2 else "Save backups",
            "ntfs": bool(_steam_libraries_on_ntfs()),
        }

    def _on_play_ready(self, _key: str, facts: object) -> None:
        if not isinstance(facts, dict):
            return
        installed = facts.get("installed") if isinstance(facts.get("installed"), dict) else {}
        for name, ready in play_launcher_states(installed):
            btn = self._launcher_btns.get(name)
            if btn is None:
                continue
            btn.setText(f"{name}\n{'Ready' if ready else 'Install from Library'}")
            restyle(btn)
        count = int(facts.get("controllers") or 0)
        self._controllers_chip.setText(
            f"Controllers\n{count} connected" if count else "Controllers\nNone seen yet"
        )
        self._saves_chip.setText(f"Saves\n{facts.get('saves') or 'Open Library'}")
        if facts.get("ntfs"):
            self._boost_body.setText("A Steam library is on NTFS. Move it before you chase FPS.")
        restyle(self._controllers_chip)
        restyle(self._saves_chip)


class AppsHubPage(SectionedHubPage):
    dest_title = "Apps"
    dest_subtitle = "Trusted installs and a workday that feels familiar."
    tab_items = (
        ("overview", "Overview"),
        ("App Store", "Discover"),
        ("Work Setup", "Work"),
    )
    child_specs = {
        "App Store": ("page_software", "SoftwarePage", False, {"initial_tab": 4, "store_landing": True}),
        "Work Setup": ("page_work", "WorkSetupPage", True, {}),
    }
    gaming_hidden_tabs = ("Work Setup",)

    def _fill_overview(self, layout: QVBoxLayout) -> None:
        layout.addWidget(_hub_card("Discover", "Install Flatpaks and find familiar alternatives.", "App Store", self.show_section))
        self._work_card = _hub_card("Work Setup", "Office, mail, focus sessions, and workday conveniences.", "Work Setup", self.show_section)
        layout.addWidget(self._work_card)

    def apply_profile(self, profile: str) -> None:
        super().apply_profile(profile)
        if hasattr(self, "_work_card"):
            self._work_card.setVisible(profile != "gaming")


class ThisPcHubPage(SectionedHubPage):
    dest_title = "This PC"
    dest_subtitle = "Health, updates, and hardware in one place."
    tab_items = (
        ("overview", "Overview"),
        ("Guardian", "Guardian"),
        ("Update", "Updates"),
        ("Hardware", "Hardware"),
        ("Plasma Wayland", "Desktop"),
        ("Diagnostics", "Health"),
        ("Repair", "Repair"),
        ("More", "More"),
    )
    more_sections = ("NVIDIA", "Kernel", "Channels", "Just", "Feedback")
    child_specs = {
        "Guardian": ("page_guardian", "GuardianPage", True, {}),
        "Update": ("page_update", "UpdatePage", False, {}),
        "Hardware": ("page_hardware", "HardwarePage", True, {}),
        "Plasma Wayland": ("page_plasma_wayland", "PlasmaWaylandPage", False, {}),
        "Diagnostics": ("page_diagnostics", "DiagnosticsPage", True, {}),
        "Repair": ("page_repair", "RepairPage", True, {}),
        "NVIDIA": ("page_nvidia", "NvidiaPage", False, {}),
        "Kernel": ("page_kernel", "KernelPage", False, {}),
        "Channels": ("page_branches", "BranchesPage", False, {}),
        "Just": ("page_just", "JustPage", False, {}),
        "Feedback": ("page_feedback", "FeedbackPage", False, {}),
    }

    def _fill_overview(self, layout: QVBoxLayout) -> None:
        self._pc_worker = None
        self._timeline_labels: dict[str, QLabel] = {}
        timeline, timeline_layout = _make_card("pulse-hub-card")
        t_title = QLabel("Deployments")
        t_title.setObjectName("card-title")
        timeline_layout.addWidget(t_title)
        for key, title, body, _state in this_pc_timeline():
            row = QHBoxLayout()
            heading = QLabel(title)
            heading.setObjectName("pulse-timeline-title")
            row.addWidget(heading)
            value = QLabel(body)
            value.setObjectName("pulse-timeline-body")
            value.setWordWrap(True)
            row.addWidget(value, 1)
            timeline_layout.addLayout(row)
            self._timeline_labels[key] = value
        open_updates = QPushButton("Open Updates")
        open_updates.setObjectName("primary")
        open_updates.clicked.connect(lambda _=False: self.show_section("Update"))
        timeline_layout.addWidget(open_updates, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(timeline)

        chips = QHBoxLayout()
        chips.setSpacing(12)
        self._gpu_chip = _chip("GPU", "Checking…", "Hardware", self.show_section)
        self._display_chip = _chip("Displays", "HDR, VRR, layout", "Plasma Wayland", self.show_section)
        self._audio_chip = _chip("Audio", "PipeWire", "Hardware", self.show_section)
        self._storage_chip = _chip("Storage", "Checking…", "Hardware", self.show_section)
        for chip in (self._gpu_chip, self._display_chip, self._audio_chip, self._storage_chip):
            chips.addWidget(chip, 1)
        layout.addLayout(chips)

        guardian, g_layout = _make_card("pulse-hub-card")
        g_title = QLabel("Guardian")
        g_title.setObjectName("card-title")
        g_layout.addWidget(g_title)
        self._guardian_body = QLabel("Checking health…")
        self._guardian_body.setObjectName("card-copy")
        self._guardian_body.setWordWrap(True)
        g_layout.addWidget(self._guardian_body)
        g_row = QHBoxLayout()
        scan = QPushButton("Open Guardian")
        scan.setObjectName("primary")
        scan.clicked.connect(lambda _=False: self.show_section("Guardian"))
        g_row.addWidget(scan)
        repair = QPushButton("Repair")
        repair.clicked.connect(lambda _=False: self.show_section("Repair"))
        g_row.addWidget(repair)
        g_row.addStretch()
        g_layout.addLayout(g_row)
        layout.addWidget(guardian)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        more = QPushButton("More on this PC")
        more.setObjectName("pulse-hub-link")
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        more.clicked.connect(lambda _=False: self.show_section("More"))
        footer.addWidget(more)
        for label, key in (
            ("NVIDIA drivers", "NVIDIA"),
            ("Update channel", "Channels"),
            ("Feedback", "Feedback"),
        ):
            footer.addWidget(_hub_link(label, key, self.show_section))
        footer.addStretch()
        layout.addLayout(footer)
        single_shot(self, 0, self._refresh_this_pc)

    def _refresh_this_pc(self) -> None:
        if self._pc_worker is not None:
            return
        from .services.runtime import DataWorker, guard_disposed

        self._pc_worker = DataWorker("pulse-this-pc", self._gather_this_pc_facts)
        self._pc_worker.result.connect(guard_disposed(self._on_this_pc_ready))
        self._pc_worker.failed.connect(lambda _k, _m: None)
        self._pc_worker.finished.connect(lambda: setattr(self, "_pc_worker", None))
        self._pc_worker.finished.connect(self._pc_worker.deleteLater)
        self._pc_worker.start()

    @staticmethod
    def _gather_this_pc_facts() -> dict:
        from .services.bootc import (
            bootc_image_timestamp,
            branch_display_name,
            current_branch,
            has_rollback_deployment,
            has_staged_update,
        )
        from .services.hardware import _detect_nvidia

        rollback = bool(has_rollback_deployment())
        when = ""
        if rollback:
            try:
                when = str(bootc_image_timestamp("rollback") or "")
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError, TypeError):
                when = ""
        guardian = {"fresh": 0, "suppressed": ""}
        try:
            from kyth_shared.guardian import pending_recommendations, suppression_reason

            pending = pending_recommendations()
            guardian["fresh"] = len(pending)
            guardian["suppressed"] = str(suppression_reason() or "")
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError, ImportError):
            guardian = {"fresh": 0, "suppressed": ""}
        return {
            "branch": branch_display_name(current_branch()),
            "staged": bool(has_staged_update()),
            "rollback": rollback,
            "rollback_when": when,
            "nvidia": bool(_detect_nvidia()),
            "guardian": guardian,
        }

    def _on_this_pc_ready(self, _key: str, facts: object) -> None:
        if not isinstance(facts, dict):
            return
        for item_key, _title, body, _state in this_pc_timeline(
            branch=str(facts.get("branch") or ""),
            staged=bool(facts.get("staged")),
            rollback=bool(facts.get("rollback")),
            rollback_when=str(facts.get("rollback_when") or ""),
        ):
            label = self._timeline_labels.get(item_key)
            if label is not None:
                label.setText(body)
                restyle(label)
        self._gpu_chip.setText("GPU\nNVIDIA" if facts.get("nvidia") else "GPU\nOpen Hardware")
        self._storage_chip.setText(
            "Storage\nStaged update ready" if facts.get("staged") else "Storage\nOpen Hardware"
        )
        guardian = facts.get("guardian") if isinstance(facts.get("guardian"), dict) else {}
        fresh = int(guardian.get("fresh", 0) or 0)
        suppressed = str(guardian.get("suppressed") or "")
        if fresh and not suppressed:
            self._guardian_body.setText(f"{fresh} issue(s) need review.")
        elif suppressed:
            self._guardian_body.setText(f"Guardian paused — {suppressed}")
        else:
            self._guardian_body.setText("No fresh recommendations. Guardian is watching.")
        restyle(self._gpu_chip)
        restyle(self._storage_chip)
        restyle(self._guardian_body)

    def _fill_more(self, layout: QVBoxLayout) -> None:
        intro = QLabel("Advanced tools stay on This PC. Search still finds them by the old names.")
        intro.setObjectName("card-copy")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        for title, copy, key in (
            ("NVIDIA drivers", "Build and verify proprietary NVIDIA kernel modules.", "NVIDIA"),
            ("Update channel", "Follow stable or testing.", "Channels"),
            ("Kernel", "Fedora is the default. CachyOS is opt-in.", "Kernel"),
            ("Recipes", "Run ujust tasks without opening a terminal.", "Just"),
            ("Feedback", "Report a problem or request a feature.", "Feedback"),
        ):
            layout.addWidget(_hub_card(title, copy, key, self.show_section))


class MoveInHubPage(SectionedHubPage):
    dest_title = "Move In"
    dest_subtitle = "Four steps. Originals stay put until you choose to copy."
    tab_items = (
        ("overview", "Journey"),
        ("Move Files", "Toolbox"),
        ("Cloud Storage", "Cloud"),
        ("Network Shares", "Shares"),
        ("VPN", "VPN"),
    )
    child_specs = {
        "Move Files": ("page_windows_migration", "WindowsMigrationPage", True, {}),
        "Cloud Storage": ("page_cloud_storage", "CloudStoragePage", False, {}),
        "Network Shares": ("page_network_shares", "NetworkSharesPage", False, {}),
        "VPN": ("page_vpn", "VpnPage", False, {}),
    }

    def _fill_overview(self, layout: QVBoxLayout) -> None:
        self._move_worker = None
        self._active = "files"
        steps = QHBoxLayout()
        steps.setSpacing(8)
        self._step_btns: dict[str, QPushButton] = {}
        for index, (key, title, _copy, _target) in enumerate(MOVE_IN_JOURNEY, 1):
            btn = QPushButton(f"{index}  {title}")
            btn.setObjectName("pulse-step")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._show_step(k))
            self._step_btns[key] = btn
            steps.addWidget(btn, 1)
        layout.addLayout(steps)

        card, card_layout = _make_card("pulse-action")
        self._step_title = QLabel("")
        self._step_title.setObjectName("pulse-action-title")
        card_layout.addWidget(self._step_title)
        self._step_body = QLabel("")
        self._step_body.setObjectName("pulse-action-body")
        self._step_body.setWordWrap(True)
        card_layout.addWidget(self._step_body)
        self._step_btn = QPushButton("Continue")
        self._step_btn.setObjectName("primary")
        self._step_btn.clicked.connect(lambda _=False: self._open_active_step())
        card_layout.addWidget(self._step_btn, 0, Qt.AlignmentFlag.AlignLeft)
        note = QLabel("Your original files stay put until you choose to move them.")
        note.setObjectName("card-copy")
        card_layout.addWidget(note)
        layout.addWidget(card)

        checklist, check_layout = _make_card("pulse-hub-card")
        check_title = QLabel("Move-in checklist")
        check_title.setObjectName("card-title")
        check_layout.addWidget(check_title)
        for title, copy, key in MOVE_IN_CHECKLIST:
            row = QHBoxLayout()
            text = QLabel(f"{title} — {copy}")
            text.setObjectName("card-copy")
            text.setWordWrap(True)
            row.addWidget(text, 1)
            link = _hub_link("Open", key, self._navigate)
            row.addWidget(link)
            check_layout.addLayout(row)
        toolbox = QPushButton("Open the full toolbox")
        toolbox.clicked.connect(lambda _=False: self.show_section("Move Files"))
        check_layout.addWidget(toolbox, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(checklist)
        self._show_step("files")
        single_shot(self, 0, self._refresh_move_in)

    def _show_step(self, key: str) -> None:
        self._active = key
        _key, title, copy, _target = move_in_step(key)
        self._step_title.setText(title)
        self._step_body.setText(copy)
        self._step_btn.setText(f"Continue {title}")
        for step_key, btn in self._step_btns.items():
            btn.setObjectName("pulse-step-active" if step_key == key else "pulse-step")
            restyle(btn)

    def _open_active_step(self) -> None:
        target = move_in_step(self._active)[3]
        if target in self.child_specs:
            self.show_section(target)
            return
        self._navigate(target)

    def _refresh_move_in(self) -> None:
        if self._move_worker is not None:
            return
        from .services.runtime import DataWorker, guard_disposed

        self._move_worker = DataWorker("pulse-move-in", self._gather_move_in_facts)
        self._move_worker.result.connect(guard_disposed(self._on_move_in_ready))
        self._move_worker.failed.connect(lambda _k, _m: None)
        self._move_worker.finished.connect(lambda: setattr(self, "_move_worker", None))
        self._move_worker.finished.connect(self._move_worker.deleteLater)
        self._move_worker.start()

    @staticmethod
    def _gather_move_in_facts() -> dict:
        from .services.gaming import _find_ntfs_drives, _steam_libraries_on_ntfs

        return {
            "ntfs_library": bool(_steam_libraries_on_ntfs()),
            "windows_found": bool(_find_ntfs_drives()),
        }

    def _on_move_in_ready(self, _key: str, facts: object) -> None:
        if not isinstance(facts, dict):
            return
        self._show_step(
            move_in_active_step(
                ntfs_library=bool(facts.get("ntfs_library")),
                windows_found=bool(facts.get("windows_found")),
            )
        )
