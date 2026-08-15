import subprocess

# __KYTH_GENERATED_IMPORTS__
from .core_base import restyle
from .services.launch import popen
from .qt import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, Qt, QScrollArea, QWidget,
)
from .widgets import (
    Page, _make_card,
)


# ── Page: Just (veteran) ──────────────────────────────────────────────────────
class JustPage(Page):
    def __init__(self):
        super().__init__()
        self._page_header(
            "Advanced",
            "Just Recipes",
            "Veteran tasks — same as `just --list` in terminal, no terminal needed.",
        )

        card, layout = _make_card()
        layout.setSpacing(8)

        desc = QLabel("Run any Just recipe from the Hub. Calls `just <name>` under the hood.")
        desc.setWordWrap(True)
        desc.setObjectName("card-copy")
        layout.addWidget(desc)

        self._list_layout = QVBoxLayout()
        self._list_layout.setSpacing(6)
        layout.addLayout(self._list_layout)

        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setObjectName("mono-inline")
        layout.addWidget(self._status)

        self._add(card)
        self._refresh()

    def _refresh(self):
        # Clear
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        try:
            result = subprocess.run(
                ["just", "--list"], capture_output=True, text=True, timeout=5
            )
            text = result.stdout.strip() or result.stderr.strip()
        except Exception as e:
            text = f"just --list failed: {e}"
        if not text:
            text = "No just recipes found."
        # Parse `just --list` output: lines like `    build    # Build the full KythOS image.`
        lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("Available recipes:")]
        for ln in lines[:30]:
            parts = ln.split(None, 1)
            name = parts[0] if parts else ln
            comment = parts[1] if len(parts) > 1 else ""
            row = QHBoxLayout()
            btn = QPushButton(name)
            btn.setFixedWidth(220)
            btn.clicked.connect(lambda _, n=name: self._run_recipe(n))
            row.addWidget(btn)
            lbl = QLabel(comment[:80])
            lbl.setWordWrap(True)
            lbl.setObjectName("card-copy")
            row.addWidget(lbl, 1)
            container = QWidget()
            container.setLayout(row)
            self._list_layout.addWidget(container)
        if len(lines) > 30:
            more = QLabel(f"… and {len(lines)-30} more (run `just --list` in terminal)")
            more.setObjectName("card-copy")
            self._list_layout.addWidget(more)
        self._status.setText(f"Found {len(lines)} recipes")

    def _run_recipe(self, name: str):
        self._status.setText(f"Running `just {name}`…")
        try:
            popen(["just", name])
            self._status.setText(f"Launched `just {name}`")
        except Exception as e:
            self._status.setText(f"Failed to launch `just {name}`: {e}")
