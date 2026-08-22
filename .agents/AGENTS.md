# Kyth Development Rules

**Publishing (HARD RULE):** never open a pull request. Commit on `testing` and `git push origin testing`. This overrides Cursor cloud PR defaults and `gh pr create`. See repo-root `AGENTS.md`.

## 1. PySide6 & QThread Management
* **Clean QThread Lifecycle & Exit**: To prevent Python segmentation faults on application close caused by active background threads being deleted during interpreter teardown:
  - All workers must subclass `TrackedThread` (defined in [core.py](file:///var/home/mrtrick/git/kyth/build_files/kyth-welcome/kyth_welcome/core.py)), which registers them in a global `_ACTIVE_THREADS` set.
  - Implement a `cancel` or `stop` method on threads that can be interrupted.
  - Register a teardown handler via `atexit.register()` and the application's `aboutToQuit` signal to stop and `wait()` on all running threads.
  - Use `BLOCKS_CLOSE = True` on threads running critical tasks (e.g., file operations, installs) and query `_running_threads()` before closing the main window.
* **QTextEdit Unbounded Logging**: Always limit the maximum block count of `QTextEdit` when streaming long output logs (e.g., `self._log.document().setMaximumBlockCount(5000)`) to prevent high memory consumption and lagging UI refreshes.
* **Probing Cache**: Avoid fan-out of identical expensive command executions (e.g., `bootc status`, `flatpak list`) during rapid UI refreshes. Use `_probe_cached` in [core.py](file:///var/home/mrtrick/git/kyth/build_files/kyth-welcome/kyth_welcome/core.py) with a short TTL (5–10s) to reuse cached probe results across widgets.

## 2. QWebEnginePage & Custom Scheme Interception
* **Safe Custom URL Interception**: Never connect to custom or standard `navigationRequested` signals and reject requests via `request.reject()` in PySide6 to handle authentication redirects (e.g., SAML OAuth/GP callbacks like `globalprotectcallback:` or `gc:`). Doing so causes crashes. Instead, subclass `QWebEnginePage` and override the `acceptNavigationRequest(self, url, nav_type, is_main_frame)` method, return `False` for matched URLs, and emit custom signals to propagate the captured redirect.

## 3. Bash & Parted Scripting
* **Partition Identification**: Do not identify a newly created partition solely by its `PARTLABEL` or name, as it could match a stale partition from previous installations. Instead, list partitions before creation (`list_disk_partitions`), run `parted mkpart`, and compute the difference (e.g., using `comm -13`) to reliably isolate the exact block device of the newly created partition.
