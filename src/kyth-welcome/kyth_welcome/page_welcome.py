import os
import time
from datetime import datetime

# __KYTH_GENERATED_IMPORTS__
from .core_base import IS_LIVE, load_profile, restyle, save_profile
from .services.launch import reboot
from .services.setup_state import STEP_LABELS, STEP_RESUME_PAGE, incomplete_steps
from .services.welcome import (
    FIRST_WEEK_ITEMS,
    _FIRST_WEEK_DISMISS,
    gather_first_week_checklist,
    pulse_dest_tiles,
    pulse_greeting,
    pulse_next_step,
)
from .qt import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    Qt,
    Signal,
    single_shot,
)
from .widgets import (
    Page,
    _make_card,
)


class WelcomePage(Page):
    profile_changed = Signal(str)

    def __init__(self, navigate=None):
        super().__init__()
        self._navigate = navigate or (lambda _: None)
        self._profile = load_profile()

        uname = os.uname()
        self._hostname = uname.nodename or "This PC"
        self._kernel = uname.release or "unknown"
        self._session = os.environ.get("XDG_SESSION_TYPE", "unknown").capitalize()
        self._status_worker = None
        self._ntfs_libs: list[str] = []
        self._repair_needed = False
        self._action_target = "Apps"
        self._facts = {
            "branch": "Checking…",
            "staged": False,
            "rollback": False,
            "windows_found": False,
            "portal": "checking…",
            "pipewire": "checking…",
            "has_nvidia": False,
        }
        self._incomplete = [] if IS_LIVE else incomplete_steps(self._profile)
        self._apply_preset_worker = None
        self._ai_worker = None
        self._ntfs_library_worker = None
        self._win_dirs_worker = None
        self._first_week_worker = None

        self._build_pulse()
        self._stretch()
        self._refresh_pulse_action()

        if not IS_LIVE:
            single_shot(self, 0, self._refresh_system_status)
            single_shot(self, 0, self._refresh_ai_plan)
            single_shot(self, 0, self._refresh_ntfs_library_warning)

    def set_profile(self, profile: str) -> None:
        """Chrome mode switch — keep Pulse copy in sync without owning the toggle."""
        self._profile = profile
        self._apply_preset_btn.setText(f"Apply {profile.title()} settings")
        self._refresh_dest_tiles()
        self._refresh_pulse_action()
        self.profile_changed.emit(profile)

    def _build_pulse(self) -> None:
        self._greeting = QLabel(pulse_greeting(datetime.now().hour, self._hostname))
        self._greeting.setObjectName("pulse-greeting")
        self._add(self._greeting)

        self._subhead = QLabel("This PC is healthy · atomic updates · one-click rollback")
        self._subhead.setObjectName("pulse-subhead")
        self._subhead.setWordWrap(True)
        self._add(self._subhead)

        apply_row = QHBoxLayout()
        apply_row.setSpacing(10)
        self._apply_preset_btn = QPushButton(f"Apply {self._profile.title()} settings")
        self._apply_preset_btn.setToolTip("Apply the Everyday or Gaming desktop preset for this mode.")
        self._apply_preset_btn.clicked.connect(lambda _=False: self._apply_role_preset())
        apply_row.addWidget(self._apply_preset_btn)
        self._preset_status = QLabel("Ready to tune.")
        self._preset_status.setObjectName("status-dim")
        apply_row.addWidget(self._preset_status, 1)
        self._add_layout(apply_row)

        hero = QHBoxLayout()
        hero.setSpacing(20)
        hero.addWidget(self._make_orb(), 0, Qt.AlignmentFlag.AlignTop)
        hero.addWidget(self._make_action_card(), 1)
        self._add_layout(hero)

        self._add(self._make_facts_strip())
        self._add_layout(self._make_dest_tiles())

    def _make_orb(self) -> QFrame:
        self._orb = QFrame()
        self._orb.setObjectName("pulse-orb-ok")
        layout = QVBoxLayout(self._orb)
        layout.setContentsMargins(12, 28, 12, 28)
        layout.setSpacing(4)
        self._orb_label = QLabel("CLEAR")
        self._orb_label.setObjectName("pulse-orb-label")
        self._orb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._orb_label)
        self._orb_caption = QLabel("Guardian watching")
        self._orb_caption.setObjectName("pulse-orb-caption")
        self._orb_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._orb_caption.setWordWrap(True)
        layout.addWidget(self._orb_caption)
        return self._orb

    def _make_action_card(self) -> QFrame:
        card, layout = _make_card("pulse-action")
        self._action_title = QLabel("This PC is quiet")
        self._action_title.setObjectName("pulse-action-title")
        layout.addWidget(self._action_title)
        self._action_body = QLabel("Checking system health…")
        self._action_body.setObjectName("pulse-action-body")
        self._action_body.setWordWrap(True)
        layout.addWidget(self._action_body)
        self._action_detail = QLabel("")
        self._action_detail.setObjectName("pulse-action-body")
        self._action_detail.setWordWrap(True)
        self._action_detail.hide()
        layout.addWidget(self._action_detail)
        self._action_btn = QPushButton("Open Apps")
        self._action_btn.setObjectName("primary")
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.clicked.connect(lambda _=False: self._on_pulse_action())
        layout.addWidget(self._action_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self._action_card = card
        return card

    def _make_facts_strip(self) -> QFrame:
        strip = QFrame()
        strip.setObjectName("pulse-facts")
        row = QHBoxLayout(strip)
        row.setContentsMargins(18, 12, 18, 12)
        row.setSpacing(16)
        self._fact_values: dict[str, QLabel] = {}
        for key, value in (
            ("Device", self._hostname),
            ("Kernel", self._kernel),
            ("Channel", "Checking…"),
            ("Rollback", "Checking…"),
        ):
            col = QVBoxLayout()
            col.setSpacing(2)
            k = QLabel(key.upper())
            k.setObjectName("pulse-fact-key")
            col.addWidget(k)
            v = QLabel(value)
            v.setObjectName("pulse-fact-val")
            v.setWordWrap(True)
            col.addWidget(v)
            self._fact_values[key] = v
            row.addLayout(col, 1)
        return strip

    def _make_dest_tiles(self):
        row = QHBoxLayout()
        row.setSpacing(12)
        self._dest_tile_btns: list[QPushButton] = []
        for key, title, copy in pulse_dest_tiles(self._profile):
            btn = QPushButton(f"{title}\n{copy}")
            btn.setObjectName("pulse-dest-tile")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(88)
            btn._dest_key = key
            btn.clicked.connect(lambda _=False, b=btn: self._navigate(b._dest_key))
            self._dest_tile_btns.append(btn)
            row.addWidget(btn, 1)
        return row

    def _refresh_dest_tiles(self) -> None:
        tiles = pulse_dest_tiles(self._profile)
        buttons = getattr(self, "_dest_tile_btns", [])
        for btn, (key, title, copy) in zip(buttons, tiles):
            btn._dest_key = key
            btn.setText(f"{title}\n{copy}")
            restyle(btn)

    def _current_next_step(self):
        setup_target = ""
        if self._incomplete:
            setup_target = STEP_RESUME_PAGE.get(self._incomplete[0][0], "") or "Hardware"
        return pulse_next_step(
            staged=bool(self._facts.get("staged")),
            rollback=bool(self._facts.get("rollback")),
            windows_found=bool(self._facts.get("windows_found")),
            ntfs_library=bool(self._ntfs_libs),
            setup_incomplete=bool(self._incomplete),
            setup_target=setup_target,
            repair_needed=self._repair_needed,
            profile=self._profile,
        )

    def _refresh_pulse_action(self) -> None:
        step = self._current_next_step()
        self._action_target = step.target
        self._action_title.setText(step.title)
        self._action_body.setText(step.body)
        self._action_btn.setText(step.button)
        self._orb_label.setText(step.orb_label)
        self._orb_caption.setText(step.orb_caption)
        self._orb.setObjectName("pulse-orb-warn" if step.severity == "warn" else "pulse-orb-ok")
        restyle(self._orb)
        if step.severity == "ok" and not self._facts.get("staged"):
            self._subhead.setText("This PC is healthy · atomic updates · one-click rollback")
        elif step.severity == "warn":
            self._subhead.setText(step.orb_caption)

    def _on_pulse_action(self) -> None:
        if self._action_target == "reboot":
            reboot()
            return
        self._navigate(self._action_target)

    def _refresh_ntfs_library_warning(self):
        if self._ntfs_library_worker is not None:
            return
        from .services.gaming import DataWorker, _steam_libraries_on_ntfs
        from .services.runtime import guard_disposed

        self._ntfs_library_worker = DataWorker("ntfs-libraries", _steam_libraries_on_ntfs)
        self._ntfs_library_worker.result.connect(guard_disposed(self._on_ntfs_library_warning_ready))
        self._ntfs_library_worker.failed.connect(lambda _k, _m: None)
        self._ntfs_library_worker.finished.connect(lambda: setattr(self, "_ntfs_library_worker", None))
        self._ntfs_library_worker.finished.connect(self._ntfs_library_worker.deleteLater)
        self._ntfs_library_worker.start()

    def _on_ntfs_library_warning_ready(self, _key: str, libs: object):
        self._ntfs_libs = list(libs) if libs else []
        self._refresh_pulse_action()

    @staticmethod
    def _gather_status_facts() -> dict:
        """Run off the GUI thread by _refresh_system_status()'s DataWorker."""
        from concurrent.futures import ThreadPoolExecutor

        from .services.bootc import branch_display_name, current_branch, has_rollback_deployment, has_staged_update
        from .services.gaming import _find_ntfs_drives
        from .services.hardware import _detect_nvidia
        from .services.process import command_stdout

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
        from .services.runtime import guard_disposed

        self._status_worker = DataWorker("welcome-status", self._gather_status_facts)
        self._status_worker.result.connect(guard_disposed(self._on_status_facts_ready))
        self._status_worker.failed.connect(guard_disposed(self._on_status_facts_failed))
        self._status_worker.finished.connect(lambda: setattr(self, "_status_worker", None))
        self._status_worker.finished.connect(self._status_worker.deleteLater)
        self._status_worker.start()

    @staticmethod
    def _gather_ai_plan() -> dict:
        try:
            from kyth_shared.ai_assist import build_repair_plan

            return build_repair_plan()
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
            return {"summary": f"AI check unavailable: {exc}", "actions": []}

    def _refresh_ai_plan(self):
        if self._ai_worker is not None:
            return
        from .services.gaming import DataWorker
        from .services.runtime import guard_disposed

        self._ai_worker = DataWorker("welcome-ai-plan", self._gather_ai_plan)
        self._ai_worker.result.connect(guard_disposed(self._on_ai_plan_ready))
        self._ai_worker.failed.connect(lambda _k, _m: None)
        self._ai_worker.finished.connect(lambda: setattr(self, "_ai_worker", None))
        self._ai_worker.finished.connect(self._ai_worker.deleteLater)
        self._ai_worker.start()

    def _on_ai_plan_ready(self, _key: str, plan: object):
        if not isinstance(plan, dict):
            return
        actions = plan.get("actions", [])
        self._repair_needed = bool(actions) and any(
            a.get("id") != "refresh-probe" for a in actions if isinstance(a, dict)
        )
        self._refresh_pulse_action()

    def _on_status_facts_failed(self, _key: str, message: str):
        self._facts["branch"] = "Unavailable"
        self._facts["portal"] = f"check failed: {message}"
        self._facts["pipewire"] = "check failed"
        self._fact_values["Channel"].setText("Unavailable")
        self._fact_values["Rollback"].setText("Check failed")
        self._subhead.setText("Status check failed — search still finds every tool.")

    def _on_status_facts_ready(self, _key: str, facts: object):
        if not isinstance(facts, dict):
            return
        self._facts.update(facts)
        self._fact_values["Channel"].setText(str(self._facts.get("branch") or "Unknown"))
        if self._facts.get("staged"):
            self._fact_values["Rollback"].setText("Staged update ready")
        elif self._facts.get("rollback"):
            self._fact_values["Rollback"].setText("Ready")
        else:
            self._fact_values["Rollback"].setText("After first update")
        self._refresh_pulse_action()
        if self._facts.get("windows_found"):
            self._refresh_win_dirs()

    def _refresh_win_dirs(self) -> None:
        try:
            from .services.migration import _ntfs_user_dirs
            from .services.runtime import DataWorker, guard_disposed

            if self._win_dirs_worker is not None:
                return
            worker = DataWorker("win-user-dirs", _ntfs_user_dirs)
            self._win_dirs_worker = worker
            worker.result.connect(guard_disposed(lambda _k, dirs: self._on_win_dirs_ready(dirs)))
            worker.failed.connect(lambda _k, _m: None)
            worker.finished.connect(lambda: setattr(self, "_win_dirs_worker", None))
            worker.finished.connect(worker.deleteLater)
            worker.start()
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            pass

    def _on_win_dirs_ready(self, dirs: object) -> None:
        if not isinstance(dirs, list):
            return
        found = [d for d in dirs if isinstance(d, dict) and d.get("exists")]
        if not found:
            self._action_detail.hide()
            return
        by_user: dict[str, list[str]] = {}
        mounts: set[str] = set()
        for item in found:
            by_user.setdefault(item.get("user", "?"), []).append(item.get("kind", "?"))
            mounts.add(str(item.get("mount", "")))
        parts = [f"{user} — {', '.join(sorted(kinds))}" for user, kinds in sorted(by_user.items())]
        mount_hint = sorted(mounts)[0] if mounts else ""
        text = "Found on " + mount_hint + ": " + " · ".join(parts) if mount_hint else "Found: " + " · ".join(parts)
        self._action_detail.setText(text)
        self._action_detail.show()
        restyle(self._action_detail)

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
        title = QLabel(f"Day {days} checklist")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel("A short list to finish settling in. Hide it whenever you like.")
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        self._first_week_rows: list[tuple[QLabel, QPushButton]] = []
        for label, text, page_key in FIRST_WEEK_ITEMS:
            row = QHBoxLayout()
            row.setSpacing(10)
            badge = QLabel("Checking…")
            badge.setObjectName("task-status-idle")
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
            btn = QPushButton("Set Up")
            btn.setToolTip(text)
            btn.clicked.connect(lambda _=False, k=page_key: self._navigate(k))
            row.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
            layout.addLayout(row)
            self._first_week_rows.append((badge, btn))
        dismiss_row = QHBoxLayout()
        dismiss_btn = QPushButton("Got it — hide this")
        dismiss_btn.clicked.connect(lambda _=False, c=card: self._dismiss_first_week(c))
        dismiss_row.addWidget(dismiss_btn)
        dismiss_row.addStretch()
        layout.addLayout(dismiss_row)
        return card

    def _refresh_first_week(self) -> None:
        if self._first_week_worker is not None:
            return
        from .services.runtime import DataWorker, guard_disposed

        worker = DataWorker("first-week-checklist", gather_first_week_checklist)
        self._first_week_worker = worker
        worker.result.connect(guard_disposed(self._on_first_week_ready))
        worker.failed.connect(lambda _k, _m: None)
        worker.finished.connect(lambda: setattr(self, "_first_week_worker", None))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_first_week_ready(self, _key: str, flags: object) -> None:
        if not isinstance(flags, list):
            return
        rows = getattr(self, "_first_week_rows", ())
        for i, done in enumerate(flags):
            if i >= len(rows):
                break
            badge, btn = rows[i]
            done = bool(done)
            badge.setText("Done" if done else "Pending")
            badge.setObjectName("task-status-ok" if done else "task-status-idle")
            restyle(badge)
            btn.setText("✓ Done" if done else "Set Up")
            btn.setObjectName("primary" if not done else "")
            restyle(btn)

    def _dismiss_first_week(self, card: QFrame):
        try:
            os.makedirs(os.path.dirname(_FIRST_WEEK_DISMISS), exist_ok=True)
            with open(_FIRST_WEEK_DISMISS, "w", encoding="utf-8") as fh:
                fh.write(str(int(time.time())))
        except OSError:
            pass
        card.hide()

    def _apply_role_preset(self):
        if self._apply_preset_worker is not None:
            return
        profile = self._profile
        save_profile(profile)
        self._apply_preset_btn.setEnabled(False)
        self._preset_status.setObjectName("status-dim")
        self._preset_status.setText("Applying…")
        restyle(self._preset_status)

        from .services.gaming import DataWorker
        from .services.process import run_command
        from .services.runtime import guard_disposed

        worker = DataWorker(
            "apply-role-preset",
            lambda: run_command(["/usr/bin/kyth-apply-role-preset", profile], timeout=20),
        )
        self._apply_preset_worker = worker
        worker.result.connect(guard_disposed(lambda _key, result: self._on_role_preset_result(result, profile)))
        worker.failed.connect(guard_disposed(lambda _key, message: self._on_role_preset_result(None, profile, message)))
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
