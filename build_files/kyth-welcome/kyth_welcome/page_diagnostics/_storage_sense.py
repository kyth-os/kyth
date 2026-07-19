# __KYTH_GENERATED_IMPORTS__
from ..core_base import _restyle
from ..services.diagnostics import (
    storage_sense_enabled as _storage_sense_enabled,
    storage_sense_run_now,
    storage_sense_set,
)
from ..qt import QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from ..widgets import _make_card


class _StorageSenseMixin:
    def _make_storage_sense_card(self) -> QFrame:
        from ..qt import QFrame
        card, layout = _make_card()
        title = QLabel("Storage Sense \u2014 automatic cleanup")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "Once a week: empties Recycle Bin items older than 30 days, removes "
            "unused Flatpak runtimes, and trims old logs. Your files are never "
            "touched \u2014 only things already thrown away or no longer used."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self._storage_sense_btn = QPushButton()
        self._storage_sense_btn.clicked.connect(self._toggle_storage_sense)
        btns.addWidget(self._storage_sense_btn)
        run_now_btn = QPushButton("Clean Up Now")
        run_now_btn.setToolTip("Runs one cleanup pass immediately.")
        run_now_btn.clicked.connect(self._run_storage_sense_now)
        btns.addWidget(run_now_btn)
        btns.addStretch()
        layout.addLayout(btns)

        self._storage_sense_status = QLabel("")
        self._storage_sense_status.setObjectName("card-copy")
        self._storage_sense_status.setWordWrap(True)
        self._storage_sense_status.hide()
        layout.addWidget(self._storage_sense_status)
        self._refresh_storage_sense_btn()
        return card

    def _refresh_storage_sense_btn(self):
        if _storage_sense_enabled():
            self._storage_sense_btn.setText("Turn Off Storage Sense")
            self._storage_sense_btn.setObjectName("")
        else:
            self._storage_sense_btn.setText("Turn On Storage Sense")
            self._storage_sense_btn.setObjectName("primary")
        _restyle(self._storage_sense_btn)

    def _toggle_storage_sense(self):
        enable = not _storage_sense_enabled()
        ok, detail = storage_sense_set(enable)
        if ok:
            self._storage_sense_status.setText(
                "\u2713 Storage Sense is on \u2014 cleanup runs weekly in the background."
                if enable else "Storage Sense is off."
            )
        else:
            action = "enable" if enable else "disable"
            self._storage_sense_status.setText(
                f"\u2717 Could not {action} the cleanup timer: {detail or 'unknown error'}. "
                "If you updated recently, restart once so the new timer is available."
            )
        self._storage_sense_status.show()
        self._refresh_storage_sense_btn()

    def _run_storage_sense_now(self):
        ok, detail = storage_sense_run_now()
        if ok:
            self._storage_sense_status.setText("\u2713 Cleanup started in the background.")
        else:
            self._storage_sense_status.setText(f"\u2717 {detail}")
        self._storage_sense_status.show()
