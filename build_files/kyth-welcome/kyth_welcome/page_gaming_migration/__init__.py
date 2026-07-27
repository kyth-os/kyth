# __KYTH_GENERATED_IMPORTS__
from ._library import _LibraryMixin
from ._saves import _SavesMixin
from ._mods import _ModsMixin
from ._scan import _ScanMixin
from ._win_lib import _WinLibMixin
from .services.runtime import release_worker_when_finished
from ..services.workers.windows_migration import WindowsLibraryWorker
from ..qt import single_shot


class _MigrationMixin(_LibraryMixin, _SavesMixin, _ModsMixin, _ScanMixin, _WinLibMixin):
    def showEvent(self, event):
        super().showEvent(event)
        if not self._dashboard_loaded and "dashboard" not in self._data_workers:
            self._refresh_gaming_dashboard()
        single_shot(self, 80, self._refresh_status)
        if not self._win_lib_probed:
            self._win_lib_probed = True
            worker = WindowsLibraryWorker()
            self._win_lib_worker = worker
            worker.result.connect(self._on_win_lib_result)
            release_worker_when_finished(self, "_win_lib_worker", worker)
            worker.start()
