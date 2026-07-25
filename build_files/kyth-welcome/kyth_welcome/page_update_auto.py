import logging
from datetime import datetime

from kyth_shared.update_status import read_update_snapshot

# __KYTH_GENERATED_IMPORTS__
from .services.dbus_utils import is_systemd_unit_enabled
from .services.launch import popen_privileged
from .services.privileged import AuthFrontend, systemctl_action
from .qt import QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, Qt
from .widgets import _make_card

_logger = logging.getLogger(__name__)


class _AutoUpdateMixin:
    """The automatic-update schedule status card: last-check state and the
    kyth-update-watcher.timer enable toggle."""

    def _build_auto_update_card(self):
        auto_card, auto_layout = _make_card()
        auto_title = QLabel("Automatic updates")
        auto_title.setObjectName("card-title")
        auto_layout.addWidget(auto_title)
        auto_status_row = QHBoxLayout()
        auto_status_row.setSpacing(24)

        auto_state_col = QVBoxLayout()
        auto_state_col.setSpacing(8)

        def _au_row(label: str) -> tuple[QHBoxLayout, QLabel]:
            row = QHBoxLayout()
            row.setSpacing(8)
            k = QLabel(label)
            k.setObjectName("prop-key")
            k.setMinimumWidth(96)
            row.addWidget(k)
            v = QLabel("—")
            v.setObjectName("prop-val")
            row.addWidget(v, 1)
            return row, v

        last_row, self._au_last_lbl      = _au_row("Last check:")
        result_row, self._au_result_lbl  = _au_row("Result:")
        reason_row, self._au_reason_lbl  = _au_row("Reason:")
        flatpak_row, self._au_flatpak_lbl = _au_row("Flatpak:")
        for row in (last_row, result_row, reason_row, flatpak_row):
            auto_state_col.addLayout(row)
        auto_status_row.addLayout(auto_state_col, 1)

        auto_ctrl_col = QVBoxLayout()
        auto_ctrl_col.setSpacing(8)
        auto_ctrl_col.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._au_enable_toggle = QCheckBox("Enabled")
        self._au_enable_toggle.setObjectName("card-copy")
        self._au_enable_toggle.stateChanged.connect(self._toggle_auto_update)
        auto_ctrl_col.addWidget(self._au_enable_toggle)
        au_trigger_btn = QPushButton("Check Now")
        au_trigger_btn.setToolTip("Manually trigger the update watcher (requires authentication)")
        au_trigger_btn.clicked.connect(self._run_auto_update_now)
        auto_ctrl_col.addWidget(au_trigger_btn)
        auto_status_row.addLayout(auto_ctrl_col)

        auto_layout.addLayout(auto_status_row)
        self._add(auto_card)

    def _refresh_auto_update_status(self) -> None:
        snapshot = read_update_snapshot()
        if snapshot is None:
            _logger.debug("_refresh_auto_update_status: watcher status is unavailable")
            status = {}
        else:
            status = snapshot.to_dict()

        ts = status.get("ts", 0)
        if ts:
            try:
                ts_str = datetime.fromtimestamp(ts).strftime("%b %d %H:%M")
            except Exception:
                ts_str = str(ts)
        else:
            ts_str = "Never"
        self._au_last_lbl.setText(ts_str)

        result = status.get("result", "")
        _colors = {"upgraded": "#4caf50", "no_change": "#b0bccf", "skipped": "#ffa726", "error": "#ef5350"}
        self._au_result_lbl.setText(result.replace("_", " ").title() if result else "—")
        self._au_result_lbl.setStyleSheet(f"color: {_colors.get(result, '#b0bccf')};")
        self._au_reason_lbl.setText(status.get("reason") or "—")

        flatpak_count = status.get("flatpak_updates", 0)
        if flatpak_count > 0:
            noun = "update" if flatpak_count == 1 else "updates"
            self._au_flatpak_lbl.setText(f"{flatpak_count} {noun} pending")
            self._au_flatpak_lbl.setStyleSheet("color: #ffa726;")
        else:
            self._au_flatpak_lbl.setText("Up to date")
            self._au_flatpak_lbl.setStyleSheet("color: #4caf50;")

        # Reflect timer enabled state
        enabled = is_systemd_unit_enabled("kyth-update-watcher.timer")
        self._au_enable_toggle.blockSignals(True)
        self._au_enable_toggle.setChecked(enabled)
        self._au_enable_toggle.blockSignals(False)

    def _toggle_auto_update(self, state: int) -> None:
        cmd = "enable" if state else "disable"
        popen_privileged(systemctl_action(
            cmd,
            "kyth-update-watcher.timer",
            now=True,
            frontend=AuthFrontend.PKEXEC,
        ))

    def _run_auto_update_now(self) -> None:
        popen_privileged(systemctl_action(
            "start",
            "kyth-update-watcher.service",
            frontend=AuthFrontend.PKEXEC,
        ))
