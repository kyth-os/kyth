"""Work dev toolbox card — brew/distrobox/copr/cachy opt-in (N30)."""
from __future__ import annotations

from ..qt import QHBoxLayout, QLabel, QPushButton
from ..widgets import _make_card
from ..services.runtime import Worker
from kyth_shared.commands import ujust_command


class _DevMixin:
    def _make_dev_card(self):
        card, layout = _make_card()
        title = QLabel("Developer Toolbox — brew / distrobox / COPR / cachy")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel("Veteran flexibility without base bloat: Homebrew, distrobox, COPR, cachy kernel — all opt-in via just, base stays vanilla (Endeavour/Aurora parity).")
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        row = QHBoxLayout()
        row.setSpacing(8)
        for label, recipe in (("Enable Brew", "enable-brew"), ("Create devbox", "create-devbox"), ("Enable COPR", "enable-copr"), ("Enable cachy", "enable-cachy-kernel")):
            btn = QPushButton(label)
            btn.setToolTip(f"ujust {recipe}")
            def _run(r=recipe):
                try:
                    w = Worker(ujust_command(r))
                    w.start()
                except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                    pass
            btn.clicked.connect(lambda _=False, r=recipe: _run(r))
            row.addWidget(btn)
        row.addStretch()
        layout.addLayout(row)
        hint = QLabel("Buttons run ujust recipes via Worker; tools installed only when you click (podman/brew detection via which).")
        hint.setObjectName("card-copy")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return card
