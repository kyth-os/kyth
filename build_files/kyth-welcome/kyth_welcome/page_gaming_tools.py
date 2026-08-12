# __KYTH_GENERATED_IMPORTS__
from .services.gaming import GAMING_TOOLS
from .page_gaming_tools_capture import _CaptureToolsMixin
from .page_gaming_tools_grid import _ToolsGridMixin
from .page_gaming_tools_launchers import _LauncherToolsMixin
from .page_gaming_tools_perf import _PerfTuningMixin
from .page_gaming_tools_proton import _ProtonToolsMixin


from .widgets import _make_section_header

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
        hdr, _ = _make_section_header("Gaming Tools", "Install launchers and tools — Bottles is easiest for .exe/.msi")
        self._add(hdr)

        self._TOOLS = GAMING_TOOLS

        self._build_tools_grid()
        self._build_capture_tools_card()
        self._build_opticscaler_card()
        # Add order intentionally puts the Discord fix card before the streaming
        # readiness card, even though the readiness card's widgets are what the
        # fix targets — preserves the original layout.
        self._build_discord_fix_card()
        self._build_streaming_readiness_card()
        t_hdr, _ = _make_section_header("Launchers", "Heroic and Lutris for Epic/GOG")
        self._add(t_hdr)
        self._build_launcher_setup_card()
        hdr2, _ = _make_section_header("Performance", "Overlays, compositor and scheduler")
        self._add(hdr2)
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
