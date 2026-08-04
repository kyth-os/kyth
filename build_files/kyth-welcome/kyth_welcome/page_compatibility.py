from typing import ClassVar

# __KYTH_GENERATED_IMPORTS__
from .core_base import restyle
from .services.workers import CompatRefreshWorker
from .services.gaming import compat_data
from .services.gaming.compat_data import (
    CompatGame,
    _COMPAT_GAMES,
    _COMPAT_STALE_DAYS,
    replace_compat_games,
    calculate_data_age_days,
    calculate_compat_stats,
)
from .qt import (
    QDesktopServices, QFrame, QHBoxLayout, QLabel, QPushButton, QUrl, QVBoxLayout, QWidget, Qt,
)
from .widgets import (
    Page, _make_card,
)


def _adopt_compat_data(updated: str, games: list[CompatGame]) -> None:
    # Mutate the shared service list so all importers see the refresh.
    replace_compat_games(updated, games)





_COMPAT_AC_EXPLAINERS: list[tuple[str, str, str]] = [
    # (ac_name, status, explanation)
    ("Valve Anti-Cheat (VAC)",
     "ok",
     "Runs in user-space inside the game process. Works on Linux without restriction."),
    ("Easy Anti-Cheat (EAC)",
     "ok",
     "Supports Linux natively — but only when the game developer flips the switch to enable it. "
     "EAC can run in kernel mode on another system; those games are blocked. Check per-game status below."),
    ("BattlEye",
     "ok",
     "Same story as EAC: full Linux support exists, but each developer must opt in. "
     "Most major BattlEye titles have enabled it. A few have not."),
    ("Vanguard / RICOCHET / Hyperion",
     "err",
     "These anti-cheats load a kernel-level driver at boot. There is no Linux equivalent "
     "and the vendors have not announced plans to change this. These games are currently unplayable on Linux."),
]


# ── Page: Compatibility ───────────────────────────────────────────────────────
class CompatibilityPage(Page):

    _STATUS_STYLE: ClassVar[dict[str, tuple[str, str, str]]] = {
        # status → (badge_text, hw-card objectName, status-badge objectName)
        "native":  ("Native",  "hw-card-ok",   "status-ok"),
        "proton":  ("Works",   "hw-card-ok",   "status-ok"),
        "tweaks":  ("Tweaks",  "hw-card-warn", "status-warn"),
        "blocked": ("Blocked", "hw-card-err",  "status-err"),
    }

    def __init__(self):
        super().__init__()
        self._page_header(
            "Gaming",
            "Game Compatibility",
            "Most of your library works. Here's the full picture before you switch.",
        )

        # ── Summary bar ───────────────────────────────────────────────────────
        sum_card, sum_layout = _make_card("card-accent-ok")
        sum_layout.setSpacing(4)
        self._sum_title = QLabel()
        self._sum_title.setObjectName("card-title")
        self._sum_title.setWordWrap(True)
        sum_layout.addWidget(self._sum_title)
        self._sum_copy = QLabel()
        self._sum_copy.setObjectName("card-copy")
        self._sum_copy.setWordWrap(True)
        sum_layout.addWidget(self._sum_copy)
        self._freshness_lbl = QLabel()
        self._freshness_lbl.setWordWrap(True)
        sum_layout.addWidget(self._freshness_lbl)
        self._update_summary(refresh_note="Checking for newer compatibility data…")
        self._add(sum_card)

        # ── Anti-cheat explainers ─────────────────────────────────────────────
        self._divider()
        ac_head = QLabel("How anti-cheat works on Linux")
        ac_head.setObjectName("section-heading")
        self._add(ac_head)

        for ac_name, ac_status, ac_text in _COMPAT_AC_EXPLAINERS:
            card_name = "hw-card-ok" if ac_status == "ok" else "hw-card-err"
            card = QFrame()
            card.setObjectName(card_name)
            cl = QHBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)
            cl.setSpacing(14)
            dot = QLabel("✓" if ac_status == "ok" else "✗")
            dot.setObjectName("glyph-ok" if ac_status == "ok" else "glyph-err")
            dot.setFixedWidth(20)
            dot.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            cl.addWidget(dot)
            text_col = QVBoxLayout()
            text_col.setSpacing(3)
            name_lbl = QLabel(ac_name)
            name_lbl.setObjectName("card-subtitle")
            desc_lbl = QLabel(ac_text)
            desc_lbl.setObjectName("card-copy")
            desc_lbl.setWordWrap(True)
            text_col.addWidget(name_lbl)
            text_col.addWidget(desc_lbl)
            cl.addLayout(text_col, 1)
            self._add(card)

        # ── Game list ─────────────────────────────────────────────────────────
        self._divider()
        games_head = QLabel("Notable games")
        games_head.setObjectName("section-heading")
        self._add(games_head)

        filter_bar = QFrame()
        filter_bar.setObjectName("segmented-tab-row")
        filter_row = QHBoxLayout(filter_bar)
        filter_row.setContentsMargins(16, 10, 16, 10)
        filter_row.setSpacing(8)
        self._filter_all  = self._make_filter_btn("All",     None,        True)
        self._filter_works = self._make_filter_btn("Works",  ("native", "proton"), False)
        self._filter_tweaks = self._make_filter_btn("Tweaks", ("tweaks",), False)
        self._filter_blocked = self._make_filter_btn("Blocked", ("blocked",), False)
        for btn in (self._filter_all, self._filter_works, self._filter_tweaks, self._filter_blocked):
            filter_row.addWidget(btn)
        filter_row.addStretch()
        self._add(filter_bar)

        self._game_rows: list[tuple[QFrame, str]] = []  # (widget, status)
        self._active_filter: tuple | None = None
        self._games_rows_layout = QVBoxLayout()
        self._games_rows_layout.setSpacing(8)
        self._add_layout(self._games_rows_layout)
        self._rebuild_game_rows()

        # ── compatibility apps via Bottles / Lutris ─────────────────────────────────
        self._divider()
        winapps_head = QLabel("Known-working compatibility apps")
        winapps_head.setObjectName("section-heading")
        self._add(winapps_head)

        winapps_intro = QLabel(
            "These apps run on KythOS via Bottles or Lutris. "
            "Use the Gaming page → Launcher setup to install launchers. "
            "For standalone .exe or .msi installers, open Bottles and create a new bottle."
        )
        winapps_intro.setObjectName("card-copy")
        winapps_intro.setWordWrap(True)
        self._add(winapps_intro)

        _WINAPPS: list[tuple[str, str, str, str]] = [
            # (name, status, tool, note)
            ("EA App",            "proton",  "Lutris",   "Use the Gaming page → Install EA App button. Installs via Lutris script."),
            ("Battle.net",        "proton",  "Lutris",   "Use the Gaming page → Install Battle.net. Installs Overwatch, Diablo, etc."),
            ("Ubisoft Connect",   "proton",  "Lutris",   "Use the Gaming page → Install Ubisoft Connect for Ubisoft game library."),
            ("Rockstar Launcher", "tweaks",  "Bottles",  "Create a Gaming bottle in Bottles and run the RGSC installer .exe."),
            ("Vortex (Nexus)",    "tweaks",  "Bottles",  "Create a Gaming bottle, install Vortex .exe. Works for most Bethesda mods."),
            ("GOG Galaxy",        "proton",  "Heroic",   "Heroic handles your GOG library natively — no GOG Galaxy needed."),
            ("Epic Games Store",  "proton",  "Heroic",   "Heroic replaces the Epic Games Launcher for your Epic library."),
            ("Xbox App",          "blocked", "—",        "No Linux client. Use Xbox Cloud Gaming (above) for Game Pass streaming."),
        ]
        for name, status, tool, note in _WINAPPS:
            badge_text, card_name, badge_name = CompatibilityPage._STATUS_STYLE.get(
                status, CompatibilityPage._STATUS_STYLE["tweaks"]
            )
            wa_row = QFrame()
            wa_row.setObjectName(card_name)
            wa_rl = QHBoxLayout(wa_row)
            wa_rl.setContentsMargins(14, 8, 14, 8)
            wa_rl.setSpacing(10)
            wa_name = QLabel(name)
            wa_name.setObjectName("card-subtitle")
            wa_rl.addWidget(wa_name, 1)
            wa_tool_lbl = QLabel(tool)
            wa_tool_lbl.setObjectName("status-dim")
            wa_rl.addWidget(wa_tool_lbl)
            wa_badge = QLabel(badge_text)
            wa_badge.setObjectName(badge_name)
            wa_badge.setToolTip(note)
            wa_rl.addWidget(wa_badge)
            note_lbl = QLabel(note)
            note_lbl.setObjectName("card-copy")
            note_lbl.setWordWrap(True)
            wa_vl = QVBoxLayout()
            wa_vl.setSpacing(0)
            wa_vl.addWidget(wa_row)
            note_lbl.setContentsMargins(17, 2, 0, 0)
            wa_vl.addWidget(note_lbl)
            container = QWidget()
            container.setLayout(wa_vl)
            self._add(container)

        # ── ProtonDB CTA ──────────────────────────────────────────────────────
        self._divider()
        pdb_card, pdb_layout = _make_card()
        pdb_title = QLabel("Check any game — ProtonDB")
        pdb_title.setObjectName("card-title")
        pdb_layout.addWidget(pdb_title)
        pdb_copy = QLabel(
            "ProtonDB has compatibility reports from thousands of Linux gamers for "
            "nearly every title on Steam. If a game isn't listed above, look it up there."
        )
        pdb_copy.setObjectName("card-copy")
        pdb_copy.setWordWrap(True)
        pdb_layout.addWidget(pdb_copy)
        pdb_btn = QPushButton("Open ProtonDB  →")
        pdb_btn.setObjectName("primary")
        pdb_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://www.protondb.com"))
        )
        pdb_layout.addWidget(pdb_btn)
        self._add(pdb_card)

        # ── Cloud Gaming — Xbox Game Pass workaround ──────────────────────────
        self._divider()
        cloud_head = QLabel("Cloud gaming (Xbox Game Pass workaround)")
        cloud_head.setObjectName("section-heading")
        self._add(cloud_head)

        cloud_card, cloud_layout = _make_card("card-accent-warn")
        cloud_title = QLabel("Xbox Game Pass — cloud streaming works today")
        cloud_title.setObjectName("card-title")
        cloud_layout.addWidget(cloud_title)
        cloud_body = QLabel(
            "The native Xbox app is not available natively here and there is no Linux client. "
            "However, Xbox Cloud Gaming (xCloud) streams your Game Pass library to any "
            "browser — no install required. Performance depends on your connection, "
            "and a controller is strongly recommended. For competitive or latency-sensitive games, "
            "keep a dual-boot or VM until a native solution ships."
        )
        cloud_body.setObjectName("card-copy")
        cloud_body.setWordWrap(True)
        cloud_layout.addWidget(cloud_body)
        cloud_btns = QHBoxLayout()
        cloud_btns.setSpacing(8)
        xbox_btn = QPushButton("Open Xbox Cloud Gaming")
        xbox_btn.setObjectName("primary")
        xbox_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://www.xbox.com/play"))
        )
        cloud_btns.addWidget(xbox_btn)
        cloud_btns.addStretch()
        cloud_layout.addLayout(cloud_btns)
        self._add(cloud_card)

        alt_card, alt_layout = _make_card()
        alt_title = QLabel("Other cloud gaming services — fully supported on Linux")
        alt_title.setObjectName("card-title")
        alt_layout.addWidget(alt_title)
        alt_body = QLabel(
            "These services work in Firefox or Chrome on KythOS with no configuration needed. "
            "GeForce NOW is the best option for library games you already own on Steam."
        )
        alt_body.setObjectName("card-copy")
        alt_body.setWordWrap(True)
        alt_layout.addWidget(alt_body)
        alt_btns = QHBoxLayout()
        alt_btns.setSpacing(8)
        for label, url in (
            ("GeForce NOW", "https://www.geforcenow.com"),
            ("Amazon Luna",  "https://luna.amazon.com"),
            ("Boosteroid",   "https://boosteroid.com"),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            alt_btns.addWidget(btn)
        alt_btns.addStretch()
        alt_layout.addLayout(alt_btns)
        self._add(alt_card)

        self._stretch()

        # Refresh the compatibility data in the background so blocked/working
        # status stays current between OS image updates.
        self._refresh_worker = CompatRefreshWorker()
        self._refresh_worker.refreshed.connect(self._on_compat_refreshed)
        self._refresh_worker.unchanged.connect(self._on_compat_unchanged)
        self._refresh_worker.start()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _update_summary(self, refresh_note: str = ""):
        stats = calculate_compat_stats(_COMPAT_GAMES)
        self._sum_title.setText(
            f"{stats.works} of the {stats.total} listed games work on KythOS — "
            f"including most of the Steam top 100."
        )
        self._sum_copy.setText(
            f"The {stats.blocked} blocked titles are tracked conservatively: if a publisher blocks "
            "or refuses SteamOS/Proton, KythOS marks it blocked until release validation proves "
            f"otherwise. Oldest source check in this list: {stats.oldest_check}."
        )
        age = calculate_data_age_days(compat_data._COMPAT_DATA_UPDATED)
        if age is not None and age > _COMPAT_STALE_DAYS:
            self._freshness_lbl.setObjectName("prop-val-orange")
            note = (
                f"⚠ Compatibility data is {age} days old (updated {compat_data._COMPAT_DATA_UPDATED}). "
                "Double-check ProtonDB before relying on a specific title."
            )
        else:
            self._freshness_lbl.setObjectName("caption-text")
            note = f"Compatibility data updated {compat_data._COMPAT_DATA_UPDATED or 'unknown'}."
        if refresh_note:
            note += f"  {refresh_note}"
        self._freshness_lbl.setText(note)
        restyle(self._freshness_lbl)

    def _rebuild_game_rows(self):
        while self._games_rows_layout.count():
            item = self._games_rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._game_rows = []
        for game in _COMPAT_GAMES:
            row = self._make_game_row(game)
            self._game_rows.append((row, game.status))
            self._games_rows_layout.addWidget(row)
        if self._active_filter is not None:
            for row, status in self._game_rows:
                row.setVisible(status in self._active_filter)

    def _on_compat_refreshed(self, updated: str, games: list):
        _adopt_compat_data(updated, games)
        self._rebuild_game_rows()
        self._update_summary(refresh_note="Refreshed just now.")

    def _on_compat_unchanged(self):
        self._update_summary()

    def _make_filter_btn(self, label: str, statuses: tuple | None, active: bool) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("segmented-tab")
        btn.setCheckable(True)
        btn.setChecked(active)
        btn.clicked.connect(lambda _=False, s=statuses: self._apply_filter(s))
        return btn

    def _apply_filter(self, statuses: tuple | None):
        self._active_filter = statuses
        for btn in (self._filter_all, self._filter_works, self._filter_tweaks, self._filter_blocked):
            btn.setChecked(False)
        if statuses is None:
            self._filter_all.setChecked(True)
        elif "blocked" in statuses:
            self._filter_blocked.setChecked(True)
        elif "tweaks" in statuses:
            self._filter_tweaks.setChecked(True)
        else:
            self._filter_works.setChecked(True)

        for row, status in self._game_rows:
            row.setVisible(statuses is None or status in statuses)

    def _make_game_row(self, game: CompatGame) -> QFrame:
        badge_text, card_name, badge_name = self._STATUS_STYLE.get(
            game.status, self._STATUS_STYLE["tweaks"]
        )
        row = QFrame()
        row.setObjectName(card_name)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(14, 8, 14, 8)
        rl.setSpacing(10)

        name_lbl = QLabel(game.name)
        name_lbl.setObjectName("card-subtitle")
        rl.addWidget(name_lbl, 1)

        tooltip = (
            f"{game.note}\n\n"
            f"Checked: {game.checked}\n"
            f"Source: {game.source}\n{game.source_url}"
        )
        name_lbl.setToolTip(tooltip)
        row.setToolTip(tooltip)

        ac_lbl = QLabel(game.anticheat)
        ac_lbl.setObjectName("status-dim")
        ac_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rl.addWidget(ac_lbl)

        checked_lbl = QLabel(game.checked)
        checked_lbl.setObjectName("prop-val-dim")
        checked_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rl.addWidget(checked_lbl)

        badge = QLabel(badge_text)
        badge.setObjectName(badge_name)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rl.addWidget(badge)

        return row
