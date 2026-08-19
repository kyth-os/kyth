# __KYTH_GENERATED_IMPORTS__
from ..actions import _install_flatpak_inline
from ..qt import QDesktopServices, QUrl
from ..widgets import _make_tip_card


class _ModsMixin:
    def _build_modding_migration_card(self):
        card, buttons = _make_tip_card(
            "Mods — Nexus, MO2, SteamTinkerLaunch",
            "Start with Steam Workshop and native mod managers when a game provides "
            "them. For Bethesda-style load orders, use SteamTinkerLaunch to install "
            "Mod Organizer 2 per game; use Bottles for standalone patchers and tools.",
            primary=None,
            buttons=[
                ("Open ProtonUp-Qt", lambda _=False: self._open_protonupqt()),
                # Bottles installs inline: the button disables/relabels
                # itself while running, so it needs a live reference to
                # itself — connected below instead of passed as callback.
                ("Install Bottles", None),
                (
                    "Modding Guide",
                    lambda: QDesktopServices.openUrl(
                        QUrl("https://github.com/mrtrick37/kyth/blob/main/docs/modding-on-kythos.md")
                    ),
                ),
            ],
        )
        bottles_btn = buttons[1]
        bottles_btn.clicked.connect(lambda _=False, b=bottles_btn: _install_flatpak_inline(
            self, b, "com.usebottles.bottles", "Bottles"))
        self._add(card)
