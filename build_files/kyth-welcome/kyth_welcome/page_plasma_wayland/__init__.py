# __KYTH_GENERATED_IMPORTS__
from ._cards import _CardsMixin
from ._profiles import _ProfilesMixin
from ._polish import _PolishMixin
from ._repair import _RepairMixin
from ._refresh import _RefreshMixin
from ..qt import (  # noqa: E501
    QFrame, QHBoxLayout, QLabel, QTimer, QVBoxLayout, Qt,
)
from ..widgets import ActionRow, Page, _make_card


class PlasmaWaylandPage(Page, _CardsMixin, _ProfilesMixin, _PolishMixin, _RepairMixin, _RefreshMixin):
    def __init__(self):
        super().__init__()
        self._initial_refresh_started = False
        self._worker = None
        self._page_header(
            "System",
            "Plasma & Wayland",
            "Session readiness, screen sharing, display tuning, shortcuts, and Plasma repair tools.",
        )

        overview_card, overview_layout = _make_card("card-accent-ok")
        title = QLabel("Wayland readiness")
        title.setObjectName("card-title")
        overview_layout.addWidget(title)
        body = QLabel(
            "KythOS keeps a stable Plasma desktop today while preparing a stronger Wayland-first path. "
            "These checks focus on the pieces users notice first: portals, PipeWire capture, display "
            "behavior, visual polish, and session repair."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        overview_layout.addWidget(body)

        self._refresh_actions = ActionRow("Ready to check this Plasma session.", "idle")
        self._refresh_btn = self._refresh_actions.add_button("Refresh Readiness", self.refresh, primary=True)
        self._refresh_actions.finish()
        overview_layout.addWidget(self._refresh_actions)

        self._probe_rows = QVBoxLayout()
        self._probe_rows.setSpacing(8)
        overview_layout.addLayout(self._probe_rows)
        self._add(overview_card)

        self._add(self._make_settings_card())
        self._add(self._make_polish_card())
        self._add(self._make_repair_card())
        self._add(self._make_presets_card())
        self._add(self._make_desktop_modes_card())
        self._add(self._make_snap_grid_card())
        self._add(self._make_wayland_readiness_card())

        self._stretch()

    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_refresh_started:
            return
        self._initial_refresh_started = True
        QTimer.singleShot(0, self.refresh)
