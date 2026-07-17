"""Wizard step builders — _WelcomeStepMixin."""
from __future__ import annotations

from ..core_base import _IS_LIVE, _has_rollback_deployment, _restyle, _save_profile
from ..services.gaming import _find_ntfs_drives, _proton_cachyos_version
from ..services.hardware import _detect_nvidia
from ..services.updates import _current_branch
from ..services.gaming import _COMPAT_GAMES
from ..qt import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget, Qt
from ..widgets import _make_card


class _WelcomeStepMixin:
    def _blocked_game_summary(self, limit: int = 5) -> str:
        blocked = [game for game in _COMPAT_GAMES if game.status == "blocked"]
        if not blocked:
            return ""
        names = [game.name for game in blocked[:limit]]
        summary = ", ".join(names)
        if len(blocked) > limit:
            summary += f", and {len(blocked) - limit} more"
        return summary


    def _make_switch_preflight_card(self) -> QFrame | None:
        rows: list[str] = []
        blocked_summary = self._blocked_game_summary()
        if blocked_summary:
            rows.append(
                "Known hard blockers: "
                f"{blocked_summary}. These are publisher anti-cheat decisions, not Proton settings."
            )
        if not _IS_LIVE and _find_ntfs_drives():
            rows.append(
                "PC game drive detected. Copy Steam libraries to a Linux-formatted disk before using Proton."
            )
        if _detect_nvidia():
            rows.append(
                "NVIDIA GPU detected. The driver page will verify the proprietary module and reboot state."
            )
        if _has_rollback_deployment():
            rows.append(
                "Rollback is available. If an update makes games worse, return to the previous image first."
            )
        if not rows:
            return None

        card, layout = _make_card("card-accent-warn")
        title = QLabel("Check these before moving your library")
        title.setObjectName("card-title")
        layout.addWidget(title)
        for text in rows:
            row = QLabel("- " + text)
            row.setObjectName("card-copy")
            row.setWordWrap(True)
            layout.addWidget(row)
        return card


    def _make_welcome_step(self) -> QWidget:
        page = QWidget()
        page.setObjectName("content-area")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Hero
        hero = QWidget()
        hero.setObjectName("wizard-hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(72, 60, 72, 54)
        hero_layout.setSpacing(16)

        logo = QLabel("KythOS")
        logo.setObjectName("wizard-logo")
        hero_layout.addWidget(logo)

        tagline = QLabel("Your PC games, running on Linux.")
        tagline.setObjectName("wizard-tagline")
        hero_layout.addWidget(tagline)

        hero_layout.addSpacing(8)

        desc = QLabel(
            "KythOS runs many Steam, Epic, and GOG games through Proton, then checks "
            "the traps PC players usually hit first: anti-cheat blockers, "
            "NTFS-formatted game drives, drivers, and rollback. Xbox and "
            "PlayStation controllers connect automatically."
        )
        desc.setObjectName("wizard-desc")
        desc.setWordWrap(True)
        hero_layout.addWidget(desc)

        # ── Usage profile ──────────────────────────────────────────────────
        # Drives which apps the Pick Apps step pre-selects and whether the
        # finish step offers the Work Setup handoff.
        hero_layout.addSpacing(10)
        profile_lbl = QLabel("What will you use this PC for?")
        profile_lbl.setObjectName("card-title")
        hero_layout.addWidget(profile_lbl)

        self._profile_buttons: dict[str, QPushButton] = {}
        profile_row = QHBoxLayout()
        profile_row.setSpacing(10)
        for key, label, tip in (
            ("everyday", "Everyday", "Apps, browser, files, cloud storage, VPN, printers, and updates."),
            ("gaming", "Gaming", "Steam, Discord, launchers, performance, and controller tools."),
        ):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.setMinimumHeight(38)
            btn.clicked.connect(lambda _=False, k=key: self._on_profile_chosen(k))
            self._profile_buttons[key] = btn
            profile_row.addWidget(btn)
        profile_row.addStretch()
        hero_layout.addLayout(profile_row)
        self._profile_buttons[self._profile].setChecked(True)

        preflight_card = self._make_switch_preflight_card()
        if preflight_card is not None:
            hero_layout.addWidget(preflight_card)

        outer.addWidget(hero, 1)
        outer.addWidget(_divider())

        # Stats bar
        stats_bar = QWidget()
        stats_bar.setObjectName("content-area")
        stats_layout = QHBoxLayout(stats_bar)
        stats_layout.setContentsMargins(72, 20, 72, 20)
        stats_layout.setSpacing(0)

        kernel = _command_stdout(["uname", "-r"]) or "unknown"
        pc_ver = _proton_cachyos_version() or "included"

        scx_sched = "Fedora"
        try:
            with open("/etc/scx/scx_loader.conf") as _scx_fh:
                for _scx_line in _scx_fh:
                    if _scx_line.startswith("SCX_SCHEDULER="):
                        scx_sched = _scx_line.split("=", 1)[1].strip().replace("scx_", "").upper()
                        break
        except OSError:
            pass

        stat_items = [
            ("Kernel", kernel),
            ("Proton-CachyOS", pc_ver),
            ("Scheduler", scx_sched),
        ]
        for i, (label, value) in enumerate(stat_items):
            if i > 0:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setFixedWidth(1)
                sep.setStyleSheet("background: #3a3a3a; border: none; max-width: 1px;")
                stats_layout.addSpacing(28)
                stats_layout.addWidget(sep)
                stats_layout.addSpacing(28)
            col = QVBoxLayout()
            col.setSpacing(4)
            lbl = QLabel(label.upper())
            lbl.setObjectName("stat-label")
            val = QLabel(value)
            val.setObjectName("stat-value")
            col.addWidget(lbl)
            col.addWidget(val)
            stats_layout.addLayout(col)

        stats_layout.addStretch()
        outer.addWidget(stats_bar)
        return page


