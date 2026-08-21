# __KYTH_GENERATED_IMPORTS__
from ..lazy_page import compose_on_first_init
from ..qt import QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit, QVBoxLayout, QWidget, single_shot
from ..widgets import ActionRow, EmptyState, Page, _make_card, _make_flow_step


def _load_diagnostics_mixins() -> tuple[type, ...]:
    from ._security import _SecurityMixin
    from ._signin import _SigninMixin
    from ._storage_sense import _StorageSenseMixin
    from ._health import _HealthMixin
    return (_SecurityMixin, _SigninMixin, _StorageSenseMixin, _HealthMixin)


@compose_on_first_init(_load_diagnostics_mixins)
class DiagnosticsPage(Page):
    def __init__(self, navigate=None):
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

        # R6: AI control plane — same repair plan that Welcome/ Repair use,
        # shown here as a compact summary above hardware cards (no new probe).
        self._navigate = navigate or (lambda _k: None)
        self._ai_card, self._ai_layout = _make_card("card-accent-ok")
        self._ai_title = QLabel("AI Control Plane — offline")
        self._ai_title.setObjectName("card-title")
        self._ai_layout.addWidget(self._ai_title)
        self._ai_body = QLabel("AI check will run with the hardware probe.")
        self._ai_body.setObjectName("card-copy")
        self._ai_body.setWordWrap(True)
        self._ai_layout.addWidget(self._ai_body)
        # Phase 2 polish: deep-link to dedicated Guardian page
        ai_row = QHBoxLayout()
        ai_row.setSpacing(8)
        self._ai_guardian_btn = QPushButton("Open Guardian")
        self._ai_guardian_btn.setObjectName("primary")
        self._ai_guardian_btn.setToolTip("Open System → Guardian for fresh health history, recipes, and model controls.")
        self._ai_guardian_btn.clicked.connect(lambda _=False: self._navigate("Guardian"))
        ai_row.addWidget(self._ai_guardian_btn)
        ai_row.addStretch()
        self._ai_layout.addLayout(ai_row)
        self._ai_card.hide()
        self._add(self._ai_card)

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

        # ── Telemetry privacy 78 + perf gate 76 — offline opt-out ─────────────
        priv_card, priv_layout = _make_card()
        priv_title = QLabel("Telemetry & Perf Gate — offline")
        priv_title.setObjectName("card-title")
        priv_layout.addWidget(priv_title)
        priv_desc = QLabel("Telemetry is local-only (no cloud). Check collectors or purge. Perf gate fails CI if p95 regresses >5% vs ledger.")
        priv_desc.setWordWrap(True)
        priv_layout.addWidget(priv_desc)
        priv_row = QHBoxLayout()
        priv_row.setSpacing(8)
        self._priv_status = QLabel("Privacy: checking…")
        self._priv_status.setObjectName("status-muted")
        priv_row.addWidget(self._priv_status, 1)
        btn_purge = QPushButton("Purge")
        btn_purge.setToolTip("Remove /var/cache/kyth/telem and ledger")
        btn_purge.clicked.connect(lambda: self._run_priv("purge"))
        priv_row.addWidget(btn_purge)
        btn_gate = QPushButton("Gate")
        btn_gate.clicked.connect(lambda: self._run_priv("gate"))
        priv_row.addWidget(btn_gate)
        btn_priv = QPushButton("Status")
        btn_priv.clicked.connect(lambda: self._run_priv("status"))
        priv_row.addWidget(btn_priv)
        priv_layout.addLayout(priv_row)
        self._add(priv_card)

        self._stretch()

    def _run_priv(self, which: str):
        try:
            if which == "status":
                from kyth_shared.telemetry_opt import load_telemetry_opt, telemetry_collectors_status
                from kyth_shared.perf_gate import load_perf_gate, check_perf_gate

                t = load_telemetry_opt()
                g = load_perf_gate()
                self._priv_status.setText(f"telemetry {t['enabled']} collectors={len(telemetry_collectors_status())} gate thr={g['threshold']}%")
            elif which == "gate":
                from kyth_shared.perf_gate import check_perf_gate

                r = check_perf_gate(current_ms=16.0)
                self._priv_status.setText(f"gate pass={r.get('pass')} delta={r.get('delta', 'n/a')}")
            elif which == "purge":
                from kyth_shared.telemetry_opt import load_telemetry_opt

                # purge via helper
                from kyth_shared.commands import run

                run(["/usr/bin/kyth-telemetry-opt", "purge"])
                self._priv_status.setText("purged telemetry cache")
            from ..core_base import restyle

            restyle(self._priv_status)
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
            self._priv_status.setText(f"{which} failed — {exc}")
            from ..core_base import restyle

            restyle(self._priv_status)

    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_refresh_started:
            return
        self._initial_refresh_started = True
        single_shot(self, 0, self.refresh)
