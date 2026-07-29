# __KYTH_GENERATED_IMPORTS__
from ..services.runtime import release_worker_when_finished
from ..services.gaming import DataWorker
from ..services.hardware import HardwareProbe
from ..services.plasma import _collect_wayland_probes
from ..widgets import HardwareCard


class _RefreshMixin:
    def refresh(self):
        if self._worker is not None and self._worker.isRunning():
            return
        self._refresh_btn.setEnabled(False)
        self._refresh_actions.status.set_state("running", "Checking Plasma and Wayland readiness...")
        self._clear_probe_rows()
        self._worker = DataWorker("plasma-wayland", _collect_wayland_probes)
        self._worker.result.connect(self._on_refresh_done)
        self._worker.failed.connect(self._on_refresh_failed)
        release_worker_when_finished(self, "_worker", self._worker)
        self._worker.start()

    def _on_refresh_done(self, _key: str, probes: list[HardwareProbe]):
        self._refresh_btn.setEnabled(True)
        for probe in probes:
            self._probe_rows.addWidget(HardwareCard(probe))
        states = {probe.status for probe in probes}
        if "err" in states:
            self._refresh_actions.status.set_state("err", "Session checks found issues.")
        elif "warn" in states:
            self._refresh_actions.status.set_state("warn", "Some Wayland pieces may need attention.")
        else:
            self._refresh_actions.status.set_state("ok", "Plasma and Wayland checks look ready.")

    def _on_refresh_failed(self, _key: str, message: str):
        self._refresh_btn.setEnabled(True)
        self._refresh_actions.status.set_state("err", f"Could not check session: {message}")

    def _clear_probe_rows(self):
        while self._probe_rows.count():
            item = self._probe_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
