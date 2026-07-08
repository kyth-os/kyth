import json
import os
from dataclasses import dataclass
from datetime import datetime
from urllib.request import Request, urlopen

# __KYTH_GENERATED_IMPORTS__
from .services.gaming import TrackedThread
from .qt import (  # noqa: E501
    QDesktopServices, QFrame, QHBoxLayout, QLabel, QPushButton, QThread, QUrl, QVBoxLayout, QWidget, Qt, Signal,
)
from .widgets import (  # noqa: E501
    Page, _make_card,
)

@dataclass(frozen=True)
class CompatGame:
    name: str
    anticheat: str
    status: str
    note: str
    checked: str
    source: str
    source_url: str


# ── Game compatibility data ────────────────────────────────────────────────────
# Status values: "native" | "proton" | "tweaks" | "blocked"
# Anti-cheat values used as display tags. Every entry carries a date/source so
# stale anti-cheat claims are easy to audit during release validation.
#
# The data lives in compat_games.json (bundled with this package) so it can be
# refreshed at runtime from the repo's main branch — anti-cheat status is the
# most volatile fact in Linux gaming and must not be frozen into an OS image.
_COMPAT_BUNDLED_PATH = os.path.join(os.path.dirname(__file__), "compat_games.json")
_COMPAT_CACHE_PATH = os.path.expanduser("~/.cache/kyth-compat-games.json")
_COMPAT_REMOTE_URL = (
    "https://raw.githubusercontent.com/mrtrick37/kyth/main/"
    "build_files/kyth-welcome/kyth_welcome/compat_games.json"
)
_COMPAT_STALE_DAYS = 45


def _parse_compat_payload(data: object) -> tuple[str, list[CompatGame]]:
    if not isinstance(data, dict):
        return "", []
    games: list[CompatGame] = []
    for entry in data.get("games", []):
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        status = str(entry.get("status", ""))
        if status not in ("native", "proton", "tweaks", "blocked"):
            continue
        games.append(CompatGame(
            name=str(entry.get("name", "")),
            anticheat=str(entry.get("anticheat", "None")),
            status=status,
            note=str(entry.get("note", "")),
            checked=str(entry.get("checked", "")),
            source=str(entry.get("source", "")),
            source_url=str(entry.get("source_url", "")),
        ))
    return str(data.get("updated", "")), games


def _load_compat_games() -> tuple[str, list[CompatGame]]:
    """Return the newest of the image-bundled data and the runtime cache."""
    best_date, best_games = "", []
    for path in (_COMPAT_BUNDLED_PATH, _COMPAT_CACHE_PATH):
        try:
            with open(path, encoding="utf-8") as fh:
                updated, games = _parse_compat_payload(json.load(fh))
        except (OSError, json.JSONDecodeError):
            continue
        if games and updated >= best_date:
            best_date, best_games = updated, games
    return best_date, best_games


_COMPAT_DATA_UPDATED, _COMPAT_GAMES = _load_compat_games()


def _adopt_compat_data(updated: str, games: list[CompatGame]) -> None:
    # Mutate the list in place so modules that imported _COMPAT_GAMES see it too.
    global _COMPAT_DATA_UPDATED
    _COMPAT_DATA_UPDATED = updated
    _COMPAT_GAMES[:] = games


def _compat_data_age_days() -> int | None:
    try:
        return (datetime.now() - datetime.strptime(_COMPAT_DATA_UPDATED, "%Y-%m-%d")).days
    except ValueError:
        return None


class _CompatRefreshWorker(TrackedThread):
    """Fetch newer compatibility data from the repo and cache it per-user."""
    refreshed = Signal(str, list)   # (updated, list[CompatGame])
    unchanged = Signal()

    def run(self):
        try:
            req = Request(_COMPAT_REMOTE_URL, headers={"User-Agent": "KythOS-Compat/1.0"})
            with urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
            updated, games = _parse_compat_payload(json.loads(raw))
            if not games or updated <= _COMPAT_DATA_UPDATED:
                self.unchanged.emit()
                return
            os.makedirs(os.path.dirname(_COMPAT_CACHE_PATH), exist_ok=True)
            with open(_COMPAT_CACHE_PATH, "w", encoding="utf-8") as fh:
                fh.write(raw)
            self.refreshed.emit(updated, games)
        except Exception:
            self.unchanged.emit()



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

    _STATUS_STYLE: dict[str, tuple[str, str, str]] = {
        # status → (badge_text, badge_css, row_left_border_color)
        "native":  ("Native",       "background:#121e2d; color:#4fc1ff; border:1px solid #1c3d60;",  "#4fc1ff"),
        "proton":  ("Works",        "background:#121e2d; color:#4fc1ff; border:1px solid #1c3d60;",  "#4fc1ff"),
        "tweaks":  ("Tweaks",       "background:#241808; color:#fbbf24; border:1px solid #f59e0b;",  "#f59e0b"),
        "blocked": ("Blocked",      "background:#3a1010; color:#f48771; border:1px solid #5a1a1a;",  "#f48771"),
    }
    _AC_BADGE_CSS = (
        "font-size:10px; font-weight:600; border-radius:3px; padding:1px 6px; "
        "background:#252526; color:#a6a6a6; border:1px solid #3c3c3c;"
    )

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
        ac_head.setObjectName("heading")
        ac_head.setStyleSheet("font-size:17px; font-weight:700; color:#ffffff;")
        self._add(ac_head)

        for ac_name, ac_status, ac_text in _COMPAT_AC_EXPLAINERS:
            card_name = "hw-card-ok" if ac_status == "ok" else "hw-card-err"
            card = QFrame()
            card.setObjectName(card_name)
            cl = QHBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)
            cl.setSpacing(14)
            dot = QLabel("✓" if ac_status == "ok" else "✗")
            dot.setStyleSheet(
                f"font-size:18px; font-weight:700; color:{'#4fc1ff' if ac_status == 'ok' else '#f48771'};"
                " background:transparent; border:none;"
            )
            dot.setFixedWidth(20)
            dot.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            cl.addWidget(dot)
            text_col = QVBoxLayout()
            text_col.setSpacing(3)
            name_lbl = QLabel(ac_name)
            name_lbl.setObjectName("card-title")
            name_lbl.setStyleSheet("font-size:13px;")
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
        games_head.setObjectName("heading")
        games_head.setStyleSheet("font-size:17px; font-weight:700; color:#ffffff;")
        self._add(games_head)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self._filter_all  = self._make_filter_btn("All",     None,        True)
        self._filter_works = self._make_filter_btn("Works",  ("native", "proton"), False)
        self._filter_tweaks = self._make_filter_btn("Tweaks", ("tweaks",), False)
        self._filter_blocked = self._make_filter_btn("Blocked", ("blocked",), False)
        for btn in (self._filter_all, self._filter_works, self._filter_tweaks, self._filter_blocked):
            filter_row.addWidget(btn)
        filter_row.addStretch()
        self._add_layout(filter_row)

        self._game_rows: list[tuple[QFrame, str]] = []  # (widget, status)
        self._active_filter: tuple | None = None
        self._games_rows_layout = QVBoxLayout()
        self._games_rows_layout.setSpacing(8)
        self._add_layout(self._games_rows_layout)
        self._rebuild_game_rows()

        # ── compatibility apps via Bottles / Lutris ─────────────────────────────────
        self._divider()
        winapps_head = QLabel("Known-working compatibility apps")
        winapps_head.setObjectName("heading")
        winapps_head.setStyleSheet("font-size:17px; font-weight:700; color:#ffffff;")
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
            badge_text, badge_css, border_color = CompatibilityPage._STATUS_STYLE.get(
                status, CompatibilityPage._STATUS_STYLE["tweaks"]
            )
            wa_row = QFrame()
            wa_row.setObjectName("hw-card-dim")
            wa_row.setStyleSheet(
                f"QFrame#hw-card-dim {{ border-left: 3px solid {border_color}; border-radius:4px; }}"
            )
            wa_rl = QHBoxLayout(wa_row)
            wa_rl.setContentsMargins(14, 8, 14, 8)
            wa_rl.setSpacing(10)
            wa_name = QLabel(name)
            wa_name.setObjectName("card-summary")
            wa_name.setStyleSheet("font-size:13px; font-weight:600;")
            wa_rl.addWidget(wa_name, 1)
            wa_tool_lbl = QLabel(f"  {tool}  ")
            wa_tool_lbl.setStyleSheet(
                "font-size:10px; font-weight:600; border-radius:3px; padding:1px 6px; "
                "background:#252526; color:#cccccc; border:1px solid #3c3c3c;"
            )
            wa_rl.addWidget(wa_tool_lbl)
            wa_badge = QLabel(f"  {badge_text}  ")
            wa_badge.setStyleSheet(badge_css + " border-radius:3px; padding:2px 8px; font-size:11px; font-weight:700;")
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
        cloud_head.setObjectName("heading")
        cloud_head.setStyleSheet("font-size:17px; font-weight:700; color:#ffffff;")
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
        self._refresh_worker = _CompatRefreshWorker()
        self._refresh_worker.refreshed.connect(self._on_compat_refreshed)
        self._refresh_worker.unchanged.connect(self._on_compat_unchanged)
        self._refresh_worker.start()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _update_summary(self, refresh_note: str = ""):
        works   = sum(1 for game in _COMPAT_GAMES if game.status in ("native", "proton", "tweaks"))
        blocked = sum(1 for game in _COMPAT_GAMES if game.status == "blocked")
        total   = len(_COMPAT_GAMES)
        oldest_check = min((game.checked for game in _COMPAT_GAMES), default="unknown")
        self._sum_title.setText(
            f"{works} of the {total} listed games work on KythOS — "
            f"including most of the Steam top 100."
        )
        self._sum_copy.setText(
            f"The {blocked} blocked titles are tracked conservatively: if a publisher blocks "
            "or refuses SteamOS/Proton, KythOS marks it blocked until release validation proves "
            f"otherwise. Oldest source check in this list: {oldest_check}."
        )
        age = _compat_data_age_days()
        if age is not None and age > _COMPAT_STALE_DAYS:
            self._freshness_lbl.setStyleSheet("font-size:11px; color:#d4a843;")
            note = (
                f"⚠ Compatibility data is {age} days old (updated {_COMPAT_DATA_UPDATED}). "
                "Double-check ProtonDB before relying on a specific title."
            )
        else:
            self._freshness_lbl.setStyleSheet("font-size:11px; color:#858585;")
            note = f"Compatibility data updated {_COMPAT_DATA_UPDATED or 'unknown'}."
        if refresh_note:
            note += f"  {refresh_note}"
        self._freshness_lbl.setText(note)

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
        btn.setCheckable(True)
        btn.setChecked(active)
        btn.setFixedHeight(28)
        btn.setStyleSheet(
            "QPushButton { border-radius:4px; padding:2px 14px; font-size:12px; "
            "background:#252526; color:#cccccc; border:1px solid #3c3c3c; }"
            "QPushButton:checked { background:#3a2d3a; color:#4fc1ff; border-color:#4fc1ff; }"
        )
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
        badge_text, badge_css, border_color = self._STATUS_STYLE.get(
            game.status, self._STATUS_STYLE["tweaks"]
        )
        row = QFrame()
        row.setObjectName("hw-card-dim")
        row.setStyleSheet(
            f"QFrame#hw-card-dim {{ border-left: 3px solid {border_color}; border-radius:4px; }}"
        )
        rl = QHBoxLayout(row)
        rl.setContentsMargins(14, 8, 14, 8)
        rl.setSpacing(10)

        name_lbl = QLabel(game.name)
        name_lbl.setObjectName("card-summary")
        name_lbl.setStyleSheet("font-size:13px; font-weight:600;")
        rl.addWidget(name_lbl, 1)

        tooltip = (
            f"{game.note}\n\n"
            f"Checked: {game.checked}\n"
            f"Source: {game.source}\n{game.source_url}"
        )
        name_lbl.setToolTip(tooltip)
        row.setToolTip(tooltip)

        ac_lbl = QLabel(game.anticheat)
        ac_lbl.setStyleSheet(self._AC_BADGE_CSS)
        ac_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ac_lbl.setFixedHeight(20)
        rl.addWidget(ac_lbl)

        checked_lbl = QLabel(game.checked)
        checked_lbl.setStyleSheet("font-size:10px; color:#858585;")
        checked_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rl.addWidget(checked_lbl)

        badge = QLabel(f"  {badge_text}  ")
        badge.setStyleSheet(
            badge_css + " border-radius:3px; padding:2px 8px; font-size:11px; font-weight:700;"
        )
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rl.addWidget(badge)

        return row
