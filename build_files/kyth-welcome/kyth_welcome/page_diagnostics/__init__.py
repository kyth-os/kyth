# __KYTH_GENERATED_IMPORTS__
from ._security import _SecurityMixin
from ._signin import _SigninMixin
from ._storage_sense import _StorageSenseMixin
from ._health import _HealthMixin
from ..qt import QLabel, QProgressBar, QPushButton, QTextEdit, QTimer, QVBoxLayout, QWidget
from ..widgets import ActionRow, EmptyState, Page, _make_card, _make_flow_step


class DiagnosticsPage(Page, _SecurityMixin, _SigninMixin, _StorageSenseMixin, _HealthMixin):
    def __init__(self):
        super().__init__()
        self._worker = None
        self._health_worker = None
        self._initial_refresh_started = False
        self._last_probes: list = []
        self._base_report = ""
        self._health_report = ""
        self._probe_cards: dict[str, object] = {}

        self._page_header(
            "System",
            "Health Report",
            "A quick look at how your hardware and system stack are doing.",
        )

        triage_card, triage_layout = _make_card()
        triage_title = QLabel("Health report triage")
        triage_title.setObjectName("card-title")
        triage_layout.addWidget(triage_title)
        for i, (title, copy) in enumerate((
            ("Summary first", "The banner tells you whether the system looks healthy, needs attention, or has a blocking issue."),
            ("Cards next", "Hardware and security rows point at the specific area: graphics, display, audio, network, storage, recovery, or sign-in."),
            ("Details last", "Technical logs stay collapsed until you need to copy, save, or attach them to an issue."),
        ), 1):
            triage_layout.addWidget(_make_flow_step(i, title, copy))
        self._add(triage_card)

        self._actions = ActionRow("Ready to run a fresh health report.", "idle")
        self._refresh_btn = self._actions.add_button("Run Health Report", self.refresh, primary=True)
        self._copy_btn = self._actions.add_button("Copy Report", self._copy_report)
        self._save_btn = self._actions.add_button("Save Report\u2026", self._save_report)
        self._issue_btn = self._actions.add_button("Report Issue", self._report_issue)
        self._actions.finish()
        self._copy_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._issue_btn.setEnabled(False)
        self._status_lbl = self._actions.status
        self._add(self._actions)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._add(self._progress)

        self._banner_card, self._banner_layout = _make_card()
        self._banner_title = QLabel()
        self._banner_title.setObjectName("card-title")
        self._banner_layout.addWidget(self._banner_title)
        self._banner_body = QLabel()
        self._banner_body.setObjectName("card-copy")
        self._banner_body.setWordWrap(True)
        self._banner_layout.addWidget(self._banner_body)
        self._banner_card.hide()
        self._add(self._banner_card)

        self._cards_widget = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(8)
        self._add(self._cards_widget)
        self._empty_state = EmptyState(
            "No checks to show yet",
            "Run a health report to populate hardware, security, and recovery checks.",
            "Run Health Report",
            self.refresh,
        )
        self._empty_state.hide()
        self._add(self._empty_state)

        self._raw_toggle = QPushButton("Show technical details")
        self._raw_toggle.setCheckable(True)
        self._raw_toggle.setChecked(False)
        self._raw_toggle.toggled.connect(self._toggle_raw)
        self._raw_toggle.hide()
        self._add(self._raw_toggle)

        self._report = QTextEdit()
        self._report.document().setMaximumBlockCount(5000)
        self._report.setReadOnly(True)
        self._report.setMinimumHeight(220)
        self._report.hide()
        self._add(self._report)

        self._add(self._make_security_card())
        self._add(self._make_signin_card())
        self._add(self._make_storage_sense_card())

        self._stretch()

    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_refresh_started:
            return
        self._initial_refresh_started = True
        QTimer.singleShot(0, self.refresh)
