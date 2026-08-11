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
from .lazy_page import compose_on_first_init
from .widgets import (
    Page, _make_card, _theme_icon,
)

def _load_welcome_mixins():
    from .page_welcome_grid import _WelcomeGridMixin
    from .page_welcome_hero import _WelcomeHeroMixin
    from .page_welcome_hud import _WelcomeHudMixin
    return (_WelcomeGridMixin, _WelcomeHeroMixin, _WelcomeHudMixin)

# ── Page: Welcome (Control Panel-style home) ──────────────────────────────────
@compose_on_first_init(_load_welcome_mixins)
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
        # R6: AI control plane — surface deterministic repair plan from same
        # probe snapshot + boot_health + Evaluation that RepairPage uses.
        self._ai_card, ai_layout = _make_card("card-accent-ok")
        ai_title = QLabel("AI Control Plane — offline")
        ai_title.setObjectName("card-title")
        ai_layout.addWidget(ai_title)
        self._ai_desc = QLabel("Checking system health…")
        self._ai_desc.setObjectName("card-copy")
        self._ai_desc.setWordWrap(True)
        ai_layout.addWidget(self._ai_desc)
        self._ai_btn = QPushButton("Open Repair")
        self._ai_btn.setToolTip("Open Repair for the AI-suggested action")
        self._ai_btn.clicked.connect(lambda _=False: self._navigate("Repair"))
        self._ai_btn.hide()
        ai_layout.addWidget(self._ai_btn)
        self._add(self._ai_card)
        self._ai_worker = None

        self._apply_preset_worker = None

        self._ntfs_library_insert_index = self._layout.count()
        self._ntfs_library_worker = None
        if not IS_LIVE:
            single_shot(self, 0, self._refresh_ntfs_library_warning)

        days = None if IS_LIVE else _first_week_days()
        if days is not None and _FIRST_WEEK_MIN_DAYS <= days <= _FIRST_WEEK_MAX_DAYS:
            self._add(self._make_first_week_card(days))

        self._add(self._make_section_header("Explore Tasks", "Choose a card below to configure launchers, tune displays, or run diagnostics."))
        # Windows transfer prominence (complaint #2) — shown above categories when NTFS found
        self._windows_transfer_card = self._make_windows_transfer_card()
        self._windows_transfer_card.hide()
        self._add(self._windows_transfer_card)
        self._build_category_section()
        self._stretch()

        if not IS_LIVE:
            single_shot(self, 0, self._refresh_system_status)
            single_shot(self, 0, self._refresh_ai_plan)

    # hero/hud/grid moved to _Welcome*Mixin (page_welcome_hero/hud/grid.py) — compose_on_first_init provides them

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
        self._ntfs_library_worker.failed.connect(lambda _k, _m: None)
        self._ntfs_library_worker.finished.connect(lambda: setattr(self, "_ntfs_library_worker", None))
        self._ntfs_library_worker.finished.connect(self._ntfs_library_worker.deleteLater)
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
        from concurrent.futures import ThreadPoolExecutor

        from .services.bootc import branch_display_name, current_branch, has_rollback_deployment, has_staged_update
        from .services.gaming import _find_ntfs_drives
        from .services.hardware import _detect_nvidia
        from .services.process import command_stdout

        # Fix 7: run 4 independent probes in parallel — portal/pipewire/nvidia/ntfs
        # previously ran serially ~9 s worst-case, now ~3 s (no bash -lc — direct systemctl, see Unit 1)
        def _portal():
            return command_stdout(
                ["systemctl", "--user", "is-active", "xdg-desktop-portal.service"],
                timeout=3,
            ) or "unknown"

        def _pipewire():
            return command_stdout(
                ["systemctl", "--user", "is-active", "pipewire.service"],
                timeout=3,
            ) or "unknown"

        with ThreadPoolExecutor(max_workers=4) as ex:
            f_portal = ex.submit(_portal)
            f_pipewire = ex.submit(_pipewire)
            f_branch = ex.submit(lambda: branch_display_name(current_branch()))
            f_staged = ex.submit(has_staged_update)
            f_rollback = ex.submit(has_rollback_deployment)
            f_windows = ex.submit(lambda: bool(_find_ntfs_drives()))
            f_nvidia = ex.submit(_detect_nvidia)
            portal = f_portal.result()
            pipewire = f_pipewire.result()
            branch = f_branch.result()
            staged = f_staged.result()
            rollback = f_rollback.result()
            windows_found = f_windows.result()
            has_nvidia = f_nvidia.result()
        return {
            "branch": branch,
            "staged": staged,
            "rollback": rollback,
            "windows_found": windows_found,
            "portal": portal,
            "pipewire": pipewire,
            "has_nvidia": has_nvidia,
        }

    def _refresh_system_status(self):
        if self._status_worker is not None:
            return
        from .services.gaming import DataWorker

        self._status_worker = DataWorker("welcome-status", self._gather_status_facts)
        self._status_worker.result.connect(self._on_status_facts_ready)
        self._status_worker.failed.connect(self._on_status_facts_failed)
        self._status_worker.finished.connect(lambda: setattr(self, "_status_worker", None))
        self._status_worker.finished.connect(self._status_worker.deleteLater)
        self._status_worker.start()

    @staticmethod
    def _gather_ai_plan() -> dict:
        try:
            from kyth_shared.ai_assist import build_repair_plan

            return build_repair_plan()
        except Exception as exc:
            return {"summary": f"AI check unavailable: {exc}", "actions": []}

    def _refresh_ai_plan(self):
        if self._ai_worker is not None:
            return
        from .services.gaming import DataWorker

        self._ai_worker = DataWorker("welcome-ai-plan", self._gather_ai_plan)
        self._ai_worker.result.connect(self._on_ai_plan_ready)
        self._ai_worker.failed.connect(lambda _k, _m: self._ai_desc.setText("AI check failed"))
        self._ai_worker.finished.connect(lambda: setattr(self, "_ai_worker", None))
        self._ai_worker.finished.connect(self._ai_worker.deleteLater)
        self._ai_worker.start()

    def _on_ai_plan_ready(self, _key: str, plan: object):
        if not isinstance(plan, dict):
            return
        summary = str(plan.get("summary", "")) or "System looks healthy. No repair actions needed."
        self._ai_desc.setText(summary)
        actions = plan.get("actions", [])
        # Show button only when at least one actionable item exists
        has_action = bool(actions) and any(a.get("id") != "refresh-probe" for a in actions if isinstance(a, dict))
        self._ai_btn.setVisible(bool(has_action))
        if has_action:
            self._ai_card.setObjectName("card-accent-warn")
        else:
            self._ai_card.setObjectName("card-accent-ok")
        restyle(self._ai_card)

    def _on_status_facts_failed(self, _key: str, message: str):
        # H4/M8: surface failure instead of leaving "Checking…" forever
        self._facts["branch"] = "Unavailable"
        self._facts["portal"] = f"check failed: {message}"
        self._facts["pipewire"] = "check failed"
        try:
            self._hud1_desc.setText(f"<b>Device:</b> {self._hostname}<br><b>Kernel:</b> {self._kernel}<br><b>Channel:</b> Unavailable")
            self._hud2_desc.setText(f"<b>Session Type:</b> {self._session}<br><b>Audio Engine:</b> check failed<br><b>Desktop Portal:</b> check failed")
        except Exception:
            pass

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

        # Show Windows transfer card when dual-boot detected (complaint #2)
        if hasattr(self, "_windows_transfer_card"):
            self._windows_transfer_card.setVisible(bool(windows_found))
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

            btn = QPushButton("✓ Done" if done else "Set Up")
            if not done:
                btn.setObjectName("primary")
            btn.setToolTip(text)
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

    def _make_windows_transfer_card(self) -> 'QFrame':
        """Prominent one-click Windows -> KythOS transfer (complaint #2)."""
        card, layout = _make_card("card-accent-ok")
        title = QLabel("🪟  Coming from Windows? Transfer in one click")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "KythOS found a Windows partition. Copy your Documents, Desktop, Downloads, "
            "browser bookmarks, and Steam saves to your new home — originals stay untouched. "
            "OneDrive/Dropbox can be re-connected on the next page."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        # Dynamic NTFS user dirs line — populated off-thread via _ntfs_user_dirs (2/5 reuse of drives probe)
        self._win_transfer_detail = QLabel("")
        self._win_transfer_detail.setObjectName("card-copy")
        self._win_transfer_detail.setWordWrap(True)
        self._win_transfer_detail.hide()
        layout.addWidget(self._win_transfer_detail)
        row = QHBoxLayout()
        row.setSpacing(8)
        go_btn = QPushButton("Transfer Files from Windows")
        go_btn.setObjectName("primary")
        go_btn.clicked.connect(lambda _=False: self._navigate("Move Files"))
        row.addWidget(go_btn)
        hw_btn = QPushButton("Check My Games First")
        hw_btn.clicked.connect(lambda _=False: self._navigate("Gaming"))
        row.addWidget(hw_btn)
        row.addStretch()
        layout.addLayout(row)
        # Kick off NTFS scan off GUI thread (probe_cached 30s, never auto-mounts BitLocker)
        try:
            from .services.migration import _ntfs_user_dirs
            from .services.runtime import DataWorker
            if not hasattr(self, "_win_dirs_worker") or self._win_dirs_worker is None:
                w = DataWorker("win-user-dirs", _ntfs_user_dirs)
                self._win_dirs_worker = w
                w.result.connect(lambda _k, dirs: self._on_win_dirs_ready(dirs))
                w.failed.connect(lambda _k, _m: None)
                w.finished.connect(lambda: setattr(self, "_win_dirs_worker", None))
                w.finished.connect(w.deleteLater)
                w.start()
        except Exception:
            pass
        return card

    def _on_win_dirs_ready(self, dirs: list[dict]) -> None:
        if not hasattr(self, "_win_transfer_detail") or self._win_transfer_detail is None:
            return
        found = [d for d in dirs if d.get("exists")]
        if not found:
            self._win_transfer_detail.hide()
            return
        # Summarize: e.g. "Found: Alice — Documents, Pictures (D:) · Bob — Documents"
        by_user: dict[str, list[str]] = {}
        mounts: set[str] = set()
        for d in found:
            by_user.setdefault(d.get("user", "?"), []).append(d.get("kind", "?"))
            mounts.add(d.get("mount", ""))
        parts = []
        for user, kinds in sorted(by_user.items()):
            parts.append(f"{user} — {', '.join(sorted(kinds))}")
        mount_hint = sorted(mounts)[0] if mounts else ""
        text = "Found on " + mount_hint + ": " + " · ".join(parts) if mount_hint else "Found: " + " · ".join(parts)
        self._win_transfer_detail.setText(text)
        self._win_transfer_detail.show()
        restyle(self._win_transfer_detail)

    def _dismiss_first_week(self, card: QFrame):
        try:
            os.makedirs(os.path.dirname(_FIRST_WEEK_DISMISS), exist_ok=True)
            with open(_FIRST_WEEK_DISMISS, "w", encoding="utf-8") as fh:
                fh.write(str(int(time.time())))
        except OSError:
            pass
        card.hide()

    # _make_section_header moved to _WelcomeGridMixin

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
        worker.finished.connect(worker.deleteLater)
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

    # _relayout_categories / _make_category_card moved to _WelcomeGridMixin
