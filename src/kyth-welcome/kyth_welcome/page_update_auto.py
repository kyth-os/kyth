import logging
from datetime import datetime

from kyth_shared.boot_health import read_state as read_boot_health_state
from kyth_shared.update_status import read_update_snapshot

# __KYTH_GENERATED_IMPORTS__
from .core_base import restyle
from .services.dbus_utils import is_systemd_unit_enabled
from .services.launch import popen_privileged, reboot_to_apply
from .services.privileged import AuthFrontend, systemctl_action
from .qt import QCheckBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, Qt
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
        health_row, self._au_health_lbl = _au_row("Boot health:")
        flatpak_row, self._au_flatpak_lbl = _au_row("Flatpak:")
        for row in (last_row, result_row, reason_row, health_row, flatpak_row):
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
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                ts_str = str(ts)
        else:
            ts_str = "Never"
        self._au_last_lbl.setText(ts_str)

        result = status.get("result", "")
        _result_styles = {
            "upgraded": "prop-val-green", "no_change": "card-copy",
            "skipped": "prop-val-orange", "quarantined": "prop-val-red", "error": "prop-val-red",
        }
        self._au_result_lbl.setText(result.replace("_", " ").title() if result else "—")
        self._au_result_lbl.setObjectName(_result_styles.get(result, "card-copy"))
        restyle(self._au_result_lbl)
        self._au_reason_lbl.setText(status.get("reason") or "—")

        health = read_boot_health_state()
        health_text = health.status.replace("_", " ").title()
        if health.failures:
            health_text += f" · {health.failures} failed boot(s)"
        if health.quarantined:
            health_text += f" · {len(health.quarantined)} quarantined"
        if health.last_recovered_digest:
            health_text += f" · recovered from {health.last_recovered_digest[:19]}…"
        self._au_health_lbl.setText(health_text)
        health_style = {
            "healthy": "prop-val-green", "recovered": "prop-val-green", "unhealthy": "prop-val-orange",
            "quarantined": "prop-val-red",
        }.get(health.status, "card-copy")
        self._au_health_lbl.setObjectName(health_style)
        restyle(self._au_health_lbl)

        flatpak_count = status.get("flatpak_updates", 0)
        if flatpak_count > 0:
            noun = "update" if flatpak_count == 1 else "updates"
            self._au_flatpak_lbl.setText(f"{flatpak_count} {noun} pending")
            self._au_flatpak_lbl.setObjectName("prop-val-orange")
        else:
            self._au_flatpak_lbl.setText("Up to date")
            self._au_flatpak_lbl.setObjectName("prop-val-green")
        restyle(self._au_flatpak_lbl)

        # Reflect timer enabled state
        enabled = is_systemd_unit_enabled("kyth-update-watcher.timer")
        self._au_enable_toggle.blockSignals(True)
        self._au_enable_toggle.setChecked(enabled)
        self._au_enable_toggle.blockSignals(False)

    def _toggle_auto_update(self, state: int) -> None:
        # H3: debounce — toggling rapidly would race two pkexec dialogs
        if getattr(self, "_au_toggle_guard", False):
            return
        self._au_toggle_guard = True
        from .qt import single_shot

        single_shot(self, 1200, lambda: setattr(self, "_au_toggle_guard", False))
        cmd = "enable" if state else "disable"
        popen_privileged(systemctl_action(
            cmd,
            "kyth-update-watcher.timer",
            now=True,
            frontend=AuthFrontend.PKEXEC,
        ))

    def _run_auto_update_now(self) -> None:
        if getattr(self, "_au_run_guard", False):
            return
        self._au_run_guard = True
        from .qt import single_shot

        single_shot(self, 2000, lambda: setattr(self, "_au_run_guard", False))
        popen_privileged(systemctl_action(
            "start",
            "kyth-update-watcher.service",
            frontend=AuthFrontend.PKEXEC,
        ))

    def _build_windows_update_style_card(self):
        card, layout = _make_card("card-accent-ok")
        title = QLabel("Active hours & reboot scheduling")
        title.setObjectName("card-title")
        layout.addWidget(title)
        body = QLabel(
            "KythOS stages the new OS image in the background, then waits for you. "
            "Reboot when you are ready — active hours defer automatic staging, and your previous image stays as System Restore for 14 days. "
            "Files in /home are never touched."
        )
        body.setObjectName("card-copy")
        body.setWordWrap(True)
        layout.addWidget(body)
        # Staged vs reboot explainer
        staged_row = QHBoxLayout()
        staged_row.setSpacing(10)
        k = QLabel("Staged update:")
        k.setObjectName("prop-key")
        k.setMinimumWidth(110)
        staged_row.addWidget(k)
        self._wu_staged_lbl = QLabel("Checking…")
        self._wu_staged_lbl.setObjectName("prop-val")
        staged_row.addWidget(self._wu_staged_lbl, 1)
        layout.addLayout(staged_row)
        active_row = QHBoxLayout()
        active_row.setSpacing(8)
        active_row.addWidget(QLabel("Active hours:"))
        self._wu_hours_lbl = QLabel("08:00 – 22:00 (watcher defers staging during active hours when configured via timer override)")
        self._wu_hours_lbl.setObjectName("card-copy")
        active_row.addWidget(self._wu_hours_lbl, 1)
        layout.addLayout(active_row)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        reboot_now = QPushButton("Reboot Now")
        reboot_now.setObjectName("primary")
        reboot_now.setToolTip("Reboot to the staged image now (if one is staged)")
        reboot_now.clicked.connect(lambda _=False: self._reboot_now_click())
        btns.addWidget(reboot_now)
        defer_btn = QPushButton("Defer Automatic Updates 3 Days")
        defer_btn.setToolTip("Stops the watcher timer for 72h — stops the watcher timer via systemctl stop")
        # H3: guard against double-click spawning two pkexec dialogs
        def _defer_click():
            if getattr(self, "_wu_defer_guard", False):
                return
            self._wu_defer_guard = True
            from .qt import single_shot

            single_shot(self, 2000, lambda: setattr(self, "_wu_defer_guard", False))
            popen_privileged(systemctl_action("stop", "kyth-update-watcher.timer", frontend=AuthFrontend.PKEXEC))

        defer_btn.clicked.connect(lambda _=False: _defer_click())
        btns.addWidget(defer_btn)
        enable_btn = QPushButton("Re-enable Updates")

        def _enable_click():
            if getattr(self, "_wu_enable_guard", False):
                return
            self._wu_enable_guard = True
            from .qt import single_shot

            single_shot(self, 2000, lambda: setattr(self, "_wu_enable_guard", False))
            popen_privileged(systemctl_action("enable", "kyth-update-watcher.timer", now=True, frontend=AuthFrontend.PKEXEC))

        enable_btn.clicked.connect(lambda _=False: _enable_click())
        btns.addWidget(enable_btn)
        btns.addStretch()
        layout.addLayout(btns)
        # H7: staged label was never refreshed — sync with bootc state when card is shown
        try:
            from .qt import single_shot as _ss

            _ss(self, 500, self._refresh_wu_staged_label)
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path  # nosec B110 -- best-effort, failure here is non-fatal by design
            pass
        self._add(card)

    def _reboot_now_click(self):
        # H8: the button previously fired systemctl reboot unconditionally —
        # no confirmation, and no check that anything was actually staged.
        # Check staged state at click time (not construction time): this
        # page is composed once and can sit alive for hours before a click,
        # long enough for a background update to stage in the meantime.
        from .services.bootc import has_staged_update

        if not has_staged_update():
            QMessageBox.information(
                self,
                "Nothing Staged",
                "No update is staged right now — rebooting would just restart the current system.",
            )
            return
        reply = QMessageBox.question(
            self,
            "Reboot Now?",
            "This closes all open apps and reboots immediately to apply the staged update.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        reboot_to_apply()

    def _refresh_wu_staged_label(self):
        """H7: keep staged label in sync with canonical bootc state."""
        try:
            from .services.bootc import has_staged_update, bootc_status_data, bootc_image_timestamp, nested_get

            if not has_staged_update():
                self._wu_staged_lbl.setText("None — system is current")
                self._wu_staged_lbl.setObjectName("prop-val-dim")
            else:
                data = bootc_status_data() or {}
                ref = nested_get(data, ("status", "staged", "image", "image")) or ""
                if isinstance(ref, dict):
                    ref = ref.get("image", "") or ref.get("imageref", "") or ""
                label = ref.split("@")[0].split("/")[-1] if isinstance(ref, str) and ref else "Staged"
                ts = bootc_image_timestamp("staged")
                self._wu_staged_lbl.setText(f"{label} — reboot to apply" + (f" · {ts}" if ts else ""))
                self._wu_staged_lbl.setObjectName("prop-val-blue")
            from .core_base import restyle

            restyle(self._wu_staged_lbl)
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            pass
