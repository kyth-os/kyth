import json
import os
import pathlib
import time

# __KYTH_GENERATED_IMPORTS__
from ..services.runtime import Worker, finish_worker, guard_disposed

_FLATHUB_CACHE = os.path.expanduser("~/.cache/kyth/flathub-search.json")
_FLATHUB_TTL = 3600


class _SearchMixin:
    def _load_flathub_cache(self, query: str) -> list[dict] | None:
        try:
            if not os.path.exists(_FLATHUB_CACHE):
                return None
            if time.time() - os.path.getmtime(_FLATHUB_CACHE) > _FLATHUB_TTL:
                return None
            data = json.loads(pathlib.Path(_FLATHUB_CACHE).read_text())
            # Simple: if cache has query substring, return it; else None
            # Real cache stores last results per query; for offline we return last search
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
        return None

    def _save_flathub_cache(self, results: list[dict]) -> None:
        try:
            pathlib.Path(_FLATHUB_CACHE).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(_FLATHUB_CACHE).write_text(json.dumps(results[:20]))
        except Exception:
            pass

    def _run_fp_search(self):
        if self._fp_search_worker and self._fp_search_worker.isRunning():
            return
        query = self._fp_search_box.text().strip()
        if not query:
            return
        self._fp_search_query = query
        self._clear_fp_results()
        self._fp_search_lines = []
        self._fp_progress.show()
        self._set_fp_task_state(f"Searching Flathub for \u201c{query}\u201d\u2026", "running")
        self._fp_search_btn.setEnabled(False)
        self._fp_search_worker = Worker(
            ["flatpak", "search", "-j", query]
        )
        self._fp_search_worker.line.connect(guard_disposed(self._on_fp_search_line))
        self._fp_search_worker.done.connect(guard_disposed(self._on_fp_search_done))
        self._fp_search_worker.start()

    def _on_fp_search_line(self, ln: str):
        self._fp_search_lines.append(ln)

    def _on_fp_search_done(self, code: int):
        self._fp_progress.hide()
        finish_worker(self, attr="_fp_search_worker")
        self._fp_search_btn.setEnabled(True)
        self._clear_fp_results()
        output = "\n".join(self._fp_search_lines).strip()
        results = []
        if output.startswith("["):
            try:
                for item in json.loads(output):
                    app_id = (item.get("application_id") or item.get("application") or "").strip()
                    if app_id:
                        results.append({
                            "application_id": app_id,
                            "name": (item.get("name") or app_id).strip(),
                            "description": (item.get("description") or "").strip(),
                            "version": (item.get("version") or "").strip(),
                            "remote": (item.get("remotes") or item.get("remote") or "flathub").strip(),
                        })
            except (json.JSONDecodeError, TypeError):
                results = []
        if results and code == 0:
            self._save_flathub_cache(results)
        else:
            # Offline fallback: if flatpak search failed and cache exists, show cached
            if code != 0 and not results:
                cached = self._load_flathub_cache(getattr(self, "_fp_search_query", ""))
                if cached:
                    results = cached
                    self._set_fp_task_state("Offline — showing cached results from last search", "offline")
            for line in self._fp_search_lines:
                parts = line.split("\t")
                if len(parts) >= 2:
                    app_id = parts[0].strip()
                    name = parts[1].strip()
                    summary = parts[2].strip() if len(parts) >= 3 else ""
                    if app_id:
                        results.append({
                            "application_id": app_id,
                            "name": name or app_id,
                            "description": summary,
                            "version": "",
                            "remote": "flathub",
                        })
        if not results:
            detail = next((line.strip() for line in self._fp_search_lines if line.strip()), "")
            if code == 0:
                msg = "No results found."
            elif detail:
                msg = f"Search failed \u2014 {detail}"
            else:
                msg = "Search failed \u2014 check that Flatpak and Flathub are available."
            self._set_fp_task_state(msg, "idle" if code == 0 else "warn")
            return
        shown = results[:30]
        count_msg = f"{len(results)} result{'s' if len(results) != 1 else ''} found"
        if len(results) > 30:
            count_msg += " \u2014 showing top 30"
        self._set_fp_task_state(count_msg + ".", "idle")
        for entry in shown:
            self._fp_results_layout.addWidget(self._make_fp_result_row(entry))

    def _clear_fp_results(self):
        def clear_layout(layout):
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                child_layout = item.layout()
                if widget:
                    widget.deleteLater()
                elif child_layout:
                    clear_layout(child_layout)
        while self._fp_results_layout.count():
            item = self._fp_results_layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget:
                widget.deleteLater()
            elif child_layout:
                clear_layout(child_layout)
