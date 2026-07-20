"""Composable, mostly-static cards for the Repair page."""

from __future__ import annotations

from collections.abc import Callable

from .core_base import _bootc_image_timestamp
from .qt import QHBoxLayout, QLabel, QPushButton
from .widgets import _make_card, _make_flow_step


def repair_overview_cards(navigate: Callable[[str], None]) -> list[object]:
    info, info_layout = _make_card()
    title = QLabel("What repair changes and what it preserves")
    title.setObjectName("card-title")
    info_layout.addWidget(title)
    body = QLabel(
        "Repair resets layered packages, system configuration, and the OS image to KythOS defaults. "
        "It does not replace a proper backup. Files in /home are left in place, so this is "
        "a safe way to recover a broken OS — but keep your saves, projects, and documents "
        "backed up somewhere external."
    )
    body.setObjectName("card-copy")
    body.setWordWrap(True)
    info_layout.addWidget(body)

    order, order_layout = _make_card("card-accent-ok")
    order_title = QLabel("Best repair order")
    order_title.setObjectName("card-title")
    order_layout.addWidget(order_title)
    steps = (
        ("Quick fixes", "Refresh menus, repair Flatpaks, restart audio or Bluetooth, and collect a snapshot first."),
        ("Roll back", "If trouble started after an update, stage the previous image before changing anything else."),
        ("Repair install", "Use the destructive OS reset only after quick fixes and rollback do not match the problem."),
    )
    for index, (step_title, copy) in enumerate(steps, 1):
        order_layout.addWidget(_make_flow_step(index, step_title, copy))

    immutable, immutable_layout = _make_card("card-accent-ok")
    immutable_title = QLabel("Why system files are read-only")
    immutable_title.setObjectName("card-title")
    immutable_layout.addWidget(immutable_title)
    immutable_body = QLabel(
        "KythOS protects the base OS like a game console image: /usr is read-only while "
        "you are using the system, and OS changes arrive as a new bootable deployment. "
        "That is why updates can be rolled back cleanly. Install apps with Flatpak, use "
        "Distrobox for development tools, keep personal files in /home, and let KythOS "
        "updates replace the base system instead of editing it by hand."
    )
    immutable_body.setObjectName("card-copy")
    immutable_body.setWordWrap(True)
    immutable_layout.addWidget(immutable_body)
    buttons = QHBoxLayout()
    buttons.setSpacing(8)
    for label, target in (("Open Update Page", "Update"), ("Open App Store", "App Store")):
        button = QPushButton(label)
        button.clicked.connect(lambda _=False, key=target: navigate(key))
        buttons.addWidget(button)
    buttons.addStretch()
    immutable_layout.addLayout(buttons)
    return [info, order, immutable]


def rollback_card(
    has_rollback: bool,
    run_rollback: Callable[[], None],
    navigate: Callable[[str], None],
) -> tuple[object, QPushButton]:
    card, layout = _make_card("card-accent-warn" if has_rollback else None)
    title = QLabel("Undo last update")
    title.setObjectName("card-title")
    layout.addWidget(title)
    timestamp = _bootc_image_timestamp("rollback")
    body = QLabel(
        (
            "A previous system image is available. Rollback restores that image on the next boot; "
            "your files, saves, and projects in /home stay in place."
            + (f"\n\nPrevious image built: {timestamp}" if timestamp else "")
        ) if has_rollback else (
            "No previous system image is available right now. After the next OS update, "
            "KythOS will keep a rollback target here so you can undo a bad update."
        )
    )
    body.setObjectName("card-copy")
    body.setWordWrap(True)
    layout.addWidget(body)
    buttons = QHBoxLayout()
    buttons.setSpacing(8)
    rollback_button = QPushButton("Rollback and Reboot")
    rollback_button.setObjectName("primary")
    rollback_button.setEnabled(has_rollback)
    rollback_button.clicked.connect(run_rollback)
    buttons.addWidget(rollback_button)
    update_button = QPushButton("Open Update Page")
    update_button.clicked.connect(lambda _=False: navigate("Update"))
    buttons.addWidget(update_button)
    buttons.addStretch()
    layout.addLayout(buttons)
    return card, rollback_button
