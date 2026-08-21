from typing import ClassVar

# __KYTH_GENERATED_IMPORTS__
from .lazy_page import compose_on_first_init
from .services import software_catalogs as _software_catalogs
from .services.runtime import DataWorker, Worker
from .qt import QPushButton, QWidget
from .widgets import Page, SegmentedTabBar, _divider


def _load_software_mixins() -> tuple[type, ...]:
    from .page_software_appimages import _AppImageTabMixin
    from .page_software_creator import _CreatorTabMixin
    from .page_software_developer import _DeveloperTabMixin
    from .page_software_flatpak import _FlatpakStoreTabMixin
    from .page_software_installed import _InstalledTabMixin
    from .page_software_security import _SecurityTabMixin
    from .page_software_starter import _StarterPackTabMixin
    return (
        _StarterPackTabMixin,
        _FlatpakStoreTabMixin,
        _AppImageTabMixin,
        _InstalledTabMixin,
        _DeveloperTabMixin,
        _SecurityTabMixin,
        _CreatorTabMixin,
    )


# ── Page: Software ────────────────────────────────────────────────────────────
# Tab mixins load on first construction; individual tabs build on first visit.
@compose_on_first_init(_load_software_mixins)
class SoftwarePage(Page):
    """App store — Starter Packs | Store | AppImages | Installed."""

    _STARTER_PACKS: ClassVar[list[dict]] = _software_catalogs.STARTER_PACKS
    _CR_TOOLS: ClassVar[list[dict]] = _software_catalogs.CR_TOOLS
    _SEC_BOX_NAME = _software_catalogs.SEC_BOX_NAME
    _SEC_BOX_IMAGE = _software_catalogs.SEC_BOX_IMAGE
    _SEC_HOST_TOOLS: ClassVar[list[dict]] = _software_catalogs.SEC_HOST_TOOLS
    _CURATED_APPIMAGES: ClassVar[list[dict]] = _software_catalogs.CURATED_APPIMAGES
    _FAMILIAR_APPS: ClassVar[list[tuple[str, str, str]]] = _software_catalogs.FAMILIAR_APPS
    _STORE_CATEGORIES: ClassVar[list[tuple[str, str]]] = _software_catalogs.STORE_CATEGORIES
    _TRENDING_APPS: ClassVar[list[str]] = _software_catalogs.TRENDING_APPS
    _STORE_SHELVES: ClassVar[list[dict]] = _software_catalogs.STORE_SHELVES

    def __init__(self, initial_tab: int = 0, store_landing: bool = False):
        super().__init__()
        self._initial_tab = initial_tab
        self._store_landing = store_landing

        # Worker references
        self._starter_worker: Worker | None = None
        self._uninstall_worker: Worker | None = None
        self._installed_list_worker: DataWorker | None = None
        self._uninstall_buttons: list[QPushButton] = []
        self._fp_search_worker: Worker | None = None
        self._fp_catalog_worker: Worker | None = None
        self._fp_refresh_worker: Worker | None = None
        self._fp_install_worker: Worker | None = None
        self._fp_uninstall_worker: Worker | None = None
        self._fp_search_lines: list[str] = []
        self._fp_catalog_lines: list[str] = []
        self._fp_catalog_entries: list[dict] = []
        self._fp_appstream_cache: dict[str, dict] | None = None
        self._fp_installing: str | None = None
        self._cr_tool_worker: Worker | None = None
        self._cr_active_tool_refs: dict | None = None
        self._cr_tool_refs: list[dict] = []
        self._dv_worker: Worker | None = None
        self._dv_selected_zip: str | None = None
        self._dev_worker: Worker | None = None
        self._sec_worker: Worker | None = None
        self._sec_host_tool_worker: Worker | None = None
        self._sec_active_host_refs: dict | None = None
        self._sec_host_tool_refs: list[dict] = []
        self._ms_fonts_worker: Worker | None = None
        self._ai_icon_path: str = ""

        # Starter pack per-pack state
        self._starter_pack_checks: dict = {}
        self._starter_pack_buttons: dict = {}
        self._starter_pack_details: dict = {}

        if store_landing:
            self._page_header(
                "Apps",
                "App Store",
                "Discover useful Flatpaks for KythOS, install them directly, and manage what you have.",
            )
        else:
            self._page_header(
                "Apps",
                "Software",
                "Starter packs, app migration helpers, AppImages, developer tools, and installed apps.",
            )

        # Tab bar — inserted into _outer between the page-header divider and the
        # scroll area. After _page_header(), _outer contains [hdr, div, scroll].
        # SegmentedTabBar (widgets.py) owns the button row/checked-state
        # bookkeeping; this page only decides what "activating a tab" does.
        tab_labels = ("Start", "Create", "Develop", "Security", "App Store", "AppImages", "Installed")
        self._tab_bar = SegmentedTabBar(list(enumerate(tab_labels)), active=self._initial_tab)
        self._tab_bar.activated.connect(self._switch_tab)
        self._outer.insertWidget(2, self._tab_bar)
        self._outer.insertWidget(3, _divider())

        self._current_tab = self._initial_tab
        self._tab_builders = (
            self._build_starter_tab,
            self._build_creator_tab,
            self._build_developer_tab,
            self._build_security_tab,
            self._build_flatpak_tab,
            self._build_appimage_tab,
            self._build_installed_tab,
        )
        # Build only the initial tab; other tabs on first visit.
        self._tab_widgets: list[QWidget | None] = [None] * len(self._tab_builders)
        self._ensure_tab(self._current_tab)
        self._stretch()

    def _ensure_tab(self, idx: int) -> QWidget:
        """Build tab *idx* on first visit and return its widget."""
        existing = self._tab_widgets[idx]
        if existing is not None:
            return existing
        tab_widget = self._tab_builders[idx]()
        self._add(tab_widget)
        tab_widget.setVisible(idx == self._current_tab)
        self._tab_widgets[idx] = tab_widget
        return tab_widget

    # ── Tab switching ──────────────────────────────────────────────────────────

    def _switch_tab(self, idx: int):
        if idx == self._current_tab:
            return
        # _build_installed_tab() already kicks off its own async refresh the
        # first time it's built (whether that happens here or from the
        # initial _ensure_tab() call in __init__) — only re-trigger it here
        # on a *revisit*, so switching to Installed doesn't fire the flatpak
        # list fetch twice back to back.
        already_built = self._tab_widgets[idx] is not None
        self._ensure_tab(idx)
        for i, widget in enumerate(self._tab_widgets):
            if widget is not None:
                widget.setVisible(i == idx)
        self._current_tab = idx
        if idx == 3:
            self._refresh_sec_status()
        elif idx == 6 and already_built:
            self._refresh_installed_list()

