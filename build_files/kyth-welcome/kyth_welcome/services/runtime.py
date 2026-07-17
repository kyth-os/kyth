"""Qt worker threads shared by System Hub pages and service workers.

Domain services should not own thread base classes — import them from here.
"""
from __future__ import annotations

import atexit
import os
import signal
import subprocess
import time

from ..qt import QThread, Signal
from .process import _get_rx_bytes, _invalidate_probe_caches

_ACTIVE_THREADS: set = set()


class TrackedThread(QThread):
    """QThread that stays registered (and referenced) while alive.

    Every worker in the app must subclass this: the registry both prevents a
    fire-and-forget thread from being garbage-collected mid-run and lets window
    close / app quit wait for stragglers instead of letting Python destroy a
    running QThread, which aborts the whole process.

    Subclasses that run user tasks (installs, copies, updates) set BLOCKS_CLOSE
    so the main window refuses to close mid-task; probes leave it False and are
    joined at quit by _shutdown_threads.
    """

    BLOCKS_CLOSE = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _ACTIVE_THREADS.add(self)
        self.finished.connect(lambda: _ACTIVE_THREADS.discard(self))


def _running_threads() -> list[TrackedThread]:
    return [t for t in _ACTIVE_THREADS if t.isRunning()]


def _shutdown_threads(timeout_ms: int = 15000) -> None:
    """Cancel and join every tracked thread. Connected to aboutToQuit so the
    interpreter never tears down a still-running QThread."""
    for t in list(_ACTIVE_THREADS):
        stop = getattr(t, "cancel", None) or getattr(t, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                pass
    deadline = time.monotonic() + timeout_ms / 1000
    for t in list(_ACTIVE_THREADS):
        remaining_ms = max(100, int((deadline - time.monotonic()) * 1000))
        t.wait(remaining_ms)


# aboutToQuit only fires when an event loop exits, so also join at interpreter
# exit — atexit runs before module teardown destroys the QThread wrappers.
# Covers embedders (tests, screenshot driver) that never call app.exec().
atexit.register(_shutdown_threads)


class Worker(TrackedThread):
    BLOCKS_CLOSE = True
    CANCELLED = 130

    line = Signal(str)
    done = Signal(int)

    def __init__(self, cmd: list[str]):
        super().__init__()
        self._cmd = cmd
        self._proc: subprocess.Popen[str] | None = None
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except Exception:
            try:
                proc.terminate()
            except Exception:
                return

    def run(self):
        try:
            env = os.environ.copy()
            # When running without a TTY, sudo needs a graphical askpass helper.
            # ksshaskpass (KDE) shows a GUI password dialog and writes it to stdout.
            env.setdefault("SUDO_ASKPASS", "/usr/bin/ksshaskpass")
            # Force English locale for all subprocesses so flatpak CLI output
            # (app names in remote-ls, search, list) is always en_US, not whatever
            # the process inherited.
            env["LANG"] = "en_US.UTF-8"
            env["LC_ALL"] = "en_US.UTF-8"
            proc = subprocess.Popen(
                self._cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                bufsize=1,
                env=env,
                cwd="/tmp",
                start_new_session=True,
            )
            self._proc = proc
            for ln in proc.stdout:
                self.line.emit(ln.rstrip())
            proc.wait()
            if self._cancel_requested:
                self.done.emit(self.CANCELLED)
            else:
                self.done.emit(proc.returncode)
        except Exception as exc:
            self.line.emit(f"Error: {exc}")
            self.done.emit(1)
        finally:
            self._proc = None
            # The command may have installed apps or staged a deployment.
            _invalidate_probe_caches()
            # Targeted disk-section drops for common mutation commands.
            try:
                cmd0 = " ".join(self._cmd[:4])
                from .probe import (
                    invalidate_after_bootc_change,
                    invalidate_after_flatpak_change,
                )
                if "flatpak" in cmd0:
                    invalidate_after_flatpak_change()
                if "bootc" in cmd0:
                    invalidate_after_bootc_change()
            except Exception:
                pass


class DownloadMonitor(TrackedThread):
    """Polls /proc/net/dev every second to track download speed and progress."""
    # downloaded, total, speed_bps, eta_sec  (object keeps Python int — avoids 32-bit overflow)
    stats = Signal(object, object, object, object)

    def __init__(self, total_bytes: int, rx_start: int):
        super().__init__()
        self._total = total_bytes
        self._rx_start = rx_start
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        rx_prev = 0
        t_prev = time.monotonic()
        speed_samples: list[float] = []

        while not self._stop:
            time.sleep(1)
            rx_now = _get_rx_bytes()
            t_now = time.monotonic()
            downloaded = min(self._total, max(0, rx_now - self._rx_start))

            dt = t_now - t_prev
            if dt > 0 and rx_prev > 0:
                speed_samples.append((rx_now - rx_prev) / dt)
                if len(speed_samples) > 5:
                    speed_samples.pop(0)
            rx_prev = rx_now
            t_prev = t_now

            avg_speed = int(sum(speed_samples) / len(speed_samples)) if speed_samples else 0
            remaining = max(0, self._total - downloaded)
            eta_sec = int(remaining / avg_speed) if avg_speed > 0 else 0
            self.stats.emit(downloaded, self._total, avg_speed, eta_sec)


class DataWorker(TrackedThread):
    result = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, key: str, fn):
        super().__init__()
        self._key = key
        self._fn = fn

    def run(self):
        try:
            self.result.emit(self._key, self._fn())
        except Exception as exc:
            self.failed.emit(self._key, str(exc))


def _finish_worker(owner: object, attr: str = "_worker") -> None:
    worker = getattr(owner, attr, None)
    if worker is None:
        return
    worker.wait()
    worker.deleteLater()
    setattr(owner, attr, None)


def _release_worker_when_finished(owner: object, attr: str, worker: QThread) -> None:
    def _release() -> None:
        if getattr(owner, attr, None) is worker:
            setattr(owner, attr, None)
        worker.deleteLater()

    worker.finished.connect(_release)
