"""Composable, mostly-static cards for the Repair page."""

from __future__ import annotations

from collections.abc import Callable

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


def system_restore_history_card(
    history: list[dict] | None,
    run_rollback: Callable[[], None],
    navigate: Callable[[str], None],
) -> object:
    """Windows-style System Restore timeline card. Pure layout — caller fetches history off-thread."""
    accent = "card-accent-ok" if history and any(h.get("available") for h in history) else None
    card, layout = _make_card(accent)
    title = QLabel("System Restore — deployment history")
    title.setObjectName("card-title")
    layout.addWidget(title)
    intro = QLabel(
        "Windows-style restore points: KythOS keeps the current image, any staged update, and the previous image. "
        "If an update causes trouble, roll back with one click — like File History for the OS. Files in /home are never touched."
    )
    intro.setObjectName("card-copy")
    intro.setWordWrap(True)
    layout.addWidget(intro)
    if not history:
        body = QLabel("Checking deployment history…")
        body.setObjectName("card-copy")
        layout.addWidget(body)
    else:
        for h in history:
            label = h.get("label", h.get("section", ""))
            if not h.get("available"):
                row_text = f"{label}: — no image (will appear after the next update)"
                status = "dim"
            else:
                ts = h.get("timestamp") or "unknown time"
                ref = h.get("reference") or h.get("branch") or "KythOS image"
                short = h.get("short_digest") or ""
                row_text = f"{label}: {ref} · {ts}" + (f" · {short}" if short else "")
                status = "ok" if h.get("section") == "booted" else ("warn" if h.get("section") == "staged" else "ok")
            row = QLabel(row_text)
            row.setObjectName("card-copy" if status != "dim" else "card-copy")
            row.setWordWrap(True)
            layout.addWidget(row)
    buttons = QHBoxLayout()
    buttons.setSpacing(8)
    rollback_btn = QPushButton("Restore Previous Image and Reboot")
    rollback_btn.setObjectName("primary")
    has_prev = bool(history and any(h.get("section") == "rollback" and h.get("available") for h in history))
    rollback_btn.setEnabled(has_prev)
    rollback_btn.clicked.connect(run_rollback)
    buttons.addWidget(rollback_btn)
    buttons.addWidget(QPushButton("Open Update Page"))
    # second button wired via closure in caller — placeholder here, caller replaces
    buttons.itemAt(1).widget().clicked.connect(lambda _=False: navigate("Update"))
    buttons.addStretch()
    layout.addLayout(buttons)
    return card


def guardian_timeline_card(
    history: list[dict] | None,
    on_feedback: Callable[[str, bool], None],
) -> object:
    """Guardian 30-day timeline: last 5 auto-fixes with redacted evidence and Yes/No."""
    from kyth_shared.guardian import RECIPES
    import time

    card, layout = _make_card("card-accent-ok" if history else None)
    title = QLabel("Guardian — self-heal history (30 days)")
    title.setObjectName("card-title")
    layout.addWidget(title)
    intro = QLabel(
        "Offline, explainable auto-repairs. Guardian never deletes files and only runs safe recipes "
        "after two failures + cooldown; gaming/thermal/update watcher suppress it."
    )
    intro.setObjectName("card-copy")
    intro.setWordWrap(True)
    layout.addWidget(intro)
    if not history:
        body = QLabel("No recent auto-repairs — system is healthy.")
        body.setObjectName("card-copy")
        layout.addWidget(body)
        return card
    # Last 5, newest first
    for item in list(history)[-5:][::-1]:
        rid = item.get("recipe_id") or (item.get("chain", [None])[0] if item.get("chain") else "unknown")
        rec = RECIPES.get(rid, None)
        rtitle = rec.title if rec else rid
        ts = item.get("timestamp", 0)
        try:
            age = time.time() - float(ts)
            if age < 3600:
                when = f"{int(age//60)}m ago"
            elif age < 86400:
                when = f"{int(age//3600)}h ago"
            else:
                when = f"{int(age//86400)}d ago"
        except (ValueError, TypeError):
            when = "recently"
        verified = item.get("verified")
        vtxt = "✓ verified" if verified else ("✗ not verified" if verified is False else "")
        row = QLabel(f"{when} — {rtitle} ({item.get('action','')}) {vtxt}")
        row.setObjectName("card-copy")
        row.setWordWrap(True)
        layout.addWidget(row)
        detail = (item.get("detail") or item.get("explanation") or "")[:200]
        if detail:
            d = QLabel(detail)
            d.setObjectName("caption-text")
            d.setWordWrap(True)
            layout.addWidget(d)
        # Feedback row per item
        fb_row = QHBoxLayout()
        fb_row.setSpacing(6)
        fb_lbl = QLabel("Did this help?")
        fb_lbl.setObjectName("caption-text")
        fb_row.addWidget(fb_lbl)
        for label, helpful in (("Yes", True), ("No", False)):
            btn = QPushButton(label)
            btn.setToolTip("Teach Guardian for next time (local only)")
            btn.clicked.connect(lambda _=False, rid=rid, helpful=helpful: on_feedback(rid, helpful))
            fb_row.addWidget(btn)
        fb_row.addStretch()
        layout.addLayout(fb_row)
    return card


def rollback_card(
    has_rollback: bool,
    run_rollback: Callable[[], None],
    navigate: Callable[[str], None],
    timestamp: str | None = None,
    warn: bool = False,
) -> tuple[object, QPushButton]:
    """timestamp: pre-fetched bootc_image_timestamp("rollback"), or None.
    Fetching it is a subprocess call — callers building this eagerly (e.g.
    a page constructor) should pass None and refresh it in asynchronously,
    the same way has_rollback itself should be treated as a placeholder
    until a background probe confirms it. warn: self-healing signal."""
    accent = "card-accent-warn" if (has_rollback or warn) else None
    card, layout = _make_card(accent)
    title = QLabel("Undo last update")
    title.setObjectName("card-title")
    layout.addWidget(title)
    if warn and has_rollback:
        body_text = (
            "⚠ Staged update appears to have failed twice — self-healing recommends rolling back. "
            "Rollback restores the previous image on next boot; your files in /home stay in place."
            + (f"\n\nPrevious image built: {timestamp}" if timestamp else "")
        )
    elif has_rollback:
        body_text = (
            "A previous system image is available. Rollback restores that image on the next boot; "
            "your files, saves, and projects in /home stay in place."
            + (f"\n\nPrevious image built: {timestamp}" if timestamp else "")
        )
    else:
        body_text = "No previous system image is available right now. After the next OS update, KythOS will keep a rollback target here so you can undo a bad update."
    body = QLabel(body_text)
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
