"""Welcome hero — hero/banner + vibe, split from page_welcome.py 737 (R7)."""
from __future__ import annotations
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

class _WelcomeHeroMixin:
    """Hero/banner helpers. No inline styles — uses QSS via objectName, avoids ai-slop purple gradient."""
    def _make_hero_banner(self, hero_view):
        container = QFrame()
        container.setObjectName("welcomeHero")
        layout = QVBoxLayout(container)
        title = QLabel(hero_view.get("title", "System Hub"))
        title.setObjectName("welcomeHeroTitle")
        subtitle = QLabel(hero_view.get("subtitle", ""))
        subtitle.setObjectName("welcomeHeroSubtitle")
        layout.addWidget(title)
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
