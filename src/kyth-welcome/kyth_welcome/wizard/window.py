"""First-run wizard shell (navigation + step composition).

Kyth Theme rewrite: a left-hand step rail instead of the old top-dot progress
track, and a profile-adaptive step list — Everyday skips the Gaming Setup
step entirely rather than showing one fixed path to everyone. Step
completion is tracked per-step via services.setup_state (STEP_KEYS: machine,
apps, gaming) so closing the wizard early is resumable from System Hub's
Home page instead of silently marking everything done.
"""
from __future__ import annotations

from typing import ClassVar

from ..core_base import load_profile, restyle, save_profile
from ..services.runtime import running_threads
from ..qt import (
    QFrame, QHBoxLayout, QIcon, QLabel, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QStackedWidget, QTimer, QVBoxLayout, QWidget, Qt, single_shot,
)
from ..services.setup_state import STEP_KEYS, mark_step, mark_wizard_closed
from ..services.launch import popen
from .steps_apps import _AppsStepMixin, _default_checked_ids
from .steps_finish import _FinishStepMixin
from .steps_gaming import _GamingStepMixin
from .steps_machine import _MachineStepMixin
from .steps_welcome import _WelcomeStepMixin
from .steps_work import _WorkStepMixin

# (key, rail label, profile gate — None means shown for every profile)
_STEP_SPECS: list[tuple[str, str, str | None]] = [
    ("welcome", "Welcome", None),
    ("machine", "Your Machine", None),
    ("apps", "Get Apps", None),
    ("work", "Work Ready", None),
    ("gaming", "Gaming Setup", "gaming"),
    ("finish", "Finish", None),
]

_HINTS = {
    "welcome": "Pick a focus. You can change it later from Home.",
    "machine": "Recommended. A quick look at what's already tuned, plus anything worth knowing.",
    "apps": "Optional. Install extras now, or continue with the game-ready defaults.",
    "gaming": "Optional. Launcher and Proton tools stay available from Gaming.",
    "finish": "System Hub stays in the app menu whenever you need it.",
}


class WizardWindow(
    QMainWindow,
    _WelcomeStepMixin,
    _MachineStepMixin,
    _AppsStepMixin,
    _WorkStepMixin,
    _GamingStepMixin,
    _FinishStepMixin,
):
    """Profile-adaptive first-run wizard. Every close path (Finish, the
    window's close button, an early quit) runs through closeEvent, which
    records any step that was never explicitly finished or skipped as
    skipped — tracked and resumable, never silently discarded."""

    _STEP_SPECS: ClassVar[list[tuple[str, str, str | None]]] = _STEP_SPECS

    def __init__(self):
        super().__init__()
        self.setObjectName("wiz-window")
        self.setWindowTitle("Welcome to KythOS")
        self.setMinimumSize(900, 620)
        self.resize(1040, 720)

        self._profile = load_profile()
        self._handoff_win: QMainWindow | None = None
        # Lazy import avoids a circular import cycle with the hub package.
        from ..page_gaming import GamingPage
        self._gaming_page = GamingPage(wizard_mode=True)

        root = QWidget()
        root.setObjectName("wiz-window")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        content_row = QWidget()
        content_row.setObjectName("wiz-window")
        row_layout = QHBoxLayout(content_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        # ── Rail ──────────────────────────────────────────────────────────────
        rail = QWidget()
        rail.setObjectName("wiz-rail")
        rail.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        rail.setFixedWidth(236)
        rail_outer = QVBoxLayout(rail)
        rail_outer.setContentsMargins(22, 26, 22, 22)
        rail_outer.setSpacing(18)

        brand = QLabel("KythOS")
        brand.setObjectName("wiz-rail-brand")
        rail_outer.addWidget(brand)

        rail_title = QLabel("SETUP")
        rail_title.setObjectName("wiz-rail-title")
        rail_outer.addWidget(rail_title)

        self._rail_steps_layout = QVBoxLayout()
        self._rail_steps_layout.setContentsMargins(0, 0, 0, 0)
        self._rail_steps_layout.setSpacing(0)
        rail_outer.addLayout(self._rail_steps_layout)
        rail_outer.addStretch(1)
        row_layout.addWidget(rail)

        # ── Content stack ─────────────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.setObjectName("wiz-window")
        row_layout.addWidget(self._stack, 1)
        root_layout.addWidget(content_row, 1)

        # Step content isn't guaranteed to fit the window (the Get Apps
        # checklist and the Gaming step's proton/compat cards + embedded
        # launcher grid can easily exceed it) — each step is built as a plain
        # fixed-layout QWidget, so without a scroll wrapper Qt compresses it
        # into corrupted, overlapping geometry instead of scrolling. Wrap each
        # one in its own QScrollArea; _go_to navigates via _step_scrollers,
        # while _steps keeps direct references to each step's own widgets.
        self._steps: dict[str, QWidget] = {
            "welcome": self._make_welcome_step(),
            "machine": self._make_machine_step(),
            "apps": self._make_first_run_apps_step(),
            "gaming": self._make_gaming_step(),
            "finish": self._make_finish_step(),
        }
        self._step_scrollers: dict[str, QScrollArea] = {}
        for key, widget in self._steps.items():
            scroller = QScrollArea()
            scroller.setObjectName("wiz-window")
            scroller.setWidgetResizable(True)
            scroller.setFrameShape(QFrame.Shape.NoFrame)
            scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroller.setWidget(widget)
            self._step_scrollers[key] = scroller
            self._stack.addWidget(scroller)

        self._rail_num_labels: dict[str, QLabel] = {}
        self._rail_text_labels: dict[str, QLabel] = {}
        self._rail_rules: list[QFrame] = []
        self._rail_built_for: list | None = None
        self._build_rail()

        # ── Footer ────────────────────────────────────────────────────────────
        footer = QWidget()
        footer.setObjectName("wiz-footer")
        footer.setFixedHeight(68)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(36, 0, 36, 0)
        footer_layout.setSpacing(10)

        self._back_btn = QPushButton("← Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.clicked.connect(self._go_back)
        footer_layout.addWidget(self._back_btn)
        self._step_hint = QLabel("")
        self._step_hint.setObjectName("wiz-footer-hint")
        self._step_hint.setWordWrap(True)
        footer_layout.addWidget(self._step_hint, 1)

        self._skip_btn = QPushButton("Skip for now")
        self._skip_btn.clicked.connect(self._go_skip)
        footer_layout.addWidget(self._skip_btn)

        self._next_btn = QPushButton("Get Started  →")
        self._next_btn.setObjectName("primary")
        self._next_btn.setFixedWidth(160)
        self._next_btn.clicked.connect(self._go_next)
        footer_layout.addWidget(self._next_btn)
        root_layout.addWidget(footer)

        self._current_key = "welcome"
        self._stack.setCurrentWidget(self._step_scrollers["welcome"])
        self._busy_timer = QTimer(self)
        self._busy_timer.setInterval(250)
        self._busy_timer.timeout.connect(self._update_nav)
        self._busy_timer.start()
        self._update_nav()

        # Every step above was just built from safe, subprocess-free
        # defaults (see steps_machine.py's module docstring) — fetch the
        # real NVIDIA/bootc/NTFS facts off the GUI thread now that the
        # window itself is fully constructed, instead of blocking this
        # __init__ (and therefore the very first frame shown on a fresh
        # install) on lspci/bootc status/lsblk.
        single_shot(self, 0, self._refresh_machine_facts)

    # ── Step/profile plumbing ───────────────────────────────────────────────────

    def _active_specs(self) -> list[tuple[str, str, str | None]]:
        return [s for s in self._STEP_SPECS if s[2] is None or s[2] == self._profile]

    def _current_index(self, specs: list[tuple[str, str, str | None]]) -> int:
        keys = [s[0] for s in specs]
        return keys.index(self._current_key) if self._current_key in keys else 0

    def _build_rail(self) -> None:
        specs = self._active_specs()
        if specs == self._rail_built_for:
            return
        self._rail_built_for = specs

        layout = self._rail_steps_layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
                continue
            sub = item.layout()
            if sub is not None:
                while sub.count():
                    sub_item = sub.takeAt(0)
                    sub_widget = sub_item.widget()
                    if sub_widget is not None:
                        sub_widget.setParent(None)
                        sub_widget.deleteLater()

        self._rail_num_labels = {}
        self._rail_text_labels = {}
        self._rail_rules = []
        for i, (key, label, _gate) in enumerate(specs):
            if i > 0:
                rule = QFrame()
                rule.setObjectName("wiz-rail-rule-upcoming")
                rule.setFixedWidth(1)
                rule.setFixedHeight(14)
                rule_row = QHBoxLayout()
                rule_row.setContentsMargins(0, 0, 0, 0)
                rule_row.addSpacing(13)
                rule_row.addWidget(rule)
                rule_row.addStretch(1)
                layout.addLayout(rule_row)
                self._rail_rules.append(rule)

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 6, 0, 6)
            row_layout.setSpacing(12)
            num = QLabel(str(i + 1))
            num.setFixedSize(26, 26)
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setObjectName("wiz-step-num-upcoming")
            row_layout.addWidget(num)
            text = QLabel(label)
            text.setObjectName("wiz-step-label-upcoming")
            row_layout.addWidget(text, 1)
            layout.addWidget(row)
            self._rail_num_labels[key] = num
            self._rail_text_labels[key] = text

    def _on_profile_chosen(self, profile: str):
        self._profile = profile
        for key, card in self._profile_cards.items():
            card.set_checked(key == profile)
        save_profile(profile)
        popen(["/usr/bin/kyth-apply-role-preset", profile])
        # Re-seed the Get Apps defaults to match the chosen profile. Only
        # enabled boxes are touched — already-installed apps stay locked.
        wanted = _default_checked_ids(profile)
        for check, app_id, _name in self._wizard_extra_checks:
            if check.isEnabled():
                check.setChecked(app_id in wanted)
        if hasattr(self, "_finish_work_btn"):
            self._finish_work_btn.setVisible(profile == "everyday")
        self._build_rail()
        self._update_nav()

    def _open_hub_at(self, page_key: str):
        """Hand off from the wizard to the System Hub opened at a page.
        closeEvent (fired by self.close()) records any not-yet-decided step
        as skipped, so this is safe to call from any step."""
        from ..windows import MainWindow
        main_win = MainWindow()
        main_win.setWindowIcon(QIcon.fromTheme("kyth"))
        main_win.showMaximized()
        main_win._navigate_to(page_key)
        self._handoff_win = main_win
        self.close()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _has_running_operation(self) -> bool:
        return any(t.BLOCKS_CLOSE for t in running_threads())

    def _update_nav(self):
        specs = self._active_specs()
        idx = self._current_index(specs)
        operation_busy = self._has_running_operation()
        self._step_hint.setText(_HINTS.get(self._current_key, ""))

        for i, (key, _label, _gate) in enumerate(specs):
            num = self._rail_num_labels.get(key)
            text = self._rail_text_labels.get(key)
            if num is None or text is None:
                continue
            if i < idx:
                num.setText("✓")
                num.setObjectName("wiz-step-num-done")
                text.setObjectName("wiz-step-label-done")
            elif i == idx:
                num.setText(str(i + 1))
                num.setObjectName("wiz-step-num-active")
                text.setObjectName("wiz-step-label-active")
            else:
                num.setText(str(i + 1))
                num.setObjectName("wiz-step-num-upcoming")
                text.setObjectName("wiz-step-label-upcoming")
            restyle(num)
            restyle(text)

        for i, rule in enumerate(self._rail_rules):
            rule.setObjectName("wiz-rail-rule-done" if i < idx else "wiz-rail-rule-upcoming")
            restyle(rule)

        self._back_btn.setVisible(idx > 0)
        self._skip_btn.setVisible(self._current_key in STEP_KEYS)
        self._back_btn.setEnabled(not operation_busy)
        self._skip_btn.setEnabled(not operation_busy)
        self._next_btn.setEnabled(not operation_busy)

        if self._current_key == "finish":
            self._next_btn.setText("Close")
        elif self._current_key == "welcome":
            self._next_btn.setText("Get Started  →")
        else:
            self._next_btn.setText("Next  →")

    def _go_to(self, key: str) -> None:
        self._current_key = key
        self._stack.setCurrentWidget(self._step_scrollers[key])
        if key == "finish":
            self._refresh_finish_status()
        self._update_nav()

    def _go_back(self):
        specs = self._active_specs()
        idx = self._current_index(specs)
        if idx > 0:
            self._go_to(specs[idx - 1][0])

    def _advance(self, mark_status: str | None) -> None:
        specs = self._active_specs()
        idx = self._current_index(specs)
        key = specs[idx][0]
        if mark_status is not None and key in STEP_KEYS:
            mark_step(key, mark_status)
        if idx == len(specs) - 1:
            self.close()
            return
        self._go_to(specs[idx + 1][0])

    def _go_next(self):
        self._advance("done")

    def _go_skip(self):
        self._advance("skipped")

    def closeEvent(self, event):
        if self._has_running_operation():
            QMessageBox.warning(
                self,
                "KythOS Is Busy",
                "A setup task is still running. Cancel it from the current page while cancellation is available, or wait for it to finish before closing.",
            )
            event.ignore()
            self.raise_()
            self.activateWindow()
            return
        mark_wizard_closed(self._profile)
        super().closeEvent(event)
