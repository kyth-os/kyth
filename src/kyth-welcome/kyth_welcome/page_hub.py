"""Pulse destination hubs — landings that route to existing Hub pages."""
from __future__ import annotations

from .qt import QFrame, QHBoxLayout, QLabel, QPushButton, Qt
from .widgets import Page, _make_card


def _hub_card(title: str, copy: str, page_key: str, navigate) -> QFrame:
    card, layout = _make_card("pulse-hub-card")
    heading = QLabel(title)
    heading.setObjectName("card-title")
    layout.addWidget(heading)
    body = QLabel(copy)
    body.setObjectName("card-copy")
    body.setWordWrap(True)
    layout.addWidget(body)
    btn = QPushButton(f"Open {title}")
    btn.setObjectName("primary")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(lambda _=False, k=page_key: navigate(k))
    layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)
    return card


def _hub_link(label: str, page_key: str, navigate) -> QPushButton:
    btn = QPushButton(label)
    btn.setObjectName("pulse-hub-link")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(lambda _=False, k=page_key: navigate(k))
    return btn


class _DestinationHubPage(Page):
    """Shared landing: title, child cards, optional footer links."""

    eyebrow = "Kyth Pulse"
    title = ""
    subtitle = ""
    cards: tuple[tuple[str, str, str], ...] = ()
    footer: tuple[tuple[str, str], ...] = ()

    def __init__(self, navigate=None):
        super().__init__()
        self._navigate = navigate or (lambda _key: None)
        self._page_header(self.eyebrow, self.title, self.subtitle)
        for heading, copy, key in self.cards:
            self._add(_hub_card(heading, copy, key, self._navigate))
        if self.footer:
            row = QHBoxLayout()
            row.setSpacing(8)
            for label, key in self.footer:
                row.addWidget(_hub_link(label, key, self._navigate))
            row.addStretch()
            self._add_layout(row)
        self._stretch()


class PlayHubPage(_DestinationHubPage):
    title = "Play"
    subtitle = "Games, boost, compatibility, and controllers — not a settings dump."
    cards = (
        ("Gaming", "Install launchers, scan libraries, and set up capture.", "Gaming"),
        ("Performance", "Tune power, scheduler, and Game Boost.", "Performance"),
        ("Compatibility", "Check ProtonDB context and known anti-cheat blocks.", "Compatibility"),
        ("Controllers", "Pair, test, and troubleshoot gamepads.", "Controllers"),
    )


class AppsHubPage(_DestinationHubPage):
    title = "Apps"
    subtitle = "Trusted installs and a workday that feels familiar."
    cards = (
        ("Discover Apps", "Install Flatpaks and find familiar alternatives.", "App Store"),
        ("Work Setup", "Office, mail, focus sessions, and workday conveniences.", "Work Setup"),
    )


class ThisPcHubPage(_DestinationHubPage):
    title = "This PC"
    subtitle = "Health, updates, hardware, and repair in one place."
    cards = (
        ("Guardian", "Self-healing checks, safe fixes, and local diagnosis.", "Guardian"),
        ("Updates", "Staged images, rollback, and auto-update settings.", "Update"),
        ("Hardware", "Graphics, displays, audio, Bluetooth, and storage.", "Hardware"),
        ("Desktop & displays", "HDR, VRR, portals, capture, and session repair.", "Plasma Wayland"),
        ("Health Report", "System checks and useful troubleshooting facts.", "Diagnostics"),
        ("Repair", "Rollback, restore, logs, and recovery tools.", "Repair"),
    )
    footer = (
        ("NVIDIA drivers", "NVIDIA"),
        ("Channels", "Channels"),
        ("Feedback", "Feedback"),
    )
