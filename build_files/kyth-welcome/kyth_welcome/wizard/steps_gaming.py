"""Wizard step builders — _GamingStepMixin.

Gaming-profile-only step. The launcher grid at the bottom embeds the live
GamingPage's "setup" section (wizard_mode=True) rather than being
reimplemented here — it's a tested install flow (Heroic/Lutris/ProtonUp-Qt
workers), not the kind of full-page-as-a-step problem the Update/Hardware
steps were; everything above it is wizard-native.
"""
from __future__ import annotations

from ..core_base import IS_LIVE
from ..services.gaming import _COMPAT_GAMES, _find_ntfs_drives
from ..qt import QDesktopServices, QFrame, QHBoxLayout, QLabel, QPushButton, QUrl, QVBoxLayout, QWidget
from ..widgets import _divider, _make_card


class _GamingStepMixin:
    def _make_windows_game_drive_card(self, drives: list[dict]) -> QFrame:
        card, layout = _make_card("wiz-card-warn")
        title = QLabel("PC game drive found")
        title.setObjectName("wiz-card-title")
        layout.addWidget(title)
        names = []
        for drive in drives[:3]:
            label = drive.get("label") or drive.get("name") or drive.get("dev") or "PC drive"
            size = drive.get("size") or ""
            names.append(f"{label} {size}".strip())
        listed = ", ".join(names)
        if len(drives) > 3:
            listed += f", and {len(drives) - 3} more"
        body = QLabel(
            f"Detected: {listed}. Do not point Steam at the NTFS library and start playing. "
            "Copy the library into Steam on a Linux-formatted disk first, then let Proton "
            "build clean prefixes there. The migration tool below mounts other system read-only."
        )
        body.setObjectName("wiz-card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        return card


    def _make_gaming_step(self) -> QWidget:
        container = QWidget()
        container.setObjectName("wiz-body")
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        intro = QWidget()
        intro.setObjectName("wiz-body")
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(52, 40, 52, 20)
        intro_layout.setSpacing(8)
        pill_lbl = QLabel("GAMING SETUP")
        pill_lbl.setObjectName("wiz-pill")
        intro_layout.addWidget(pill_lbl)
        title_lbl = QLabel("Install your games.")
        title_lbl.setObjectName("wiz-heading")
        subtitle_lbl = QLabel(
            "Install launchers for Steam, Epic, GOG, and Battle.net below. "
            "Then follow the Proton steps to unlock your full game library."
        )
        subtitle_lbl.setObjectName("wiz-subheading")
        subtitle_lbl.setWordWrap(True)
        intro_layout.addWidget(title_lbl)
        intro_layout.addWidget(subtitle_lbl)
        outer.addWidget(intro)

        # ── Proton setup card ─────────────────────────────────────────────────
        proton_section = QWidget()
        proton_section.setObjectName("wiz-body")
        ps_layout = QVBoxLayout(proton_section)
        ps_layout.setContentsMargins(52, 6, 52, 0)
        ps_layout.setSpacing(10)

        windows_drives = [] if IS_LIVE else [
            d for d in _find_ntfs_drives() if not d.get("is_bitlocker")
        ]
        if windows_drives:
            ps_layout.addWidget(self._make_windows_game_drive_card(windows_drives))

        proton_head = QLabel("Enable Proton — play your entire game library")
        proton_head.setObjectName("wiz-card-title")
        proton_head.setStyleSheet("font-size: 15px;")
        ps_layout.addWidget(proton_head)

        proton_card, pc_layout = _make_card("wiz-card-ok")
        intro_copy = QLabel("Do this once after Steam finishes installing:")
        intro_copy.setObjectName("wiz-card-copy")
        pc_layout.addWidget(intro_copy)

        for step in [
            "1.  Open Steam",
            "2.  Steam  →  Settings  →  Compatibility",
            "3.  Turn on  Enable Steam Play for all other titles",
            "4.  Select  Proton-CachyOS  from the version dropdown",
            "5.  Restart Steam — your full game library now appears",
        ]:
            lbl = QLabel(step)
            lbl.setObjectName("wiz-card-copy")
            lbl.setStyleSheet("padding-left: 8px;")
            pc_layout.addWidget(lbl)

        tip = QLabel(
            "Proton-CachyOS is already installed on this system and kept up to date automatically."
        )
        tip.setObjectName("wiz-card-copy")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #34d399; margin-top: 6px;")
        pc_layout.addWidget(tip)
        ps_layout.addWidget(proton_card)
        outer.addWidget(proton_section)

        # ── Compatibility teaser ──────────────────────────────────────────────
        compat_section = QWidget()
        compat_section.setObjectName("wiz-body")
        cs_layout = QHBoxLayout(compat_section)
        cs_layout.setContentsMargins(52, 14, 52, 0)

        compat_card, cc_layout = _make_card("wiz-card")
        cc_layout.setSpacing(6)
        compat_lbl = QLabel("Check your must-play games now — before you commit an evening to one")
        compat_lbl.setObjectName("wiz-card-copy")
        compat_lbl.setStyleSheet("font-weight: 700; color: #f2f4fb;")
        cc_layout.addWidget(compat_lbl)
        # Front-load the hard wall: kernel-level anti-cheat is the #1 reason
        # other system switchers give up, and no Proton setting will ever fix it.
        # Showing the blocked titles here beats discovering them the hard way.
        blocked = [game for game in _COMPAT_GAMES if game.status == "blocked"]
        if blocked:
            blocked_names = "  ·  ".join(
                f"{game.name} ({game.anticheat})" for game in blocked
            )
            blocked_lbl = QLabel(
                f"Will NOT run — blocked by kernel-level anti-cheat on every Linux system: {blocked_names}."
            )
            blocked_lbl.setObjectName("wiz-card-copy")
            blocked_lbl.setWordWrap(True)
            blocked_lbl.setStyleSheet("color: #f7768e;")
            cc_layout.addWidget(blocked_lbl)
        compat_sub = QLabel(
            "The rest of the tracked list is marked native, works through Proton, or needs "
            "specific tweaks. The Compatibility page in the System Hub keeps the full list "
            "current, and ProtonDB has reports for nearly every Steam title."
        )
        compat_sub.setObjectName("wiz-card-copy")
        compat_sub.setWordWrap(True)
        compat_btn = QPushButton("Browse ProtonDB →")
        compat_btn.setObjectName("primary")
        compat_btn.setFixedWidth(200)
        compat_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://www.protondb.com"))
        )
        cc_layout.addWidget(compat_sub)
        cc_layout.addWidget(compat_btn)
        cs_layout.addWidget(compat_card, 1)

        outer.addWidget(compat_section)
        outer.addWidget(_divider())

        # ── Launcher grid (live GamingPage "setup" section) ───────────────────
        outer.addWidget(self._gaming_page, 1)
        return container
