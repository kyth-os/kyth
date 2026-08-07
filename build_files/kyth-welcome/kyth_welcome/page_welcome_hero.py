"""Welcome hero — hero/banner + vibe, split from page_welcome.py 737 (R7)."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

class _WelcomeHeroMixin:
    """Hero/banner helpers. No inline styles — uses QSS via objectName, avoids ai-slop purple gradient."""
    def _make_hero_banner(self, hero_view):
        container = QFrame()
        container.setObjectName("welcomeHero")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)
        kicker = QLabel(hero_view.get("kicker", "Welcome to KythOS — Windows apps & games, without Windows"))
        kicker.setObjectName("welcomeHeroKicker")
        kicker.setWordWrap(True)
        layout.addWidget(kicker)
        title = QLabel(hero_view.get("title", "System Hub"))
        title.setObjectName("welcomeHeroTitle")
        layout.addWidget(title)
        subtitle = QLabel(hero_view.get("subtitle", "Your files, your games, your drivers — ready out of the box."))
        subtitle.setObjectName("welcomeHeroSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        return container

    def _make_vibe_section(self):
        frame = QFrame()
        frame.setObjectName("vibeSection")
        layout = QVBoxLayout(frame)
        label = QLabel("Vibe")
        label.setObjectName("vibeLabel")
        layout.addWidget(label)
        return frame
