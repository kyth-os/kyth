"""Windows Takeout wizard — unified migration checklist, _TakeoutMixin."""
from __future__ import annotations

from ..core_base import restyle
from ..services.windows_migration import summarize_takeout, takeout_checklist
from ..qt import QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from ..widgets import _make_card


class _TakeoutMixin:
    def _build_takeout_card(self):
        """Top wizard card driven from already-probed partitions + extras."""
        card, layout = _make_card("card-accent-ok")
        title = QLabel("Windows Takeout — What we found")
        title.setObjectName("card-title")
        layout.addWidget(title)
        intro = QLabel(
            "After you click Scan Drives, this wizard summarizes everything KythOS can bring over — "
            "Steam and other launchers, your user files, browser bookmarks, OneDrive folders, and game saves — "
            "with the next step for each. Nothing is copied until you choose it below."
        )
        intro.setObjectName("card-copy")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self._takeout_status = QLabel("Scan drives above to build your Takeout checklist.")
        self._takeout_status.setObjectName("card-copy")
        self._takeout_status.setWordWrap(True)
        layout.addWidget(self._takeout_status)
        self._takeout_rows = QVBoxLayout()
        self._takeout_rows.setSpacing(6)
        layout.addLayout(self._takeout_rows)
        self._takeout_summary: dict = {}
        btns = QHBoxLayout()
        btns.setSpacing(8)
        to_gaming = QPushButton("Move Steam Games")
        to_gaming.setToolTip("Open Gaming → Migration to copy Steam libraries to a Linux disk")
        to_gaming.clicked.connect(lambda _=False: self._navigate("Gaming"))
        btns.addWidget(to_gaming)
        to_cloud = QPushButton("Set Up Cloud Storage")
        to_cloud.clicked.connect(lambda _=False: self._navigate("Cloud Storage"))
        btns.addWidget(to_cloud)
        btns.addStretch()
        layout.addLayout(btns)
        self._add(card)

    def _clear_takeout_rows(self):
        while self._takeout_rows.count():
            item = self._takeout_rows.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _update_takeout(self, partitions: list[dict] | None = None):
        """Rebuild wizard from latest partition + extras state."""
        if partitions is None:
            # Called after extras scan; reuse last summary base.
            if not self._takeout_summary:
                return
            # Extras already merged via _on_extras if available.
            self._render_takeout()
            return
        summary = summarize_takeout(partitions or [])
        # If extras already scanned, merge saves/wallpapers now.
        extras = getattr(self, "_extras", None)
        if isinstance(extras, list) and extras:
            try:
                from ..services.windows_migration import enrich_with_extras
                summary = enrich_with_extras(summary, extras)
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                pass
        self._takeout_summary = summary
        self._render_takeout()

    def _render_takeout(self):
        summary = self._takeout_summary or {}
        self._clear_takeout_rows()
        if not summary or (not summary.get("profile_count") and not summary.get("steam_count") and not summary.get("launcher_count") and not summary.get("browser_count") and not summary.get("has_onedrive")):
            if summary.get("locked_count"):
                self._takeout_status.setText("Found BitLocker-locked drives — unlock them below, then rescan to build the checklist.")
                self._takeout_status.setObjectName("status-warn")
            elif summary.get("dirty_count"):
                self._takeout_status.setText("Drives are hibernated — boot Windows → full Shut Down → rescan.")
                self._takeout_status.setObjectName("status-warn")
            else:
                self._takeout_status.setText("No Windows user data found on the mounted drives.")
                self._takeout_status.setObjectName("card-copy")
            restyle(self._takeout_status)
            return
        score = summary.get("score", 0)
        self._takeout_status.setText(f"Readiness {score}/5 · {summary.get('steam_count',0)} Steam · {summary.get('launcher_count',0)} other launchers · {summary.get('profile_count',0)} profiles · {summary.get('browser_count',0)} browsers" + (" · OneDrive found" if summary.get("has_onedrive") else ""))
        self._takeout_status.setObjectName("status-ok" if score >= 3 else "status-warn")
        restyle(self._takeout_status)
        for row in takeout_checklist(summary):
            self._takeout_rows.addWidget(self._make_migration_row(row["status"], row["title"], row["detail"]))
            # Per-launcher reinstall hints as sub-rows
            if row["title"] == "Other launchers":
                for item in summary.get("launcher_items") or []:
                    self._takeout_rows.addWidget(self._make_migration_row("dim", item["display"], f"{item['path']} → {item['hint']}"))
