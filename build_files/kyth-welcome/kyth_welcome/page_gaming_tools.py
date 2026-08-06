# __KYTH_GENERATED_IMPORTS__
from .services.gaming import GAMING_TOOLS
from .qt import QLabel
from .page_gaming_tools_capture import _CaptureToolsMixin
from .page_gaming_tools_grid import _ToolsGridMixin
from .page_gaming_tools_launchers import _LauncherToolsMixin
from .page_gaming_tools_perf import _PerfTuningMixin
from .page_gaming_tools_proton import _ProtonToolsMixin


class _ToolsMixin(
    _ToolsGridMixin, _CaptureToolsMixin, _LauncherToolsMixin, _PerfTuningMixin, _ProtonToolsMixin,
):
    """Gaming Tools install grid, tuning cards, and Proton-CachyOS management — the GAMING HUB "setup"/"tuning" sections.

    Split by concern across sibling modules: the flatpak tool-tile grid
    (page_gaming_tools_grid), GPU/capture/streaming helpers
    (page_gaming_tools_capture), Heroic/Lutris launcher installers
    (page_gaming_tools_launchers), MangoHud/Gamescope/sched-ext/profile tuning
    (page_gaming_tools_perf), and Proton-CachyOS/GE-Proton/vkBasalt
    (page_gaming_tools_proton). This file only orchestrates the build order.
    """

    def _build_gaming_tools_section(self):
        # ── Gaming Tools ──────────────────────────────────────────────────────
        tools_head = QLabel("Gaming Tools")
        tools_head.setObjectName("section-heading")
        self._add(tools_head)
        tools_sub = QLabel(
            "Install the launchers and tools you want. "
            "Bottles is the easiest option for standalone `.exe` and `.msi` installers. "
            "Additional launchers and device tools are available here or via the corresponding ujust recipe."
        )
        tools_sub.setObjectName("card-copy")
        tools_sub.setWordWrap(True)
        self._add(tools_sub)

        self._TOOLS = GAMING_TOOLS

        self._build_tools_grid()
        self._build_capture_tools_card()
        self._build_opticscaler_card()
        # Add order intentionally puts the Discord fix card before the streaming
        # readiness card, even though the readiness card's widgets are what the
        # fix targets — preserves the original layout.
        self._build_discord_fix_card()
        self._build_streaming_readiness_card()
        self._build_launcher_setup_card()
        self._build_overlays_bulk_card()
        self._build_mangohud_card()
        if not self._wizard_mode:
            self._build_gamescope_card()
        self._build_profile_builder_card()
        if not self._wizard_mode:
            self._build_scx_card()
        self._build_proton_cachyos_card()
        if not self._wizard_mode:
            self._build_ge_proton_card()
            self._build_vkbasalt_card()
            self._build_combos_reference()
