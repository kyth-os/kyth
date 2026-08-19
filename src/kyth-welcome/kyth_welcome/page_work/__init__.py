# __KYTH_GENERATED_IMPORTS__
from ._apps import _WorkAppsMixin
from ._m365 import _M365Mixin
from ._fonts import _FontsMixin
from ._pst import _PstMixin
from ._focus import _FocusMixin
from ._connect import _ConnectMixin
from ._dev import _DevMixin
from ..qt import QApplication, QTimer
from ..widgets import Page


class WorkSetupPage(Page, _WorkAppsMixin, _M365Mixin, _FontsMixin, _PstMixin, _FocusMixin, _ConnectMixin, _DevMixin):
    def __init__(self, navigate=None):
        super().__init__()
        self._navigate = navigate or (lambda _: None)
        self._ms_fonts_worker = None
        self._pst_worker = None
        self._focus_remaining = 0
        self._focus_warnings: list[str] = []
        self._focus_notification_cookie: int | None = None
        self._focus_inhibit_proc = None
        self._focus_timer = QTimer(self)
        self._focus_timer.setInterval(1000)
        self._focus_timer.timeout.connect(self._focus_tick)
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._cleanup_focus_session)

        self._page_header(
            "Apps",
            "Work Setup",
            "Everything a work machine needs before Monday morning: office apps, email, "
            "Microsoft 365, document fonts, VPN, network shares, cloud sync, and printing. "
            "Each step is optional \u2014 set up only what your workplace uses.",
        )

        self._add(self._make_work_apps_card())
        self._add(self._make_m365_card())
        self._add(self._make_fonts_card())
        self._add(self._make_pst_card())
        self._add(self._make_focus_card())
        self._add(self._make_connect_card())
        self._add(self._make_dev_card())
        self._stretch()
