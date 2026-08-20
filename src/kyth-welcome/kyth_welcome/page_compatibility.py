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
    Page, SegmentedTabBar, _make_card,
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

        self._filter_bar = SegmentedTabBar(
            [
                (None, "All"),
                (("native", "proton"), "Works"),
                (("tweaks",), "Tweaks"),
                (("blocked",), "Blocked"),
            ],
            active=None,
        )
        self._filter_bar.activated.connect(self._apply_filter)
        self._add(self._filter_bar)

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

        # ── Will My Games Run? — personal library scanner (Truth Engine) ──
        self._add(self._make_truth_engine_card())

        self._stretch()

        # Refresh the compatibility data in the background so blocked/working
        # status stays current between OS image updates.
        self._refresh_worker = CompatRefreshWorker()
        self._refresh_worker.refreshed.connect(self._on_compat_refreshed)
        self._refresh_worker.unchanged.connect(self._on_compat_unchanged)
        self._refresh_worker.start()

        # New #3: pre-flight — local GPU + HDR/VRR check for blocked titles
        try:
            from kyth_shared.system.gpu import lspci_gpu_lines

            gpu = "\n".join(lspci_gpu_lines()[:1])
            if gpu:
                self._sum_copy.setText(self._sum_copy.text() + f"\n\nLocal GPU: {gpu[:80]}")
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            pass

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

    def _apply_filter(self, statuses: tuple | None):
        self._active_filter = statuses
        for row, status in self._game_rows:
            row.setVisible(statuses is None or status in statuses)

    def _make_truth_engine_card(self):
        from .widgets import _make_card
        from .qt import QPushButton, QVBoxLayout
        card, layout = _make_card("card-accent-ok")
        title = QLabel("Will My Games Run? — scan your library")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Scans installed Steam manifests on this PC (no cloud login needed) and maps each title to KythOS compat data: "
            "Native/Works/Tweaks/Blocked with the vendor anti-cheat reason. Unknown titles suggest a ProtonDB check. "
            "Also scans a mounted Windows drive's Steam libraries when available."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        self._truth_status = QLabel("Click Scan to check the games installed here.")
        self._truth_status.setObjectName("card-copy")
        self._truth_status.setWordWrap(True)
        layout.addWidget(self._truth_status)
        self._truth_rows = QVBoxLayout()
        self._truth_rows.setSpacing(6)
        layout.addLayout(self._truth_rows)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        scan_btn = QPushButton("Scan Installed Games")
        scan_btn.setObjectName("primary")
        scan_btn.clicked.connect(self._run_truth_scan)
        btns.addWidget(scan_btn)
        btns.addStretch()
        layout.addLayout(btns)
        return card

    def _run_truth_scan(self):
        from .services.runtime import DataWorker, guard_disposed, release_worker_when_finished
        self._truth_status.setText("Scanning Steam libraries…")
        restyle(self._truth_status)
        while self._truth_rows.count():
            it = self._truth_rows.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        def _scan():
            try:
                from kyth_shared.gaming.truth_engine import classify_library, scan_steam_manifests
                from kyth_shared.gaming.compat_data import _COMPAT_GAMES as _G
                # Also include Windows-mounted libraries if probed
                extra_paths: list[str] = []
                try:
                    from kyth_welcome.services.gaming import _find_steam_libraries
                    for lib in (_find_steam_libraries() or []):
                        p = lib.get("path") if isinstance(lib, dict) else None
                        if p:
                            extra_paths.append(p)
                except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                    pass
                names = scan_steam_manifests(extra_paths if extra_paths else None)
                if not names:
                    # Fallback: scan default local paths too
                    names = scan_steam_manifests()
                result = classify_library(names, list(_G))
                result["names"] = names
                return result
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
                return {"error": str(exc), "total": 0, "buckets": {}}

        worker = DataWorker("truth-engine", _scan)
        worker.result.connect(guard_disposed(self._on_truth_result))
        worker.failed.connect(guard_disposed(lambda _k, msg: self._truth_status.setText(f"Scan failed: {msg}")))
        self._truth_worker = worker
        release_worker_when_finished(self, "_truth_worker", worker)
        worker.start()

    def _on_truth_result(self, _key: str, data: dict):
        if data.get("error"):
            self._truth_status.setText(f"Scan failed: {data['error']}")
            restyle(self._truth_status)
            return
        total = data.get("total", 0)
        if total == 0:
            self._truth_status.setText("No installed Steam games found here. Install Steam, launch it once, or mount your Windows Steam drive and rescan.")
            restyle(self._truth_status)
            return
        self._truth_status.setText(f"{data.get('summary','')}  (checked {total} titles)")
        self._truth_status.setObjectName("status-ok" if data.get("blocked", 0) == 0 else "status-warn")
        restyle(self._truth_status)
        # Show up to 8 per bucket
        for bucket in ("blocked", "tweaks", "unknown", "proton", "native"):
            items = (data.get("buckets") or {}).get(bucket) or []
            for item in items[:4]:
                name = item.get("name", "")
                note = item.get("note", "")[:90]
                status = item.get("status", bucket)
                badge, card_name, _ = self._STATUS_STYLE.get(status, self._STATUS_STYLE["tweaks"])
                if bucket == "unknown":
                    card_name = "hw-card-dim"
                    badge = "Unknown"
                row = QFrame()
                row.setObjectName(card_name)
                rl = QHBoxLayout(row)
                rl.setContentsMargins(12, 6, 12, 6)
                rl.setSpacing(10)
                lbl = QLabel(name)
                lbl.setObjectName("card-subtitle")
                lbl.setToolTip(note)
                rl.addWidget(lbl, 1)
                b = QLabel(badge)
                b.setObjectName("status-err" if bucket == "blocked" else ("status-warn" if bucket in ("tweaks","unknown") else "status-ok"))
                rl.addWidget(b)
                self._truth_rows.addWidget(row)

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
