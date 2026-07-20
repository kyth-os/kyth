from urllib.parse import urlencode

# __KYTH_GENERATED_IMPORTS__
from .core_base import _release_worker_when_finished
from .services.gaming import (
    _PROTONDB_TIER_STYLE, _ProtonDbBatchWorker, _detect_installed_games, _load_protondb_cache,
    _save_protondb_cache, find_compat_game, recommended_launcher_for_game, recommended_profile_for_game
)
from .services.gaming import _COMPAT_GAMES
from .qt import QComboBox, QDesktopServices, QFrame, QHBoxLayout, QLabel, QPushButton, QUrl, QVBoxLayout, Qt
from .widgets import _copy_text, _make_card


class _LibraryMixin:
    """Game readiness scanner and My Games dashboard — the GAMING HUB "library" section."""

    def _build_game_readiness_card(self):
        # ── Game readiness scanner ───────────────────────────────────────────
        scanner_card, scanner_layout = _make_card()
        scanner_title = QLabel("Game Readiness Scanner")
        scanner_title.setObjectName("card-title")
        scanner_layout.addWidget(scanner_title)
        scanner_desc = QLabel(
            "Search the KythOS compatibility list and get the recommended launcher, "
            "runner, launch profile, save step, and source check date."
        )
        scanner_desc.setObjectName("card-copy")
        scanner_desc.setWordWrap(True)
        scanner_layout.addWidget(scanner_desc)
        scanner_row = QHBoxLayout()
        scanner_row.setSpacing(8)
        self._readiness_combo = QComboBox()
        self._readiness_combo.setEditable(True)
        self._readiness_combo.setMinimumWidth(320)
        for game in sorted(_COMPAT_GAMES, key=lambda item: item.name.lower()):
            self._readiness_combo.addItem(game.name)
        scanner_row.addWidget(self._readiness_combo, 1)
        readiness_btn = QPushButton("Check Game")
        readiness_btn.setObjectName("primary")
        readiness_btn.clicked.connect(self._check_game_readiness)
        scanner_row.addWidget(readiness_btn)
        scanner_layout.addLayout(scanner_row)
        self._readiness_result = QLabel("Pick a game or type a title to check readiness.")
        self._readiness_result.setObjectName("card-copy")
        self._readiness_result.setWordWrap(True)
        scanner_layout.addWidget(self._readiness_result)
        scanner_btns = QHBoxLayout()
        scanner_btns.setSpacing(8)
        protondb_lookup = QPushButton("Open ProtonDB")
        protondb_lookup.clicked.connect(self._open_readiness_protondb)
        scanner_btns.addWidget(protondb_lookup)
        anticheat_lookup = QPushButton("Open Anti-Cheat Status")
        anticheat_lookup.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://areweanticheatyet.com")))
        scanner_btns.addWidget(anticheat_lookup)
        scanner_btns.addStretch()
        scanner_layout.addLayout(scanner_btns)
        self._add(scanner_card)

    def _build_my_games_card(self):
        # ── My Games dashboard ───────────────────────────────────────────────
        my_games_card, my_games_layout = _make_card()
        my_games_top = QHBoxLayout()
        my_games_title = QLabel("My Games")
        my_games_title.setObjectName("card-title")
        my_games_top.addWidget(my_games_title)
        my_games_top.addStretch()
        my_games_refresh = QPushButton("Scan Libraries")
        my_games_refresh.clicked.connect(lambda _=False: self._refresh_my_games(async_scan=True))
        my_games_top.addWidget(my_games_refresh)
        my_games_layout.addLayout(my_games_top)
        my_games_desc = QLabel(
            "Detects installed games from Steam, Heroic, Lutris, and Bottles, then "
            "adds KythOS compatibility and profile hints when a title matches the curated list."
        )
        my_games_desc.setObjectName("card-copy")
        my_games_desc.setWordWrap(True)
        my_games_layout.addWidget(my_games_desc)
        self._my_games_summary_lbl = QLabel("Scan libraries to build your local dashboard.")
        self._my_games_summary_lbl.setObjectName("card-copy")
        self._my_games_summary_lbl.setWordWrap(True)
        my_games_layout.addWidget(self._my_games_summary_lbl)
        self._my_games_rows_layout = QVBoxLayout()
        self._my_games_rows_layout.setSpacing(8)
        my_games_layout.addLayout(self._my_games_rows_layout)
        self._add(my_games_card)

    def _make_my_game_row(self, game_info: dict, protondb_tier: str = "") -> QFrame:
        compat = find_compat_game(_COMPAT_GAMES, game_info.get("name", ""))
        if compat is None:
            status = "dim"
            status_text = "Unknown"
            summary = "Not in curated list. ProtonDB rating shown when available."
            profile = "kyth-gamescope quality -- %command%"
        else:
            status = "ok" if compat.status in ("native", "proton") else "warn" if compat.status == "tweaks" else "err"
            status_text = {
                "native": "Native",
                "proton": "Works",
                "tweaks": "Tweaks",
                "blocked": "Blocked",
            }.get(compat.status, compat.status)
            summary = f"{compat.note} Checked {compat.checked} via {compat.source}."
            profile = recommended_profile_for_game(compat)

        row = QFrame()
        row.setObjectName("hw-card-dim")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        name_lbl = QLabel(game_info.get("name", "Unknown game"))
        name_lbl.setObjectName("card-summary")
        name_lbl.setStyleSheet("font-size:13px; font-weight:700;")
        top.addWidget(name_lbl, 1)
        launcher_lbl = QLabel(f"  {game_info.get('launcher', 'Unknown')}  ")
        launcher_lbl.setStyleSheet("font-size:10px; font-weight:600; border-radius:3px; padding:1px 6px; background:#252526; color:#cccccc; border:1px solid #3c3c3c;")
        top.addWidget(launcher_lbl)
        badge = QLabel(f"  {status_text}  ")
        badge_bg, badge_fg = {
            "ok": ("#121e2d", "#4fc1ff"),
            "warn": ("#241808", "#fbbf24"),
            "err": ("#3a1010", "#f48771"),
            "dim": ("#252526", "#858585"),
        }.get(status, ("#252526", "#858585"))
        badge.setStyleSheet(f"background:{badge_bg}; color:{badge_fg}; border:1px solid {badge_fg}; border-radius:3px; padding:2px 8px; font-size:11px; font-weight:700;")
        top.addWidget(badge)
        if compat is not None and compat.status == "blocked" and compat.anticheat and compat.anticheat.lower() not in ("none", ""):
            ac_badge = QLabel(f"  ⛔ {compat.anticheat}  ")
            ac_badge.setToolTip(
                f"Blocked by {compat.anticheat} anti-cheat — not supported on Linux. "
                "No workaround exists; this game requires other system."
            )
            ac_badge.setStyleSheet(
                "background:#3a1010; color:#f48771; border:1px solid #f48771;"
                " border-radius:3px; padding:2px 8px; font-size:11px; font-weight:700;"
            )
            top.addWidget(ac_badge)
        tier = protondb_tier.lower().strip()
        if tier and game_info.get("launcher") == "Steam":
            tier_bg, tier_fg = _PROTONDB_TIER_STYLE.get(tier, ("#252526", "#858585"))
            pdb_badge = QLabel(f"  PDB: {tier.capitalize()}  ")
            pdb_badge.setToolTip(f"ProtonDB community rating: {tier.capitalize()}")
            pdb_badge.setStyleSheet(
                f"background:{tier_bg}; color:{tier_fg}; border:1px solid {tier_fg};"
                " border-radius:3px; padding:2px 8px; font-size:11px; font-weight:700;"
            )
            top.addWidget(pdb_badge)
        layout.addLayout(top)

        detail = QLabel(
            f"{summary}\n"
            f"Profile: {profile}\n"
            f"Path: {game_info.get('path') or 'unknown'}"
        )
        detail.setObjectName("card-copy")
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(detail)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        copy_profile = QPushButton("Copy Profile")
        copy_profile.clicked.connect(lambda _=False, text=profile: _copy_text(text))
        btns.addWidget(copy_profile)
        path = game_info.get("path", "")
        if path:
            open_path = QPushButton("Open Folder")
            open_path.clicked.connect(lambda _=False, p=path: self._open_user_path(p))
            btns.addWidget(open_path)
        btns.addStretch()
        layout.addLayout(btns)
        return row

    def _refresh_my_games(self, async_scan: bool = False):
        self._clear_rows(self._my_games_rows_layout)
        self._my_games_summary_lbl.setText("Scanning installed game libraries…")
        if async_scan:
            self._start_data_worker("games", _detect_installed_games)
            return
        self._render_my_games(_detect_installed_games())

    def _render_my_games(self, games: list[dict], cache: dict[str, str] | None = None):
        self._last_detected_games = games
        if not hasattr(self, "_my_games_rows_layout"):
            return
        self._clear_rows(self._my_games_rows_layout)
        if not games:
            self._my_games_summary_lbl.setText(
                "No installed games detected yet. Install a game in Steam, Heroic, Lutris, or Bottles, then scan again."
            )
            return

        if cache is None:
            cache = _load_protondb_cache()

        matched = sum(1 for game in games if find_compat_game(_COMPAT_GAMES, game.get("name", "")))
        by_launcher: dict[str, int] = {}
        for game in games:
            launcher = game.get("launcher", "Unknown")
            by_launcher[launcher] = by_launcher.get(launcher, 0) + 1
        launcher_summary = ", ".join(f"{name}: {count}" for name, count in sorted(by_launcher.items()))
        self._my_games_summary_lbl.setText(
            f"Detected {len(games)} installed item(s); {matched} matched KythOS compatibility data. {launcher_summary}"
        )

        for game in games[:20]:
            appid = game.get("appid", "")
            tier = cache.get(appid, "") if appid else ""
            self._my_games_rows_layout.addWidget(self._make_my_game_row(game, tier))
        if len(games) > 20:
            more = QLabel(f"{len(games) - 20} more detected. Showing the first 20 to keep the dashboard fast.")
            more.setObjectName("card-copy")
            self._my_games_rows_layout.addWidget(more)

        uncached = [
            g.get("appid", "") for g in games
            if g.get("launcher") == "Steam" and g.get("appid") and g.get("appid") not in cache
        ]
        if uncached and (self._protondb_worker is None or not self._protondb_worker.isRunning()):
            self._protondb_worker = _ProtonDbBatchWorker(uncached, cache)
            self._protondb_worker.finished_all.connect(self._on_protondb_done)
            _release_worker_when_finished(self, "_protondb_worker", self._protondb_worker)
            self._protondb_worker.start()

    def _on_protondb_done(self, full_cache: dict):
        _save_protondb_cache(full_cache)
        if self._last_detected_games:
            self._render_my_games(self._last_detected_games, full_cache)

    def _check_game_readiness(self):
        query = self._readiness_combo.currentText()
        game = find_compat_game(_COMPAT_GAMES, query)
        if game is None:
            encoded = urlencode({"q": query.strip() or "game"})
            self._readiness_result.setText(
                "Not in the KythOS curated list yet. Check ProtonDB and Are We Anti-Cheat Yet, "
                f"then record the result in docs/gaming-results/. Search: https://www.protondb.com/search?{encoded}"
            )
            return

        status_label = {
            "native": "Native Linux",
            "proton": "Works via Proton",
            "tweaks": "Works with tweaks",
            "blocked": "Blocked by publisher/anti-cheat",
        }.get(game.status, game.status)
        save_note = (
            "Back up saves with Ludusavi before migrating or modding."
            if game.status != "blocked"
            else "Do not migrate saves until the game has a supported Linux path."
        )
        mod_note = (
            "Use the Modding guide before applying other system mod managers."
            if game.status != "blocked"
            else "Modding is irrelevant while the game is blocked."
        )
        self._readiness_result.setText(
            f"{game.name}: {status_label}\n"
            f"Anti-cheat/middleware: {game.anticheat}\n"
            f"Launcher: {recommended_launcher_for_game(game)}\n"
            f"Runner/profile: {recommended_profile_for_game(game)}\n"
            f"Saves: {save_note}\n"
            f"Mods: {mod_note}\n"
            f"Checked: {game.checked} via {game.source}\n"
            f"{game.note}"
        )

    def _open_readiness_protondb(self):
        query = self._readiness_combo.currentText().strip()
        if query:
            QDesktopServices.openUrl(QUrl(f"https://www.protondb.com/search?{urlencode({'q': query})}"))
        else:
            QDesktopServices.openUrl(QUrl("https://www.protondb.com"))
