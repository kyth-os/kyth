import json
import os

# __KYTH_GENERATED_IMPORTS__
from ..services.appstream import load_appstream_catalog
from ..services.runtime import Worker, finish_worker, guard_disposed


class _CatalogMixin:
    def _load_fp_catalog(self):
        if self._fp_catalog_worker and self._fp_catalog_worker.isRunning():
            return
        self._clear_fp_results()
        self._fp_catalog_lines = []
        self._fp_progress.show()
        self._set_fp_task_state("Loading cached Flathub catalog...", "running")
        self._fp_catalog_btn.setEnabled(False)
        self._fp_catalog_worker = Worker([
            "flatpak", "remote-ls", "--cached", "--app",
            "--columns=application,name,description,version,download-size,installed-size",
            "-j", "flathub",
        ])
        self._fp_catalog_worker.line.connect(guard_disposed(self._on_fp_catalog_line))
        self._fp_catalog_worker.done.connect(guard_disposed(self._on_fp_catalog_done))
        self._fp_catalog_worker.start()

    def _on_fp_catalog_line(self, ln: str):
        self._fp_catalog_lines.append(ln)

    def _on_fp_catalog_done(self, code: int):
        self._fp_progress.hide()
        finish_worker(self, attr="_fp_catalog_worker")
        self._fp_catalog_btn.setEnabled(True)
        output = "\n".join(self._fp_catalog_lines).strip()
        entries = []
        # Flatpak --cached -j output may be truncated or split across lines
        # when pipe races; try full JSON first, then line-delimited fallback.
        if output:
            try:
                data = json.loads(output)
                if isinstance(data, list):
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        app_id = (item.get("application_id") or item.get("application") or "").strip()
                        if app_id:
                            item["application_id"] = app_id
                            item["remote"] = "flathub"
                            entries.append(item)
            except (json.JSONDecodeError, TypeError):
                # Try line-delimited JSON objects (one per line) as fallback
                for line in self._fp_catalog_lines:
                    line = line.strip()
                    if not line or line in ("[", "]", ","):
                        continue
                    try:
                        item = json.loads(line.rstrip(","))
                        if isinstance(item, dict):
                            app_id = (item.get("application_id") or item.get("application") or "").strip()
                            if app_id:
                                item["application_id"] = app_id
                                item["remote"] = "flathub"
                                entries.append(item)
                    except (json.JSONDecodeError, TypeError):
                        continue
        if code != 0 or not entries:
            detail = next((line.strip() for line in self._fp_catalog_lines if line.strip()), "")
            self._set_fp_task_state(detail or "Cached Flathub catalog could not be loaded.", "warn")
            return
        self._fp_catalog_entries = entries
        self._render_fp_entries(entries, "Cached Flathub catalog")

    def _render_fp_entries(self, entries: list[dict], title: str, limit: int = 60):
        self._clear_fp_results()
        shown = entries[:limit]
        count_msg = f"{title}: {len(entries)} app{'s' if len(entries) != 1 else ''}"
        if len(entries) > limit:
            count_msg += f" \u2014 showing first {limit}"
        self._set_fp_task_state(count_msg + ".", "idle")
        for entry in shown:
            self._fp_results_layout.addWidget(self._make_fp_result_row(entry))

    def _show_fp_category(self, category_query: str, label: str):
        catalog = self._fp_appstream_catalog()
        tokens = {token.strip().lower() for token in category_query.split() if token.strip()}
        matches = []
        for app_id, details in catalog.items():
            categories = {cat.lower() for cat in details.get("categories", [])}
            if not tokens.intersection(categories):
                continue
            entry = {
                "application_id": app_id,
                "name": details.get("name", app_id),
                "description": details.get("summary", ""),
                "version": details.get("version", ""),
                "remote": "flathub",
            }
            matches.append(entry)
        matches.sort(key=lambda item: (item.get("name") or item.get("application_id") or "").lower())
        self._render_fp_entries(matches, label)

    def _fp_icon_path(self, app_id: str) -> str:
        for size in ("128x128", "64x64"):
            path = f"/var/lib/flatpak/appstream/flathub/x86_64/active/icons/{size}/{app_id}.png"
            if os.path.exists(path):
                return path
        return ""

    def _fp_appstream_catalog(self) -> dict[str, dict]:
        if self._fp_appstream_cache is not None:
            return self._fp_appstream_cache
        self._fp_appstream_cache = load_appstream_catalog()
        return self._fp_appstream_cache

    def _fp_appstream_details(self, app_id: str) -> dict:
        return self._fp_appstream_catalog().get(app_id, {})

    def _refresh_fp_metadata(self):
        if self._fp_refresh_worker and self._fp_refresh_worker.isRunning():
            return
        self._fp_search_lines = []
        self._fp_progress.show()
        self._set_fp_task_state("Refreshing Flathub metadata...", "running")
        self._fp_refresh_btn.setEnabled(False)
        self._fp_refresh_worker = Worker(["flatpak", "update", "--appstream"])
        self._fp_refresh_worker.line.connect(guard_disposed(self._on_fp_search_line))
        self._fp_refresh_worker.done.connect(guard_disposed(self._on_fp_refresh_done))
        self._fp_refresh_worker.start()

    def _on_fp_refresh_done(self, code: int):
        self._fp_progress.hide()
        finish_worker(self, attr="_fp_refresh_worker")
        self._fp_refresh_btn.setEnabled(True)
        self._fp_appstream_cache = None
        self._fp_catalog_entries = []
        if code == 0:
            self._set_fp_task_state("Flathub metadata refreshed.", "success")
        else:
            detail = next((line.strip() for line in self._fp_search_lines if line.strip()), "")
            self._set_fp_task_state(detail or f"Metadata refresh failed (exit {code}). Cached data can still be used.", "warn")
