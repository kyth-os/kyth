import atexit
import glob
import hashlib
import os
import json
import re
import signal
import shlex
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

# __KYTH_GENERATED_IMPORTS__
from .qt import (  # noqa: E501
    QLabel, QPushButton, QTextEdit, QThread, QWidget, Signal,
)

# ── Constants ──────────────────────────────────────────────────────────────────
REGISTRY = "ghcr.io/mrtrick37/kyth"
_CLOUD_SYNC_CONFIG = os.path.expanduser("~/.config/kyth-cloud-sync.json")
_SYNC_INTERVAL_MS = 5 * 60 * 1000  # 5 minutes
_WIZARD_SENTINEL = os.path.expanduser("~/.config/kyth-welcome-done")
_SMB_CONFIG = os.path.expanduser("~/.config/kyth-smb-shares.json")
_SMB_CREDS_DIR = "/etc/kyth-smb-creds"
_PROTONDB_CACHE_PATH = os.path.expanduser("~/.cache/kyth-protondb.json")
_PROTONDB_TIER_STYLE: dict[str, tuple[str, str]] = {
    "platinum": ("#102010", "#7ee8a2"),
    "gold":     ("#2b2410", "#d4a843"),
    "silver":   ("#181e2b", "#8cadcf"),
    "bronze":   ("#2b1a10", "#c47c4a"),
    "borked":   ("#3a1010", "#f48771"),
    "pending":  ("#252526", "#858585"),
}


def _is_live_session() -> bool:
    try:
        with open("/proc/cmdline") as _f:
            return "kyth.live" in _f.read()
    except OSError:
        return False


_IS_LIVE = _is_live_session()


def _prefer_xwayland_if_wayland_plugin_missing() -> None:
    # KDE Wayland sessions usually expose both WAYLAND_DISPLAY and DISPLAY.
    # If qt6-qtwayland is missing in the image, Qt aborts before showing any
    # window; falling back to xcb lets the helper still open via XWayland.
    if os.environ.get("QT_QPA_PLATFORM"):
        return
    if not os.environ.get("WAYLAND_DISPLAY") or not os.environ.get("DISPLAY"):
        return

    # Use filesystem scan so this runs safely before QApplication is created
    # (QLibraryInfo.path() can initialize Qt internals that produce ghost windows).
    _QT6_PLATFORM_DIRS = [
        "/usr/lib64/qt6/plugins/platforms",
        "/usr/lib/qt6/plugins/platforms",
        "/usr/lib/x86_64-linux-gnu/qt6/plugins/platforms",
        "/usr/lib/aarch64-linux-gnu/qt6/plugins/platforms",
    ]
    for platform_dir in _QT6_PLATFORM_DIRS:
        if not os.path.isdir(platform_dir):
            continue
        if any(
            name.startswith("libqwayland-") or name == "libqwayland-generic.so"
            for name in os.listdir(platform_dir)
        ):
            return  # wayland platform plugin present — use it
        os.environ["QT_QPA_PLATFORM"] = "xcb"
        return
    os.environ["QT_QPA_PLATFORM"] = "xcb"


def _apply_install_badge(lbl: QLabel, ok: bool, ok_text: str = "Installed",
                         warn_text: str = "Not Installed") -> None:
    if ok:
        bg = "#121e2d"
        fg = "#4fc1ff"
        border = "#1c3d60"
        text = ok_text
    else:
        bg = "#171d27"
        fg = "#a9b5c7"
        border = "#2e394c"
        text = warn_text

    lbl.setText(f"  {text}  ")
    lbl.setStyleSheet(
        f"background: {bg}; color: {fg}; border: 1px solid {border}; "
        "border-radius: 10px; padding: 3px 8px; font-size: 11px; "
        "font-weight: 700; letter-spacing: 0.2px;"
    )

# ── Worker thread ──────────────────────────────────────────────────────────────
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


class UpdateCheckWorker(TrackedThread):
    """Checks if a newer image is available in the registry without downloading anything.
    Compares the local booted digest against the remote manifest via skopeo inspect.
    Emits result(state, remote_ts) where state is 'available', 'uptodate', or 'error'."""
    result = Signal(str, str)

    def run(self):
        local_data = _bootc_status_data() or {}
        booted = _nested_get(local_data, ("status", "booted")) or {}
        local_digest = None
        for path in (
            ("image", "imageDigest"),
            ("image", "digest"),
            ("imageDigest",),
            ("digest",),
        ):
            v = _nested_get(booted, path)
            if isinstance(v, str) and v.startswith("sha256:"):
                local_digest = v
                break

        if not local_digest:
            self.result.emit("error", "")
            return

        tag = _current_branch() or "latest"
        ref = f"{REGISTRY}:{tag}"

        try:
            r = subprocess.run(
                ["skopeo", "inspect", "--raw", "--no-creds", f"docker://{ref}"],
                capture_output=True, timeout=45,
            )
        except FileNotFoundError:
            self.result.emit("error", "")
            return
        except subprocess.TimeoutExpired:
            self.result.emit("error", "")
            return
        except Exception:
            self.result.emit("error", "")
            return

        if r.returncode != 0:
            self.result.emit("error", "")
            return

        # bootc stores the platform-specific (amd64) manifest digest in imageDigest,
        # not the OCI image index digest. Parse the index to extract the amd64 entry.
        # Fall back to hashing the raw bytes (for single-arch images with no index).
        remote_digest = None
        remote_ts = ""
        try:
            manifest = json.loads(r.stdout)
            for entry in manifest.get("manifests", []):
                plat = entry.get("platform", {})
                if plat.get("architecture") == "amd64" and plat.get("os") == "linux":
                    d = entry.get("digest", "")
                    if d.startswith("sha256:"):
                        remote_digest = d
                    break
            annotations = manifest.get("annotations") or {}
            raw_ts = annotations.get("org.opencontainers.image.created", "")
            if raw_ts:
                dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).astimezone()
                remote_ts = dt.strftime("%Y-%m-%d %H:%M %Z")
        except Exception:
            pass

        if remote_digest is None:
            remote_digest = "sha256:" + hashlib.sha256(r.stdout).hexdigest()

        if local_digest and remote_digest == local_digest:
            self.result.emit("uptodate", remote_ts)
        else:
            self.result.emit("available", remote_ts)


# ── Firmware check worker ──────────────────────────────────────────────────────
class FirmwareCheckWorker(TrackedThread):
    """Query fwupd for pending firmware updates (non-blocking background check).

    Emits result(count, summary) where count is:
      -1  fwupd unavailable or hard error
       0  up to date
       n  number of devices with pending updates
    """
    result = Signal(int, str)

    def run(self):
        _run_command(["fwupdmgr", "refresh", "--force"], timeout=30)
        updates = _run_command(["fwupdmgr", "get-updates"], timeout=20)
        if updates is None:
            self.result.emit(-1, "fwupd not available.")
            return
        if updates.returncode == 2 or not updates.stdout.strip():
            # exit code 2 = nothing to update
            self.result.emit(0, "")
            return
        if updates.returncode != 0:
            self.result.emit(-1, updates.stdout.strip() or "fwupdmgr get-updates failed.")
            return
        count = max(1, updates.stdout.count("Device ID:"))
        self.result.emit(count, updates.stdout.strip())


# ── Changelog worker ───────────────────────────────────────────────────────────
class ChangelogWorker(TrackedThread):
    """Fetches OCI revision annotations for the booted and latest remote images so the
    Update page can show a precise GitHub compare link instead of a generic commits URL."""
    result = Signal(str, str)  # (booted_rev, remote_rev) — short git SHAs, may be empty

    def _fetch_annotations(self, ref: str) -> dict:
        try:
            r = subprocess.run(
                ["skopeo", "inspect", "--raw", "--no-creds", f"docker://{ref}"],
                capture_output=True, timeout=30,
            )
            if r.returncode != 0:
                return {}
            manifest = json.loads(r.stdout)
            annotations = manifest.get("annotations") or {}
            # For multi-arch index the interesting annotations are on the amd64 entry.
            if not annotations.get("org.opencontainers.image.revision"):
                for entry in manifest.get("manifests", []):
                    plat = entry.get("platform", {})
                    if plat.get("architecture") == "amd64" and plat.get("os") == "linux":
                        annotations = entry.get("annotations") or annotations
                        break
            return annotations
        except Exception:
            return {}

    def run(self):
        tag = _current_branch() or "latest"
        booted_digest = _bootc_image_digest("booted")
        booted_rev = ""
        if booted_digest:
            ann = self._fetch_annotations(f"{REGISTRY}@{booted_digest[1]}")
            booted_rev = ann.get("org.opencontainers.image.revision", "")[:12]
        remote_ann = self._fetch_annotations(f"{REGISTRY}:{tag}")
        remote_rev = remote_ann.get("org.opencontainers.image.revision", "")[:12]
        self.result.emit(booted_rev, remote_rev)


# ── Hardware probe dataclass + worker ─────────────────────────────────────────
@dataclass
class HardwareProbe:
    title: str
    status: str
    summary: str
    details: str
    action: str | None = None
    action_page_key: str | None = None
    action_cmd: list[str] | None = None


class HardwareProbeWorker(TrackedThread):
    done = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            self.done.emit(_collect_hardware_probes())
        except Exception as exc:
            self.failed.emit(str(exc))


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


# ── Helper utilities ───────────────────────────────────────────────────────────
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


def _cancel_worker(
    owner: object,
    attr: str = "_worker",
    status_lbl: QLabel | None = None,
    log: QTextEdit | None = None,
    cancel_btn: QPushButton | None = None,
    message: str = "Cancelling...",
) -> bool:
    worker = getattr(owner, attr, None)
    if worker is None or not worker.isRunning() or not hasattr(worker, "cancel"):
        return False
    if cancel_btn is not None:
        cancel_btn.setEnabled(False)
    if status_lbl is not None:
        status_lbl.setText(message)
        status_lbl.setObjectName("status-warn")
        status_lbl.show()
        _restyle(status_lbl)
    if log is not None:
        log.append("\nCancel requested. Waiting for the running command to stop...")
        log.ensureCursorVisible()
    worker.cancel()
    return True


def _set_session_inhibit(owner: object, reason: str | None = None) -> None:
    current = getattr(owner, "_screen_inhibit_cookie", None)
    if reason is None:
        if current is None:
            return
        cmd = [
            "gdbus", "call", "--session",
            "--dest", "org.freedesktop.ScreenSaver",
            "--object-path", "/ScreenSaver",
            "--method", "org.freedesktop.ScreenSaver.UnInhibit",
            str(current),
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
        finally:
            owner._screen_inhibit_cookie = None
        return

    if current is not None:
        return

    cmd = [
        "gdbus", "call", "--session",
        "--dest", "org.freedesktop.ScreenSaver",
        "--object-path", "/ScreenSaver",
        "--method", "org.freedesktop.ScreenSaver.Inhibit",
        "kyth-welcome", reason,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
    except OSError:
        return

    if result.returncode != 0:
        return

    match = re.search(r"\((\d+),\)", result.stdout)
    if match:
        owner._screen_inhibit_cookie = int(match.group(1))


def _run_command(cmd: list[str], timeout: int = 5) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


def _command_stdout(cmd: list[str], timeout: int = 5) -> str:
    result = _run_command(cmd, timeout=timeout)
    if result is None:
        return ""
    return result.stdout.strip()


def _with_idle_inhibit(cmd: list[str], reason: str) -> list[str]:
    inhibit = shutil.which("systemd-inhibit")
    if not inhibit:
        return cmd
    return [inhibit, "--what=idle:sleep", f"--why={reason}", "--mode=block", *cmd]


# Short-lived cache for expensive read-only probes (bootc status, flatpak list).
# Helpers like _current_branch/_has_staged_update each spawn `bootc status`
# otherwise, and a single page refresh fans out into a dozen identical spawns.
# Worker invalidates on completion, so post-operation refreshes stay accurate.
_PROBE_CACHE_LOCK = threading.Lock()
_PROBE_CACHE: dict[str, tuple[float, object]] = {}
_BOOTC_CACHE_TTL = 5.0
_FLATPAK_CACHE_TTL = 10.0


def _invalidate_probe_caches() -> None:
    with _PROBE_CACHE_LOCK:
        _PROBE_CACHE.clear()


def _probe_cached(key: str, ttl: float, fetch):
    with _PROBE_CACHE_LOCK:
        hit = _PROBE_CACHE.get(key)
        if hit is not None and time.monotonic() - hit[0] < ttl:
            return hit[1]
        value = fetch()
        _PROBE_CACHE[key] = (time.monotonic(), value)
        return value


def _fetch_bootc_status_text() -> str:
    for cmd in (["sudo", "-n", "bootc", "status"], ["bootc", "status"]):
        result = _run_command(cmd, timeout=10)
        if result is None or result.returncode != 0 or not result.stdout.strip():
            continue
        return result.stdout.strip()
    return ""


def _bootc_status_text() -> str:
    return _probe_cached("bootc-status-text", _BOOTC_CACHE_TTL, _fetch_bootc_status_text)


def _fetch_bootc_status_data() -> dict | None:
    for cmd in (["sudo", "-n", "bootc", "status", "--json"], ["bootc", "status", "--json"]):
        result = _run_command(cmd, timeout=10)
        if result is None or result.returncode != 0 or not result.stdout.strip():
            continue
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            continue
    return None


def _bootc_status_data() -> dict | None:
    return _probe_cached("bootc-status-data", _BOOTC_CACHE_TTL, _fetch_bootc_status_data)


def _nested_get(data: object, path: tuple[str, ...]) -> object | None:
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _walk_strings(data: object):
    if isinstance(data, str):
        yield data
        return
    if isinstance(data, dict):
        for value in data.values():
            yield from _walk_strings(value)
        return
    if isinstance(data, list):
        for value in data:
            yield from _walk_strings(value)


def _active_bootc_operation() -> str | None:
    result = _run_command(["ps", "-eo", "pid=,args="], timeout=5)
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return None
    for line in result.stdout.splitlines():
        text = line.strip()
        if not text or " bootc " not in f" {text} ":
            continue
        if any(op in text for op in (" bootc upgrade", " bootc switch", " bootc rollback", " bootc reset")):
            return text
    return None


def _default_phase(mode: str) -> str:
    return {
        "update": "Pulling OS image from container registry…",
        "topgrade": "Running full system update…",
        "rollback": "Staging rollback deployment…",
    }.get(mode, "Operation in progress…")


def _get_rx_bytes() -> int:
    """Sum RX bytes across all non-loopback interfaces from /proc/net/dev."""
    try:
        total = 0
        with open("/proc/net/dev") as f:
            for line in f:
                if ":" not in line:
                    continue
                iface, data = line.split(":", 1)
                if iface.strip() == "lo":
                    continue
                total += int(data.split()[0])
        return total
    except Exception:
        return 0


def _bootc_proxy_running() -> bool:
    """Return True if the skopeo image-proxy bootc spawns is still alive (download in progress)."""
    try:
        r = subprocess.run(
            ["pgrep", "-f", "skopeo.*image-proxy"],
            capture_output=True, timeout=2,
        )
        return r.returncode == 0
    except Exception:
        return False


def _get_disk_write_bytes() -> int:
    """Sum write bytes across all block devices from /proc/diskstats."""
    try:
        total = 0
        with open("/proc/diskstats") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 10:
                    total += int(parts[9])  # sectors written (512 bytes each)
        return total * 512
    except Exception:
        return 0


def _parse_size_bytes(size_str: str) -> int:
    """Parse '8.3 GB' or '500 MB' to bytes. Returns 0 on failure."""
    try:
        parts = size_str.strip().split()
        value = float(parts[0])
        unit = parts[1].upper().rstrip("B") if len(parts) > 1 else ""
        mult = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
        return int(value * mult.get(unit, 0))
    except Exception:
        return 0


def _human_bytes(n: int) -> str:
    """Format bytes as a human-readable string."""
    for unit, threshold in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if abs(n) >= threshold:
            return f"{n / threshold:.1f} {unit}"
    return f"{n} B"


def _human_bytes_pair(downloaded: int, total: int) -> tuple[str, str]:
    """Format a downloaded/total pair using the same unit, anchored to total."""
    for unit, threshold in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if abs(total) >= threshold:
            return f"{downloaded / threshold:.1f}", f"{total / threshold:.1f} {unit}"
    return str(downloaded), f"{total} B"


def _parse_update_phase(line: str, mode: str) -> str | None:
    """Map a raw output line to a short human-readable phase label, or None to keep the last."""
    lo = line.lower()
    # bootc / skopeo / ostree
    if "layers already present" in lo or "layers needed" in lo:
        return "Checking for new image layers…"
    if "resolved" in lo and ("image" in lo or REGISTRY in lo):
        return "Resolving OS image version…"
    if "fetching" in lo and ("manifest" in lo or "sha256" in lo):
        return "Fetching image manifest…"
    if any(k in lo for k in ("pulling", "copying", "fetching")) and any(
        k in lo for k in ("sha256", "blob", "layer", "ghcr.io", "registry")
    ):
        return "Downloading image layers…"
    if "unpacking" in lo or "extracting" in lo:
        return "Unpacking image layers…"
    if "checking out" in lo or "checkout" in lo or "importing" in lo:
        return "Importing image into system storage…"
    if "writing manifest" in lo or "manifest to image destination" in lo:
        return "Storing image manifest…"
    if "writing" in lo or "composing" in lo or "committing" in lo:
        return "Writing new OS image to disk…"
    if "rpmdb" in lo:
        return "Updating package database in the new image…"
    if "initramfs" in lo or "kernel" in lo:
        return "Preparing boot files for the new image…"
    if "deploying" in lo:
        return "Deploying new OS image…"
    if "staging" in lo or "staged" in lo or "transaction complete" in lo:
        return "Staging new image for next reboot…"
    if "no update available" in lo or "already booted" in lo:
        return "Already on the latest image — nothing to download."
    if "queued" in lo and "boot" in lo:
        return "Staged — new image ready for next reboot."
    # topgrade section headers look like "―― HH:MM:SS - Section Name ――"
    if mode == "topgrade" and line.startswith("――"):
        m = re.match(r"――\s*[\d:]+\s*-\s*(.+?)\s*――", line)
        if m:
            section = m.group(1).strip()
            if section:
                return f"Updating {section}…"
    return None


def _bootc_cancel_block_reason(mode: str, phase: str) -> str:
    if mode == "rollback":
        return "Rollback is already staging the previous deployment. Let it finish, then reboot or update again."
    if phase in {
        "Unpacking image layers…",
        "Download complete — processing image layers…",
        "Processing image layers…",
        "Importing image into system storage…",
        "Storing image manifest…",
        "Writing new OS image to disk…",
        "Updating package database in the new image…",
        "Preparing boot files for the new image…",
        "Deploying new OS image…",
        "Staging new image for next reboot…",
        "Staged — new image ready for next reboot.",
    }:
        return "The operation is past the safe cancel point and is writing or staging the new image. Let it finish."
    if "writing image to disk" in phase.lower() or "committing image" in phase.lower():
        return "The operation is writing the new image. Let it finish."
    return ""


def _bootc_image_reference() -> str | None:
    data = _bootc_status_data() or {}
    candidates = (
        ("status", "booted", "image", "reference"),
        ("status", "booted", "image", "image", "reference"),
        ("status", "booted", "image", "image", "image"),
        ("status", "booted", "image", "image"),
        ("status", "booted", "image"),
        ("spec", "image", "image"),
        ("spec", "image", "reference"),
    )
    for path in candidates:
        value = _nested_get(data, path)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in _walk_strings(data):
        stripped = value.strip()
        if REGISTRY in stripped:
            return stripped
    text = _bootc_status_text()
    if text:
        pattern = re.compile(rf"({re.escape(REGISTRY)}(?::[A-Za-z0-9._-]+)?(?:@sha256:[a-fA-F0-9]+)?)")
        match = pattern.search(text)
        if match:
            return match.group(1)
    # Fallback: rpm-ostree status (runs without root, works on ostree-managed systems)
    rpmostree = _run_command(["rpm-ostree", "status"], timeout=10)
    if rpmostree and rpmostree.returncode == 0:
        pattern = re.compile(rf"({re.escape(REGISTRY)}(?::[A-Za-z0-9._-]+)?(?:@sha256:[a-fA-F0-9]+)?)")
        match = pattern.search(rpmostree.stdout)
        if match:
            return match.group(1)
    return None


def _branch_from_ref(ref: str | None) -> str | None:
    if not ref:
        return None
    ref = ref.strip()
    if not ref:
        return None
    base = ref.split("@", 1)[0] if "@" in ref else ref
    if ":" in base:
        tag = base.rsplit(":", 1)[-1]
        if tag:
            return tag
    return None


def _branch_display_name(tag: str | None) -> str:
    if tag == "latest":
        return "Stable (latest)"
    if tag == "testing":
        return "Testing"
    if tag == "latest-cachy":
        return "Stable + CachyOS kernel"
    if tag == "testing-cachy":
        return "Testing + CachyOS kernel"
    return tag or "unknown"


def _current_branch() -> str | None:
    return _branch_from_ref(_bootc_image_reference())


def _current_kernel_flavor() -> str:
    try:
        with open("/usr/share/kyth/kernel-flavor") as fh:
            flavor = fh.read().strip().lower()
            if flavor in {"fedora", "cachy"}:
                return flavor
    except OSError:
        pass
    kernel = _command_stdout(["uname", "-r"]).lower()
    if "cachy" in kernel:
        return "cachy"
    return "fedora"


def _image_tag_for_channel(channel: str, flavor: str | None = None) -> str:
    base = "testing" if channel == "testing" else "latest"
    flavor = flavor or _current_kernel_flavor()
    suffix = "-cachy" if flavor == "cachy" else ""
    return f"{base}{suffix}"


def _image_tag_for_kernel(flavor: str) -> str:
    channel = "testing" if (_current_branch() or "").startswith("testing") else "latest"
    if flavor == "cachy":
        return f"{channel}-cachy"
    return channel


def _has_staged_update() -> bool:
    data = _bootc_status_data() or {}
    return data.get("status", {}).get("staged") is not None


def _has_rollback_deployment() -> bool:
    data = _bootc_status_data() or {}
    return data.get("status", {}).get("rollback") is not None


def _bootc_image_timestamp(section: str) -> str | None:
    """Return a human-readable build timestamp for 'booted', 'staged', or 'rollback'."""
    data = _bootc_status_data() or {}
    section_data = _nested_get(data, ("status", section)) or {}
    for path in (("image", "timestamp"), ("timestamp",)):
        value = _nested_get(section_data, path)
        if isinstance(value, str) and value.strip():
            try:
                dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00")).astimezone()
                return dt.strftime("%Y-%m-%d %H:%M %Z")
            except Exception:
                return value.strip()
    return None


def _bootc_image_digest(section: str) -> tuple[str, str] | None:
    """Return (short, full) sha256 digest for 'booted', 'staged', or 'rollback'. None if unavailable."""
    data = _bootc_status_data() or {}
    section_data = _nested_get(data, ("status", section)) or {}
    for path in (
        ("image", "imageDigest"),
        ("image", "digest"),
        ("imageDigest",),
        ("digest",),
    ):
        value = _nested_get(section_data, path)
        if isinstance(value, str) and value.startswith("sha256:"):
            full = value[7:]  # strip "sha256:" prefix
            return full[:12], full
    return None


def _installed_flatpak_ids() -> frozenset | None:
    """One `flatpak list` snapshot instead of a `flatpak info` spawn per app.
    Returns None when the listing itself fails (flatpak missing/broken)."""
    def fetch() -> frozenset | None:
        result = _run_command(["flatpak", "list", "--app", "--columns=application"], timeout=10)
        if result is None or result.returncode != 0:
            return None
        return frozenset(ln.strip() for ln in result.stdout.splitlines() if ln.strip())

    return _probe_cached("flatpak-apps", _FLATPAK_CACHE_TTL, fetch)


def _is_flatpak_installed(app_id: str) -> bool:
    ids = _installed_flatpak_ids()
    if ids is not None:
        return app_id in ids
    result = _run_command(["flatpak", "info", app_id], timeout=8)
    return result is not None and result.returncode == 0


# Window-class prefix each Chromium-family browser bakes into the app id of
# its --app windows (e.g. brave-teams.microsoft.com__-Default).
_CHROMIUM_APP_ID_PREFIX = {
    "chromium-browser": "chromium",
    "chromium": "chromium",
    "org.chromium.Chromium": "chromium",
    "brave-browser": "brave",
    "com.brave.Browser": "brave",
    "microsoft-edge": "msedge",
    "com.microsoft.Edge": "msedge",
    "google-chrome": "chrome",
    "com.google.Chrome": "chrome",
}


def _chromium_app_window_id(browser: str, url: str) -> str:
    """Wayland app id / X11 WM_CLASS a Chromium-family browser gives a window
    opened with --app=url: <prefix>-<host>_<path with / as _>-<profile>.
    --class/--name are ignored on Wayland, so StartupWMClass must carry this
    generated id for the task bar to match the window to its .desktop file."""
    parts = urlsplit(url)
    name = f"{parts.hostname or ''}_{parts.path or '/'}".replace("/", "_")
    return f"{_CHROMIUM_APP_ID_PREFIX[browser]}-{name}-Default"


def _chromium_app_window_cmd(url: str) -> tuple[list[str], str] | None:
    """Build a command that opens url as a dedicated app window, plus the
    window class the browser will assign to it, or None.

    KythOS ships Brave as a Flatpak, not a native chromium-browser binary, so
    native binaries are only found on systems where the user installed one.
    """
    args = [f"--app={url}"]
    for binary in ("chromium-browser", "chromium", "brave-browser",
                   "microsoft-edge", "google-chrome"):
        if shutil.which(binary):
            return [binary, *args], _chromium_app_window_id(binary, url)
    for app_id in ("com.brave.Browser", "org.chromium.Chromium",
                   "com.microsoft.Edge", "com.google.Chrome"):
        if _is_flatpak_installed(app_id):
            return (["flatpak", "run", app_id, *args],
                    _chromium_app_window_id(app_id, url))
    return None


def _install_flatpak_inline(owner: object, btn: QPushButton, app_id: str, name: str,
                            extra_cmd: str = "", done_cb=None) -> None:
    """Install a Flathub app on a Worker thread, driving the button state.

    In-app replacement for terminal-popping installs: the button itself shows
    progress and outcome, and polkit/askpass handles any elevation. extra_cmd
    is shell appended after a successful install (e.g. a flatpak override).
    One worker per app id, kept on `owner` so concurrent clicks are ignored.
    """
    attr = "_inline_install_" + re.sub(r"\W", "_", app_id)
    existing = getattr(owner, attr, None)
    if existing is not None and existing.isRunning():
        return
    orig = btn.text()
    btn.setEnabled(False)
    btn.setText("Installing…")
    cmd = (
        "flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
        f" && flatpak install -y --or-update flathub {shlex.quote(app_id)}"
    )
    if extra_cmd:
        cmd += f" && {extra_cmd}"
    worker = Worker(["bash", "-c", cmd])

    def _done(code: int):
        _finish_worker(owner, attr=attr)
        if code == 0:
            btn.setText("✓ Installed")
            btn.setToolTip(f"{name} is installed. Find it in the app launcher.")
        else:
            btn.setText(orig)
            btn.setEnabled(True)
            btn.setToolTip(f"Install failed (exit {code}). Check your network connection and try again.")
        if done_cb:
            done_cb(code)

    worker.done.connect(_done)
    setattr(owner, attr, worker)
    worker.start()


_DEFAULT_FIRST_RUN_APPS = (
    ("com.valvesoftware.Steam", "Steam"),
    ("net.lutris.Lutris", "Lutris"),
    ("com.heroicgameslauncher.hgl", "Heroic"),
    ("com.usebottles.bottles", "Bottles"),
    ("com.github.mtkennerly.ludusavi", "Ludusavi"),
    ("com.dec05eba.gpu_screen_recorder", "GPU Screen Recorder"),
    ("io.github.benjamimgois.goverlay", "GOverlay"),
    ("dev.vencord.Vesktop", "Vesktop"),
)


def _first_run_app_setup_state() -> tuple[str, str, list[str]]:
    if _IS_LIVE:
        return (
            "live",
            "Live sessions include the KythOS tools and launcher defaults. Install to this PC for persistent app setup.",
            [],
        )
    missing = [name for app_id, name in _DEFAULT_FIRST_RUN_APPS if not _is_flatpak_installed(app_id)]
    done = os.path.exists("/var/lib/kyth/default-flatpaks-v8-done")
    if not missing:
        return "ready", "Steam, game launchers, Bottles, save backup, and gaming tools are ready.", []

    status_path = os.path.expanduser("~/.local/share/kyth/first-run-apps.status")
    status: dict[str, str] = {}
    if os.path.exists(status_path):
        try:
            with open(status_path, encoding="utf-8") as fh:
                for line in fh:
                    if "=" in line:
                        key, value = line.rstrip("\n").split("=", 1)
                        status[key] = shlex.split(value)[0] if value else ""
        except Exception:
            status = {}

    service = _run_command(["systemctl", "is-active", "kyth-default-flatpaks.service"], timeout=3)
    service_state = service.stdout.strip() if service and service.stdout.strip() else ""
    if service_state in {"active", "activating"} or status.get("state") == "setting_up":
        return (
            "setting_up",
            f"KythOS is finishing app setup in the background. Pending: {', '.join(missing)}.",
            missing,
        )
    if service_state == "failed" or status.get("state") == "failed":
        return (
            "failed",
            f"Default app setup needs a retry. Pending: {', '.join(missing)}.",
            missing,
        )
    if done:
        return (
            "partial",
            f"Setup finished, but these apps are still missing: {', '.join(missing)}.",
            missing,
        )
    return (
        "pending",
        f"Connect to the network and let KythOS finish first-run app setup. Pending: {', '.join(missing)}.",
        missing,
    )


def _davinci_flatpak_app_id() -> str | None:
    for app_id in (
        "com.blackmagic.Resolve",
        "com.blackmagic.ResolveStudio",
        "com.blackmagicdesign.resolve",
    ):
        if _is_flatpak_installed(app_id):
            return app_id
    return None


def _davinci_download_dir() -> str:
    candidate = _command_stdout(["xdg-user-dir", "DOWNLOAD"])
    if candidate:
        candidate = os.path.expanduser(candidate)
        if os.path.isdir(candidate):
            return candidate
    return os.path.expanduser("~/Downloads")


def _davinci_zip_candidates() -> list[str]:
    roots: list[str] = []
    for candidate in (_davinci_download_dir(), os.path.expanduser("~/Downloads")):
        expanded = os.path.abspath(os.path.expanduser(candidate))
        if os.path.isdir(expanded) and expanded not in roots:
            roots.append(expanded)

    patterns = (
        "DaVinci_Resolve*_Linux.zip",
        "DaVinci_Resolve_Studio*_Linux.zip",
        "*DaVinci*Resolve*Linux*.zip",
    )
    matches: dict[str, float] = {}
    for root in roots:
        for pattern in patterns:
            for base in (root, os.path.join(root, "*")):
                for path in glob.glob(os.path.join(base, pattern)):
                    if os.path.isfile(path):
                        try:
                            matches[path] = os.path.getmtime(path)
                        except OSError:
                            matches[path] = 0

    return sorted(matches, key=lambda item: (matches[item], item.lower()), reverse=True)


def _rclone_available() -> bool:
    return shutil.which("rclone") is not None


def _rclone_list_remotes() -> list[tuple[str, str]]:
    """Return [(name, type), …] for every configured rclone remote."""
    result = _run_command(["rclone", "listremotes", "--long"], timeout=5)
    if result is None or result.returncode != 0:
        return []
    remotes: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            remotes.append((parts[0].rstrip(":"), parts[1].lower()))
    return remotes


def _rclone_has_remote_type(remote_type: str) -> bool:
    """Return True only when a remote whose type is *exactly* remote_type exists."""
    return any(rtype == remote_type.lower() for _, rtype in _rclone_list_remotes())


def _load_sync_config() -> dict:
    """Load {remote_name: {folder, last_sync, last_ok}} from disk."""
    try:
        with open(_CLOUD_SYNC_CONFIG) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_sync_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(_CLOUD_SYNC_CONFIG), exist_ok=True)
    with open(_CLOUD_SYNC_CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)


# ── SMB/CIFS network share helpers ────────────────────────────────────────────

def _load_smb_config() -> list[dict]:
    try:
        with open(_SMB_CONFIG) as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_smb_config(shares: list[dict]) -> None:
    os.makedirs(os.path.dirname(_SMB_CONFIG), exist_ok=True)
    fd = os.open(_SMB_CONFIG, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(shares, f, indent=2)


def _systemd_escape_mount_path(path: str) -> str:
    """Return the systemd .mount unit filename for a given absolute mount path."""
    try:
        r = subprocess.run(
            ["systemd-escape", "--path", "--suffix=mount", path],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    # Fallback: strip leading /, replace / with -, append .mount
    return path.lstrip("/").replace("/", "-") + ".mount"


def _is_cifs_available() -> bool:
    return bool(shutil.which("mount.cifs"))


def _is_mounted(path: str) -> bool:
    try:
        r = subprocess.run(
            ["findmnt", "--noheadings", "--target", path],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def _build_add_share_script(share: dict, mount_now: bool) -> str:
    import base64 as _b64
    name       = share["name"]
    server     = share["server"]
    share_path = share["share_path"].lstrip("/")
    mount_pt   = share["mount_point"]
    username   = share["username"]
    password   = share.get("password", "")
    domain     = share.get("domain", "")
    auto_mount = share.get("auto_mount", False)
    uid        = os.getuid()
    gid        = os.getgid()

    unit_name  = _systemd_escape_mount_path(mount_pt)
    cred_file  = f"{_SMB_CREDS_DIR}/{name}"
    unc        = f"//{server}/{share_path}"
    opts       = (
        f"credentials={cred_file},uid={uid},gid={gid},"
        "iocharset=utf8,vers=3.0,nofail,_netdev"
    )

    creds = f"username={username}\npassword={password}\n"
    if domain:
        creds += f"domain={domain}\n"
    creds_b64 = _b64.b64encode(creds.encode()).decode()

    unit = "\n".join([
        "[Unit]",
        f"Description=SMB Share {unc}",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Mount]",
        f"What={unc}",
        f"Where={mount_pt}",
        "Type=cifs",
        f"Options={opts}",
        "TimeoutSec=30",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
    ])
    unit_b64 = _b64.b64encode(unit.encode()).decode()
    creds_dir_q = shlex.quote(_SMB_CREDS_DIR)
    cred_file_q = shlex.quote(cred_file)
    mount_pt_q = shlex.quote(mount_pt)
    unit_path_q = shlex.quote(f"/etc/systemd/system/{unit_name}")
    unit_name_q = shlex.quote(unit_name)

    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"mkdir -p {creds_dir_q}",
        f"chmod 700 {creds_dir_q}",
        f"echo '{creds_b64}' | base64 -d > {cred_file_q}",
        f"chmod 600 {cred_file_q}",
        f"mkdir -p {mount_pt_q}",
        f"echo '{unit_b64}' | base64 -d > {unit_path_q}",
        "systemctl daemon-reload",
    ]
    if auto_mount:
        lines.append(f"systemctl enable {unit_name_q}")
    if mount_now:
        lines.append(f"systemctl start {unit_name_q} || true")

    return "\n".join(lines)


def _build_remove_share_script(share: dict) -> str:
    name      = share["name"]
    mount_pt  = share["mount_point"]
    unit_name = _systemd_escape_mount_path(mount_pt)
    cred_file = f"{_SMB_CREDS_DIR}/{name}"
    unit_name_q = shlex.quote(unit_name)
    unit_path_q = shlex.quote(f"/etc/systemd/system/{unit_name}")
    cred_file_q = shlex.quote(cred_file)

    return "\n".join([
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"systemctl stop {unit_name_q} 2>/dev/null || true",
        f"systemctl disable {unit_name_q} 2>/dev/null || true",
        f"rm -f {unit_path_q}",
        "systemctl daemon-reload",
        f"rm -f {cred_file_q}",
    ])


def _open_terminal_with_cmd(args: list[str], title: str = "") -> bool:
    """Launch args inside a terminal window; try several emulators. Returns True on success."""
    # xdg-terminal-exec is the XDG standard launcher (installed on KythOS)
    if shutil.which("xdg-terminal-exec"):
        try:
            subprocess.Popen(["xdg-terminal-exec"] + args)
            return True
        except OSError:
            pass
    # Konsole — --hold keeps the window open after the command exits
    if shutil.which("konsole"):
        try:
            opts = ["konsole", "--hold"]
            if title:
                opts += ["--title", title]
            subprocess.Popen(opts + ["-e"] + args)
            return True
        except OSError:
            pass
    # xterm fallback
    if shutil.which("xterm"):
        try:
            opts = ["xterm", "-hold"]
            if title:
                opts += ["-T", title]
            subprocess.Popen(opts + ["-e"] + args)
            return True
        except OSError:
            pass
    return False


def _mangohud_installed() -> bool:
    return shutil.which("mangohud") is not None


def _gamescope_installed() -> bool:
    return shutil.which("gamescope") is not None


def _vkbasalt_installed() -> bool:
    return any(
        os.path.exists(p) for p in (
            "/usr/lib64/vkbasalt/libvkbasalt.so",
            "/usr/lib/vkbasalt/libvkbasalt.so",
            "/usr/lib64/libvkbasalt.so",
            "/usr/lib/libvkbasalt.so",
        )
    )


def _ge_proton_version() -> str | None:
    """Return the latest installed GE-Proton directory name, or None."""
    found: list[str] = []
    for base in (
        "/usr/share/steam/compatibilitytools.d",
        "/var/lib/kyth/ge-proton",
    ):
        try:
            found.extend(e for e in os.listdir(base) if e.startswith("GE-Proton"))
        except OSError:
            pass
    return sorted(found)[-1] if found else None


def _compat_tool_version(prefix: str) -> str | None:
    """Return the latest installed Steam compatibility tool matching prefix."""
    bases = [
        "/usr/share/steam/compatibilitytools.d",
        "/var/lib/kyth/ge-proton",
        os.path.expanduser("~/.steam/root/compatibilitytools.d"),
        os.path.expanduser("~/.steam/steam/compatibilitytools.d"),
        os.path.expanduser("~/.local/share/Steam/compatibilitytools.d"),
    ]
    found: list[str] = []
    for base in bases:
        try:
            found.extend(e for e in os.listdir(base) if e.lower().startswith(prefix.lower()))
        except OSError:
            pass
    return sorted(found)[-1] if found else None


def _ntsync_state() -> tuple[str, str]:
    if os.path.exists("/dev/ntsync"):
        return "ok", "/dev/ntsync is present."
    module_probe = _run_command(["modprobe", "-n", "ntsync"], timeout=5)
    if module_probe is not None and module_probe.returncode == 0:
        return "warn", "ntsync module exists but /dev/ntsync is not present yet."
    return "warn", "ntsync device not detected; Proton will fall back to fsync/esync."


def _vulkan_state() -> tuple[str, str]:
    if shutil.which("vulkaninfo"):
        result = _run_command(["vulkaninfo", "--summary"], timeout=12)
        if result is not None and result.returncode == 0:
            gpus = [
                line.split("=", 1)[1].strip()
                for line in result.stdout.splitlines()
                if "deviceName" in line and "=" in line
            ]
            return "ok", "Vulkan ready" + (f": {', '.join(gpus[:2])}" if gpus else ".")
        return "err", "vulkaninfo is installed but Vulkan probing failed."
    render_nodes = glob.glob("/dev/dri/renderD*")
    if render_nodes:
        return "warn", "Render device exists, but vulkaninfo is not installed for a full check."
    return "err", "No Vulkan render device detected."


def _gaming_health_items(*, controllers: dict | None = None,
                         windows_drives: list | None = None) -> list[tuple[str, str, str]]:
    """Small, fast checks aimed at PC gamers before they launch a title.

    controllers/windows_drives accept precomputed probe results so callers that
    build several sections (the gaming dashboard) don't repeat the hardware scans.
    """
    ge_ver = _ge_proton_version()
    cachy_ver = _compat_tool_version("proton-cachyos")
    vulkan_status, vulkan_summary = _vulkan_state()
    ntsync_status, ntsync_summary = _ntsync_state()
    steam_ok = _is_flatpak_installed("com.valvesoftware.Steam")
    heroic_ok = _is_flatpak_installed("com.heroicgameslauncher.hgl")
    lutris_ok = _is_flatpak_installed("net.lutris.Lutris")
    if controllers is None:
        controllers = _detect_controllers()
    controller_count = len(controllers.get("usb_controllers", [])) + len(controllers.get("input_nodes", []))
    if windows_drives is None:
        windows_drives = _find_ntfs_drives()
    ntfs_count = sum(not d.get("is_bitlocker") for d in windows_drives)
    bitlocker_count = sum(bool(d.get("is_bitlocker")) for d in windows_drives)
    if bitlocker_count:
        windows_drive_summary = (
            f"{ntfs_count} readable NTFS and {bitlocker_count} locked BitLocker "
            "partition(s) detected; unlock and migrate them below."
        )
    else:
        windows_drive_summary = f"{ntfs_count} NTFS partition(s) detected; use migration below."

    return [
        ("ok" if steam_ok else "warn", "Steam", "Installed." if steam_ok else "Install Steam to run your Steam library."),
        ("ok" if ge_ver else "err", "GE-Proton", ge_ver or "Missing; use Update GE-Proton below."),
        ("ok" if cachy_ver else "dim", "Proton-CachyOS SLR", cachy_ver or "Optional runner for stubborn games."),
        (vulkan_status, "Vulkan", vulkan_summary),
        (ntsync_status, "NTSYNC", ntsync_summary),
        ("ok" if shutil.which("umu-run") else "warn", "umu-launcher", "Installed." if shutil.which("umu-run") else "Needed by some Lutris/Heroic launcher flows."),
        ("ok" if _gamescope_installed() else "warn", "Gamescope", "Installed." if _gamescope_installed() else "Missing compositor for HDR/VRR/upscaling presets."),
        ("ok" if _mangohud_installed() else "warn", "MangoHud", "Installed." if _mangohud_installed() else "Missing performance overlay."),
        ("ok" if controller_count else "dim", "Controllers", f"{controller_count} controller input(s) detected." if controller_count else "Connect one and press Refresh."),
        ("ok" if heroic_ok or lutris_ok else "dim", "Non-Steam launchers", "Heroic or Lutris installed." if heroic_ok or lutris_ok else "Install Heroic or Lutris for Epic, GOG, Battle.net, EA, and Ubisoft."),
        ("warn" if windows_drives else "ok", "PC game drives", windows_drive_summary if windows_drives else "No PC game drives detected."),
        ("warn" if _has_staged_update() else "ok", "OS update", "Update staged; reboot before benchmarking." if _has_staged_update() else "No staged OS update."),
    ]


def _gaming_migration_checklist_items(*, controllers: dict | None = None,
                                      windows_drives: list | None = None,
                                      saves: tuple | None = None) -> list[tuple[str, str, str]]:
    steam_ok = _is_flatpak_installed("com.valvesoftware.Steam")
    heroic_ok = _is_flatpak_installed("com.heroicgameslauncher.hgl")
    lutris_ok = _is_flatpak_installed("net.lutris.Lutris")
    discord_ok = _is_flatpak_installed("com.discordapp.Discord")
    obs_ok = _is_flatpak_installed("com.obsproject.Studio")
    ludusavi_status, _, ludusavi_summary = saves if saves is not None else _ludusavi_backup_summary()
    controller_info = controllers if controllers is not None else _detect_controllers()
    controller_count = len(controller_info.get("usb_controllers", [])) + len(controller_info.get("input_nodes", []))
    if windows_drives is None:
        windows_drives = _find_ntfs_drives()
    ntfs_count = sum(not d.get("is_bitlocker") for d in windows_drives)
    bitlocker_count = sum(bool(d.get("is_bitlocker")) for d in windows_drives)
    if bitlocker_count:
        migration_summary = (
            f"{ntfs_count} readable NTFS and {bitlocker_count} locked BitLocker "
            "partition(s) detected; unlock them on Move Files first."
        )
    else:
        migration_summary = f"{ntfs_count} NTFS partition(s) detected; copy games read-only below."
    ge_ver = _ge_proton_version()
    return [
        ("ok" if steam_ok else "warn", "Steam installed", "Ready." if steam_ok else "Install Steam, then enable Steam Play for all titles."),
        ("ok" if ge_ver else "err", "GE-Proton ready", ge_ver or "Missing; update GE-Proton before testing PC games."),
        ("ok" if heroic_ok and lutris_ok else "warn", "Non-Steam launchers", "Heroic and Lutris installed." if heroic_ok and lutris_ok else "Install Heroic for Epic/GOG and Lutris for Battle.net/EA/Ubisoft."),
        (ludusavi_status, "Saves backed up", ludusavi_summary),
        ("warn" if windows_drives else "dim", "Game library migration", migration_summary if windows_drives else "No PC game drive detected."),
        ("ok" if controller_count else "dim", "Controller tested", f"{controller_count} controller input(s) detected." if controller_count else "Connect a controller and use the Controllers page to verify input."),
        ("ok" if discord_ok and obs_ok else "warn", "Social and capture", "Discord and OBS installed." if discord_ok and obs_ok else "Install Discord and OBS if this player streams, records, or joins voice chat."),
        ("ok", "Blocked games explained", "Compatibility page uses dated source checks for anti-cheat blockers."),
    ]


def _collect_gaming_dashboard() -> dict:
    # Probe hardware and saves once; health and checklist share the results.
    controllers = _detect_controllers()
    windows_drives = _find_ntfs_drives()
    saves = _ludusavi_backup_summary()
    return {
        "health": _gaming_health_items(controllers=controllers, windows_drives=windows_drives),
        "checklist": _gaming_migration_checklist_items(
            controllers=controllers, windows_drives=windows_drives, saves=saves),
        "streaming": _streaming_health_items(),
        "saves": saves,
        "games": _detect_installed_games(),
    }


def _ludusavi_backup_summary() -> tuple[str, str, str]:
    ludusavi_ok = _is_flatpak_installed("com.github.mtkennerly.ludusavi")
    candidates = [
        os.path.expanduser("~/Ludusavi"),
        os.path.expanduser("~/Games/Ludusavi"),
        os.path.expanduser("~/Documents/Ludusavi"),
        os.path.expanduser("~/.var/app/com.github.mtkennerly.ludusavi"),
    ]
    existing = [path for path in candidates if os.path.exists(path)]
    if ludusavi_ok and existing:
        newest = max(existing, key=lambda path: os.path.getmtime(path))
        return "ok", "Save backups", f"Ludusavi installed; backup/config path found: {newest}"
    if ludusavi_ok:
        return "warn", "Save backups", "Ludusavi installed; run a backup before migration or modding."
    return "warn", "Save backups", "Install Ludusavi before importing saves or modding."


def _parse_steam_acf(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    except OSError:
        return {}
    return _parse_steam_acf_text(text)


def _parse_steam_acf_text(text: str) -> dict:
    data: dict[str, str] = {}
    for key in ("appid", "name", "installdir"):
        match = re.search(rf'"{re.escape(key)}"\s+"([^"]*)"', text, re.IGNORECASE)
        if match:
            data[key] = match.group(1)
    return data


def _steam_library_roots() -> list[str]:
    roots: list[str] = []
    for root in (
        os.path.expanduser("~/.local/share/Steam"),
        os.path.expanduser("~/.steam/steam"),
        os.path.expanduser("~/.var/app/com.valvesoftware.Steam/.local/share/Steam"),
    ):
        if os.path.isdir(root) and root not in roots:
            roots.append(root)

    for root in list(roots):
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        try:
            with open(vdf, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            lib = match.group(1).replace("\\\\", "/")
            lib = os.path.expanduser(lib)
            if os.path.isdir(lib) and lib not in roots:
                roots.append(lib)
    return roots


_PROC_MOUNT_ESCAPE_RE = re.compile(r"\\([0-7]{3})")


def _decode_proc_mount_field(value: str) -> str:
    """Decode the octal escapes used by /proc/mounts fields."""
    return _PROC_MOUNT_ESCAPE_RE.sub(
        lambda match: chr(int(match.group(1), 8)),
        value,
    )


def _steam_libraries_on_ntfs() -> list[str]:
    """Steam library roots that sit on an NTFS/other system filesystem.

    Reusing the old PC game drive as a Steam library is the first thing
    most switchers try, and Proton breaks on NTFS in ways that look like
    "Linux gaming is broken" rather than "wrong filesystem" — so detect it
    proactively instead of waiting for the support request.
    """
    mounts: list[tuple[str, str]] = []
    try:
        with open("/proc/mounts", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 3:
                    # /proc/mounts octal-escapes spaces and tabs in mount points.
                    mount_point = _decode_proc_mount_field(parts[1])
                    mounts.append((mount_point, parts[2].lower()))
    except OSError:
        return []
    # Longest mount point first so nested mounts resolve to the right fs.
    mounts.sort(key=lambda entry: len(entry[0]), reverse=True)

    flagged: list[str] = []
    for root in _steam_library_roots():
        real = os.path.realpath(root)
        for mount_point, fstype in mounts:
            if real == mount_point or real.startswith(mount_point.rstrip("/") + "/"):
                # ntfs-3g mounts report as "fuseblk"; exFAT/FAT are equally
                # unfit for Proton prefixes (no symlinks), so flag them too.
                if fstype in ("ntfs", "ntfs3", "fuseblk", "exfat", "vfat"):
                    flagged.append(root)
                break
    return flagged


def _detect_steam_games() -> list[dict]:
    games: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for root in _steam_library_roots():
        steamapps = os.path.join(root, "steamapps")
        for manifest in glob.glob(os.path.join(steamapps, "appmanifest_*.acf")):
            data = _parse_steam_acf(manifest)
            name = data.get("name", "").strip()
            appid = data.get("appid", "").strip()
            installdir = data.get("installdir", "").strip()
            if not name:
                continue
            install_path = os.path.join(steamapps, "common", installdir) if installdir else steamapps
            key = ("Steam", appid or name.lower())
            if key in seen:
                continue
            seen.add(key)
            games.append({
                "name": name,
                "launcher": "Steam",
                "path": install_path,
                "appid": appid,
            })
    return games


def _detect_heroic_games() -> list[dict]:
    games: list[dict] = []
    seen: set[str] = set()
    roots = [
        os.path.expanduser("~/.config/heroic"),
        os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic"),
    ]
    for root in roots:
        for pattern in (
            os.path.join(root, "GamesConfig", "*.json"),
            os.path.join(root, "legendaryConfig", "legendary", "installed.json"),
            os.path.join(root, "gog_store", "installed.json"),
        ):
            for path in glob.glob(pattern):
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                        data = json.load(fh)
                except (OSError, json.JSONDecodeError):
                    continue
                entries = data.values() if isinstance(data, dict) else data if isinstance(data, list) else []
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    name = (
                        entry.get("title")
                        or entry.get("name")
                        or entry.get("app_name")
                        or entry.get("appName")
                        or ""
                    )
                    install_path = (
                        entry.get("install_path")
                        or entry.get("installPath")
                        or entry.get("path")
                        or entry.get("folder_name")
                        or ""
                    )
                    name = str(name).strip()
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    games.append({
                        "name": name,
                        "launcher": "Heroic",
                        "path": str(install_path),
                        "appid": str(entry.get("app_name") or entry.get("appName") or ""),
                    })
    return games


def _detect_lutris_games() -> list[dict]:
    games: list[dict] = []
    seen: set[str] = set()
    roots = [
        os.path.expanduser("~/.local/share/lutris/games"),
        os.path.expanduser("~/.var/app/net.lutris.Lutris/data/lutris/games"),
    ]
    for root in roots:
        for path in glob.glob(os.path.join(root, "*.yml")) + glob.glob(os.path.join(root, "*.yaml")):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    text = fh.read()
            except OSError:
                continue
            name_match = re.search(r"(?m)^\s*name:\s*[\"']?(.+?)[\"']?\s*$", text)
            game_match = re.search(r"(?m)^\s*game_slug:\s*[\"']?(.+?)[\"']?\s*$", text)
            path_match = re.search(r"(?m)^\s*(?:prefix|working_dir):\s*[\"']?(.+?)[\"']?\s*$", text)
            name = (name_match.group(1) if name_match else "").strip()
            if not name:
                name = os.path.splitext(os.path.basename(path))[0].replace("-", " ").title()
            key = (game_match.group(1) if game_match else name).lower()
            if key in seen:
                continue
            seen.add(key)
            games.append({
                "name": name,
                "launcher": "Lutris",
                "path": (path_match.group(1).strip() if path_match else path),
                "appid": "",
            })
    return games


def _detect_bottles_apps() -> list[dict]:
    games: list[dict] = []
    seen: set[str] = set()
    roots = [
        os.path.expanduser("~/.local/share/bottles/bottles"),
        os.path.expanduser("~/.var/app/com.usebottles.bottles/data/bottles/bottles"),
    ]
    for root in roots:
        for path in glob.glob(os.path.join(root, "*")):
            if not os.path.isdir(path):
                continue
            name = os.path.basename(path).replace("_", " ").replace("-", " ").strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            games.append({
                "name": name,
                "launcher": "Bottles",
                "path": path,
                "appid": "",
            })
    return games


def _detect_installed_games() -> list[dict]:
    games = []
    games.extend(_detect_steam_games())
    games.extend(_detect_heroic_games())
    games.extend(_detect_lutris_games())
    games.extend(_detect_bottles_apps())
    games.sort(key=lambda item: (item.get("launcher", ""), item.get("name", "").lower()))
    return games


def _load_protondb_cache() -> dict[str, str]:
    try:
        with open(_PROTONDB_CACHE_PATH, encoding="utf-8") as _f:
            data = json.load(_f)
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save_protondb_cache(cache: dict[str, str]) -> None:
    try:
        os.makedirs(os.path.dirname(_PROTONDB_CACHE_PATH), exist_ok=True)
        with open(_PROTONDB_CACHE_PATH, "w", encoding="utf-8") as _f:
            json.dump(cache, _f)
    except OSError:
        pass


class _ProtonDbBatchWorker(TrackedThread):
    """Fetches ProtonDB tiers for a list of Steam appids, skipping already-cached ones."""
    tier_fetched = Signal(str, str)   # (appid, tier)
    finished_all = Signal(dict)       # full {appid: tier} map

    def __init__(self, appids: list[str], existing: dict[str, str]):
        super().__init__()
        self._appids = appids
        self._existing = dict(existing)

    def run(self):
        result = dict(self._existing)
        for appid in self._appids:
            if not appid or appid in result:
                continue
            try:
                req = Request(
                    f"https://www.protondb.com/api/v1/reports/summaries/{appid}.json",
                    headers={"User-Agent": "KythOS-GameCheck/1.0"},
                )
                with urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    tier = data.get("tier") or "pending"
                    result[appid] = tier
                    self.tier_fetched.emit(appid, tier)
            except Exception:
                result[appid] = "pending"
            time.sleep(0.06)
        self.finished_all.emit(result)


def _streaming_health_items() -> list[tuple[str, str, str]]:
    pipewire_ok = shutil.which("pw-cli") is not None or shutil.which("wpctl") is not None
    obs_capture_ok = any(
        os.path.exists(path) for path in (
            "/usr/lib64/libobs_vkcapture.so",
            "/usr/lib/libobs_vkcapture.so",
            "/usr/lib64/obs-plugins/libobs_vkcapture.so",
            "/usr/lib/obs-plugins/libobs_vkcapture.so",
        )
    )
    v4l2_probe = _run_command(["modprobe", "-n", "v4l2loopback"], timeout=4)
    v4l2_ok = v4l2_probe is not None and v4l2_probe.returncode == 0
    mic_hint = "PipeWire ready; test mic in Discord/OBS." if pipewire_ok else "PipeWire tools not found."
    obs_ok = _is_flatpak_installed("com.obsproject.Studio")
    discord_ok = _is_flatpak_installed("com.discordapp.Discord")

    return [
        ("ok" if obs_ok else "warn", "OBS Studio", "Installed." if obs_ok else "Install OBS for capture and streaming."),
        ("ok" if discord_ok else "warn", "Discord", "Installed." if discord_ok else "Install Discord for voice and screen share testing."),
        ("ok" if pipewire_ok else "warn", "PipeWire", mic_hint),
        ("ok" if obs_capture_ok else "warn", "Game capture", "obs-vkcapture runtime present." if obs_capture_ok else "obs-vkcapture runtime not detected."),
        ("ok" if v4l2_ok else "dim", "Virtual camera", "v4l2loopback available." if v4l2_ok else "Optional: v4l2loopback not available."),
    ]


def _detect_nvidia() -> bool:
    try:
        r = subprocess.run(["lspci"], capture_output=True, text=True, timeout=5)
        return "nvidia" in r.stdout.lower()
    except Exception:
        return False


def _nvidia_module_loaded() -> bool:
    try:
        r = subprocess.run(["lsmod"], capture_output=True, text=True, timeout=5)
        return "nvidia" in r.stdout.lower()
    except Exception:
        return False


def _akmod_nvidia_built() -> bool:
    try:
        r = subprocess.run(["modinfo", "nvidia"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def _akmod_nvidia_installed() -> bool:
    try:
        r = subprocess.run(["rpm", "-q", "akmod-nvidia"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def _hw_setup_service_state() -> str:
    """Returns the systemd active state of kyth-hw-setup.service.
    Possible values: 'activating' (running), 'active' (done), 'failed', 'inactive', or ''."""
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "kyth-hw-setup.service"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def _hw_setup_done() -> bool:
    return os.path.exists("/var/lib/kyth/hw-setup-done")


def _status_palette(status: str) -> tuple[str, str, str]:
    if status == "ok":
        return ("#121e2d", "#4fc1ff", "OK")
    if status == "warn":
        return ("#152030", "#e0af68", "Warning")
    if status == "err":
        return ("#2b1520", "#f7768e", "Issue")
    return ("#1e1e2e", "#45475a", "Info")


# ── Hardware probes ────────────────────────────────────────────────────────────
def _gpu_probe(pci_text: str, lsmod_text: str) -> HardwareProbe:
    gpu_lines = [
        line.strip()
        for line in pci_text.splitlines()
        if any(token in line.lower() for token in ("vga compatible controller", "3d controller", "display controller"))
    ]
    if not gpu_lines:
        return HardwareProbe(
            "Graphics", "dim",
            "No GPU information detected.",
            "The helper app could not find a display adapter via lspci.",
        )

    has_nvidia = any("nvidia" in line.lower() for line in gpu_lines)
    has_amd = any("[amd/ati]" in line.lower() or "advanced micro devices" in line.lower() for line in gpu_lines)
    has_intel = any("intel corporation" in line.lower() for line in gpu_lines)
    vendors = [v for v, flag in [("NVIDIA", has_nvidia), ("AMD", has_amd), ("Intel", has_intel)] if flag]
    hybrid = len(vendors) > 1

    if has_nvidia:
        if _nvidia_module_loaded():
            summary = "Hybrid graphics active with NVIDIA drivers." if hybrid else "NVIDIA GPU with active proprietary drivers."
            return HardwareProbe("Graphics", "ok", summary, "Detected:\n" + "\n".join(gpu_lines))
        if _akmod_nvidia_built():
            return HardwareProbe(
                "Graphics", "warn",
                "NVIDIA drivers installed but not yet active.",
                "The nvidia module exists for this kernel but is not loaded.\nDetected:\n" + "\n".join(gpu_lines),
                "Reboot to activate the staged driver.",
                action_page_key="NVIDIA",
            )
        summary = "Hybrid graphics: NVIDIA driver not active." if hybrid else "NVIDIA hardware found without an active driver."
        return HardwareProbe(
            "Graphics", "err", summary,
            "Detected:\n" + "\n".join(gpu_lines),
            "Open NVIDIA Drivers to build and stage the driver.",
            action_page_key="NVIDIA",
        )

    if has_amd:
        loaded = "amdgpu" in lsmod_text.lower()
        status = "ok" if loaded else "warn"
        summary = "AMD GPU — amdgpu driver loaded." if loaded else "AMD GPU — amdgpu driver not found in lsmod."
        return HardwareProbe("Graphics", status, summary, "Detected:\n" + "\n".join(gpu_lines))

    if has_intel:
        loaded = "i915" in lsmod_text.lower() or "\nxe " in f"\n{lsmod_text.lower()}"
        status = "ok" if loaded else "warn"
        summary = "Intel GPU — kernel driver loaded." if loaded else "Intel GPU — no kernel driver found in lsmod."
        return HardwareProbe("Graphics", status, summary, "Detected:\n" + "\n".join(gpu_lines))

    return HardwareProbe("Graphics", "dim", "GPU detected, vendor not recognized.", "Detected:\n" + "\n".join(gpu_lines))


def _firmware_probe() -> HardwareProbe:
    devices = _run_command(["fwupdmgr", "get-devices"], timeout=15)
    if devices is None:
        return HardwareProbe("Firmware", "dim", "fwupd not available.", "Install fwupd to inspect firmware-managed devices.")
    if devices.returncode != 0:
        return HardwareProbe(
            "Firmware", "warn",
            "Firmware tooling installed but device enumeration failed.",
            devices.stdout.strip() or "fwupdmgr get-devices exited with an error.",
        )

    device_count = devices.stdout.count("Device ID:")
    updates = _run_command(["fwupdmgr", "get-updates"], timeout=20)
    if updates is not None and updates.returncode == 0:
        return HardwareProbe(
            "Firmware", "warn",
            f"Firmware updates available for {device_count or 'one or more'} device(s).",
            updates.stdout.strip() or devices.stdout.strip(),
        )
    if updates is not None and updates.returncode == 2:
        return HardwareProbe(
            "Firmware", "ok",
            f"fwupd managing {device_count} device(s), no pending updates.",
            devices.stdout.strip(),
        )
    return HardwareProbe(
        "Firmware", "dim",
        f"fwupd available, {device_count} managed device(s).",
        devices.stdout.strip(),
    )


def _connectivity_probe(pci_text: str, usb_text: str) -> HardwareProbe:
    combined = "\n".join([pci_text.lower(), usb_text.lower()])
    wifi_present = any(token in combined for token in ("network controller", "wireless", "wi-fi", "802.11", "wlan"))
    bluetooth_present = "bluetooth" in combined
    rfkill = _command_stdout(["rfkill", "list"], timeout=5)
    nmcli = _command_stdout(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"], timeout=5)

    blocked = []
    if rfkill:
        lines = rfkill.lower().splitlines()
        if any("soft blocked: yes" in l for l in lines):
            blocked.append("soft-blocked")
        if any("hard blocked: yes" in l for l in lines):
            blocked.append("hard-blocked")

    wifi_states = [l for l in nmcli.splitlines() if ":wifi:" in l]

    parts = []
    if wifi_present:
        parts.append("Wi-Fi")
    if bluetooth_present:
        parts.append("Bluetooth")

    if not parts:
        return HardwareProbe(
            "Connectivity", "dim",
            "No Wi-Fi or Bluetooth hardware detected.",
            "Expected on desktops or virtual machines.",
        )

    details = []
    if wifi_states:
        details.append("NetworkManager:\n" + "\n".join(wifi_states))
    if rfkill:
        details.append("rfkill:\n" + rfkill)

    if blocked:
        return HardwareProbe(
            "Connectivity", "warn",
            f"{', '.join(parts)} detected but radio is {', '.join(blocked)}.",
            "\n\n".join(details) or "rfkill reports blocked radios.",
            "Enable Wireless",
            action_cmd=["rfkill", "unblock", "all"],
        )

    return HardwareProbe(
        "Connectivity", "ok",
        f"{', '.join(parts)} hardware detected and ready.",
        "\n\n".join(details) or "Wireless hardware looks healthy.",
    )


def _audio_probe() -> HardwareProbe:
    pipewire = _run_command(["systemctl", "--user", "is-active", "pipewire.service"], timeout=5)
    wireplumber = _run_command(["systemctl", "--user", "is-active", "wireplumber.service"], timeout=5)
    pactl_info = _run_command(["pactl", "info"], timeout=5)
    sinks = _command_stdout(["pactl", "list", "short", "sinks"], timeout=5)
    sink_count = len([l for l in sinks.splitlines() if l.strip()])

    if pactl_info is None:
        return HardwareProbe("Audio", "dim", "Audio inspection tools not available.", "Could not query pactl.")

    if pactl_info.returncode != 0:
        return HardwareProbe(
            "Audio", "warn",
            "PipeWire is not responding to pactl.",
            pactl_info.stdout.strip() or "pactl info returned a non-zero exit code.",
            "Log out and back in, then refresh.",
        )

    services = []
    if pipewire is not None and pipewire.returncode == 0:
        services.append("pipewire")
    if wireplumber is not None and wireplumber.returncode == 0:
        services.append("wireplumber")

    if sink_count == 0:
        return HardwareProbe(
            "Audio", "warn",
            "Audio services running but no playback sinks detected.",
            (pactl_info.stdout.strip() + "\n\nSinks:\n" + (sinks or "none")).strip(),
            "Reconnect audio hardware or inspect your session config.",
        )

    return HardwareProbe(
        "Audio", "ok",
        f"Audio stack healthy — {sink_count} playback sink(s).",
        ("Services: " + ", ".join(services) + "\n\n" if services else "") + pactl_info.stdout.strip(),
    )


def _controller_probe(usb_text: str, lsmod_text: str) -> HardwareProbe:
    _GAMING_VIDS: dict[str, str] = {
        "045e": "Xbox",
        "054c": "PlayStation",
        "057e": "Nintendo",
        "2dc8": "8BitDo",
        "0f0d": "HORI",
        "28de": "Valve",
        "20d6": "PowerA",
        "0e6f": "PDP",
    }
    _XONE_DONGLE_PIDS = {"02e6", "02fe"}
    _DUALSENSE_PIDS   = {"0ce6", "0df2"}
    _DS4_PIDS         = {"05c4", "09cc", "0ba0"}

    usb_controllers: list[str] = []
    xone_dongle     = False
    dualsense_found = False

    for line in usb_text.splitlines():
        m = re.search(r"ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)", line)
        if not m:
            continue
        vid, pid, desc = m.group(1).lower(), m.group(2).lower(), m.group(3).strip()
        if vid not in _GAMING_VIDS:
            continue
        if vid == "045e" and pid in _XONE_DONGLE_PIDS:
            xone_dongle = True
            usb_controllers.append("Xbox Wireless USB Dongle")
        elif vid == "054c" and pid in _DUALSENSE_PIDS:
            dualsense_found = True
            usb_controllers.append("PlayStation DualSense")
        elif vid == "054c" and pid in _DS4_PIDS:
            usb_controllers.append("PlayStation DualShock 4")
        else:
            usb_controllers.append(desc or f"{_GAMING_VIDS[vid]} controller")

    # /dev/input/by-id catches Bluetooth controllers and anything lsusb missed
    input_nodes: list[str] = []
    try:
        for name in sorted(os.listdir("/dev/input/by-id")):
            if any(tok in name.lower() for tok in ("joystick", "gamepad", "controller")):
                input_nodes.append(name)
    except OSError:
        pass

    lsmod_norm = lsmod_text.lower().replace("-", "_")
    xone_loaded    = "xone_hid"      in lsmod_norm
    xpadneo_loaded = "xpadneo"       in lsmod_norm
    hid_ps_loaded  = "hid_playstation" in lsmod_norm

    if not usb_controllers and not input_nodes:
        return HardwareProbe(
            "Controllers", "dim",
            "No gaming controllers detected.",
            (
                "Supported out of the box: Xbox (USB wired/wireless dongle), PlayStation\n"
                "DualSense / DualShock 4, Nintendo Switch Pro, 8BitDo, and most USB or\n"
                "Bluetooth HID controllers.\n\n"
                "Connect a controller and press Refresh."
            ),
        )

    details_parts: list[str] = []
    if usb_controllers:
        details_parts.append("USB devices:\n" + "\n".join(f"  {c}" for c in usb_controllers))
    if input_nodes:
        details_parts.append("Input nodes:\n" + "\n".join(f"  {n}" for n in input_nodes))
    active_mods = [label for label, flag in [
        ("xpadneo (Xbox BT)",       xpadneo_loaded),
        ("xone_hid (Xbox dongle)",  xone_loaded),
        ("hid_playstation (PS4/5)", hid_ps_loaded),
    ] if flag]
    if active_mods:
        details_parts.append("Active modules: " + ", ".join(active_mods))
    details = "\n\n".join(details_parts)

    # Xbox wireless dongle present but xone module not active → firmware step needed
    if xone_dongle and not xone_loaded:
        xone_cmd = shutil.which("xone-dongle-install") or shutil.which("xone-firmware-install")
        firmware_hint = (
            f"Run:  sudo {xone_cmd}" if xone_cmd
            else "Run:  sudo xone-dongle-install"
        )
        return HardwareProbe(
            "Controllers", "warn",
            "Xbox Wireless USB Dongle detected — firmware setup required before controllers can pair.",
            (
                details + "\n\n"
                "The xone kernel module is installed but the dongle has not been flashed with\n"
                "Microsoft's firmware. Xbox wireless controllers cannot connect until this step\n"
                "is complete.\n\n" + firmware_hint
            ),
            "Install Xbox dongle firmware (opens password prompt)",
            action_cmd=(["pkexec", xone_cmd] if xone_cmd else None),
        )

    n = len(usb_controllers) or len(input_nodes)
    summary = f"{n} controller{'s' if n != 1 else ''} detected and ready."
    if dualsense_found:
        if shutil.which("dualsensectl"):
            summary += " DualSense haptics and adaptive triggers available via dualsensectl."
        else:
            summary += " DualSense connected — adaptive triggers and haptics work in supported games."

    return HardwareProbe("Controllers", "ok", summary, details)


def _strip_ansi(text: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)


def _format_display_mode(mode: str) -> str:
    m = re.match(r'(\d+)x(\d+)@([\d.]+)', mode)
    if not m:
        return mode
    try:
        hz = float(m.group(3))
    except ValueError:
        return mode
    return f"{m.group(1)}×{m.group(2)} @ {hz:.0f}Hz"


def _cpu_probe() -> HardwareProbe:
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as fh:
            cpuinfo = fh.read()
    except OSError:
        return HardwareProbe("CPU", "dim", "Could not read CPU information.", "/proc/cpuinfo not accessible.")

    model = next(
        (line.split(":", 1)[1].strip() for line in cpuinfo.splitlines() if line.startswith("model name")),
        "Unknown CPU",
    )
    # Trim redundant suffix noise
    model = re.sub(r'\s+(CPU|Processor)\s*$', '', model, flags=re.IGNORECASE).strip()

    logical = sum(1 for line in cpuinfo.splitlines() if line.startswith("processor"))

    # Physical cores: Core(s) per socket × Socket(s) from lscpu
    physical: int | None = None
    lscpu_out = _command_stdout(["lscpu"], timeout=5)
    cores_per_sock = sockets = None
    for line in lscpu_out.splitlines():
        if line.startswith("Core(s) per socket:"):
            try:
                cores_per_sock = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        if line.startswith("Socket(s):"):
            try:
                sockets = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    if cores_per_sock and sockets:
        physical = cores_per_sock * sockets

    gov_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
    try:
        governor = open(gov_path).read().strip()
    except OSError:
        governor = None

    # sched-ext state
    scx_state: str | None = None
    try:
        scx_state = open("/sys/kernel/sched_ext/state").read().strip()
    except OSError:
        pass

    scx_scheduler: str | None = None
    try:
        with open("/etc/scx/scx_loader.conf") as fh:
            for line in fh:
                if line.startswith("SCX_SCHEDULER="):
                    scx_scheduler = line.split("=", 1)[1].strip()
                    break
    except OSError:
        pass

    details: list[str] = [f"Model:    {model}"]
    if physical and logical:
        smt = f" / {logical} threads (SMT on)" if logical > physical else ""
        details.append(f"Cores:    {physical}{smt}")
    elif logical:
        details.append(f"Logical CPUs: {logical}")
    if governor:
        details.append(f"Governor: {governor}")

    scx_blurb = ""
    if scx_state == "enabled" and scx_scheduler:
        short = scx_scheduler.replace("scx_", "")
        details.append(f"Scheduler: {scx_scheduler} via sched-ext (active)")
        scx_blurb = f" {short.upper()} gaming scheduler active."
    elif scx_state == "enabled":
        details.append("Scheduler: sched-ext active")
        scx_blurb = " sched-ext gaming scheduler active."
    elif scx_scheduler:
        svc = _run_command(["systemctl", "is-active", "scx_loader.service"], timeout=5)
        if svc and svc.returncode == 0:
            short = scx_scheduler.replace("scx_", "")
            details.append(f"Scheduler: {scx_scheduler} (scx_loader active)")
            scx_blurb = f" {short.upper()} gaming scheduler active."
        else:
            details.append(f"Scheduler: {scx_scheduler} configured — scx_loader not running")
    else:
        details.append("Scheduler: CFS (sched-ext not configured)")

    summary = model + "." + scx_blurb if not scx_blurb else model + "." + scx_blurb
    return HardwareProbe("CPU", "ok", summary, "\n".join(details))


def _memory_probe() -> HardwareProbe:
    try:
        meminfo: dict[str, str] = {}
        with open("/proc/meminfo") as fh:
            for line in fh:
                k, _, v = line.partition(":")
                meminfo[k.strip()] = v.strip()
    except OSError:
        return HardwareProbe("Memory", "dim", "Could not read memory information.", "/proc/meminfo not accessible.")

    def _kb(key: str) -> float:
        raw = meminfo.get(key, "0")
        try:
            return int(raw.split()[0])
        except (ValueError, IndexError):
            return 0.0

    total_kb = _kb("MemTotal")
    avail_kb = _kb("MemAvailable")
    total_gb = total_kb / (1024 * 1024)
    avail_gb = avail_kb / (1024 * 1024)
    used_gb  = total_gb - avail_gb

    if total_gb >= 32:
        tier, status = "excellent for gaming", "ok"
    elif total_gb >= 16:
        tier, status = "good for gaming", "ok"
    elif total_gb >= 8:
        tier, status = "adequate for most games", "ok"
    else:
        tier, status = "below recommended for modern games (16 GB+)", "warn"

    details = (
        f"Total:     {total_gb:.1f} GB\n"
        f"In use:    {used_gb:.1f} GB\n"
        f"Available: {avail_gb:.1f} GB"
    )

    swap_out = _command_stdout(["swapon", "--show=NAME,SIZE,TYPE", "--noheadings"], timeout=5)
    if swap_out:
        details += "\n\nSwap:\n" + "\n".join(f"  {l}" for l in swap_out.splitlines())

    return HardwareProbe("Memory", status, f"{total_gb:.0f} GB RAM — {tier}.", details)


def _display_probe() -> HardwareProbe:
    kscreen_raw = _command_stdout(["kscreen-doctor", "-o"], timeout=8)

    if kscreen_raw:
        return _parse_kscreen_output(kscreen_raw)

    # Fallback: sysfs DRM enumeration (resolution only, no refresh rate)
    connected: list[str] = []
    for status_path in sorted(glob.glob("/sys/class/drm/card*/card*-*/status")):
        try:
            if open(status_path).read().strip() != "connected":
                continue
        except OSError:
            continue
        connector = os.path.basename(os.path.dirname(status_path))
        _, _, name = connector.partition("-")
        modes_path = os.path.join(os.path.dirname(status_path), "modes")
        try:
            first_mode = open(modes_path).readline().strip()
        except OSError:
            first_mode = ""
        connected.append(f"{name}{': ' + first_mode if first_mode else ''}")

    if not connected:
        return HardwareProbe("Display", "dim", "No connected displays detected via DRM.", "kscreen-doctor unavailable and no DRM outputs found.")

    return HardwareProbe(
        "Display", "ok",
        f"{len(connected)} display{'s' if len(connected) > 1 else ''} connected.",
        "Outputs:\n" + "\n".join(f"  {c}" for c in connected) + "\n\n(Install kscreen for refresh rate and VRR details.)",
    )


def _parse_kscreen_output(raw: str) -> HardwareProbe:
    text = _strip_ansi(raw)

    outputs: list[dict] = []
    cur: dict | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("Output:"):
            if cur is not None:
                outputs.append(cur)
            parts = line.split()
            name = parts[2] if len(parts) > 2 else "Unknown"
            cur = {"name": name, "enabled": False, "connected": False,
                   "current_mode": None, "vrr": "", "hdr": "", "modes": []}
        elif cur is None:
            continue
        elif line == "enabled":
            cur["enabled"] = True
        elif line == "connected":
            cur["connected"] = True
        elif line.startswith("Modes:"):
            for token in line[6:].split():
                m = re.match(r'\d+:([\dx@.\d]+)([*!]*)', token)
                if not m:
                    continue
                mode_str = m.group(1)
                cur["modes"].append(mode_str)
                if "*" in m.group(2):
                    cur["current_mode"] = mode_str
        elif line.lower().startswith("vrr:"):
            cur["vrr"] = line.split(":", 1)[1].strip().lower()
        elif line.lower().startswith("hdr:"):
            cur["hdr"] = line.split(":", 1)[1].strip().lower()

    if cur is not None:
        outputs.append(cur)

    active = [o for o in outputs if o["connected"] and o["enabled"]]
    if not active:
        return HardwareProbe("Display", "dim", "No active displays detected.", text.strip()[:600])

    display_strs: list[str] = []
    details_parts: list[str] = []
    vrr_warnings: list[str] = []

    for out in active:
        mode = out["current_mode"] or (out["modes"][0] if out["modes"] else "")
        mode_fmt = _format_display_mode(mode) if mode else "unknown resolution"

        attrs: list[str] = []
        vrr = out["vrr"]
        hdr = out["hdr"]
        if vrr and vrr not in ("never", "incapable", ""):
            attrs.append(f"VRR {vrr}")
        if hdr == "enabled":
            attrs.append("HDR")

        label = out["name"] + ": " + mode_fmt
        if attrs:
            label += f" ({', '.join(attrs)})"
        display_strs.append(label)

        mode_list = ", ".join(out["modes"][:8])
        if len(out["modes"]) > 8:
            mode_list += f" (+{len(out['modes']) - 8} more)"
        detail_lines = [
            f"{out['name']}: {mode_fmt}",
            f"  VRR: {vrr or 'unknown'}",
            f"  HDR: {hdr or 'unknown'}",
        ]
        if mode_list:
            detail_lines.append(f"  Available: {mode_list}")
        details_parts.append("\n".join(detail_lines))

        # Warn if high-refresh monitor has VRR capable but disabled
        if vrr == "never":
            max_hz = 0.0
            for m_str in out["modes"]:
                hz_m = re.search(r'@([\d.]+)', m_str)
                if hz_m:
                    try:
                        max_hz = max(max_hz, float(hz_m.group(1)))
                    except ValueError:
                        continue
            if max_hz >= 100:
                vrr_warnings.append(
                    f"{out['name']} supports up to {max_hz:.0f}Hz but VRR/FreeSync is set to Never."
                )

    n = len(active)
    summary = f"{n} display{'s' if n > 1 else ''}: " + " · ".join(display_strs) + "."
    details = "\n\n".join(details_parts)

    if vrr_warnings:
        return HardwareProbe(
            "Display", "warn",
            summary,
            details + "\n\n" + "\n".join(vrr_warnings),
            "Enable VRR in System Settings → Display & Monitor for smoother gameplay.",
        )

    return HardwareProbe("Display", "ok", summary, details)


def _thermal_probe() -> HardwareProbe:
    cpu_readings: dict[str, float] = {}
    gpu_readings: dict[str, float] = {}

    for hwmon_dir in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        try:
            name = open(os.path.join(hwmon_dir, "name")).read().strip()
        except OSError:
            continue

        is_cpu = name in ("k10temp", "coretemp", "zenpower", "nct6798", "it8686")
        is_gpu = name in ("amdgpu", "radeon", "nouveau")
        if not is_cpu and not is_gpu:
            continue

        for temp_input in sorted(glob.glob(os.path.join(hwmon_dir, "temp*_input"))):
            label_file = temp_input.replace("_input", "_label")
            label = ""
            try:
                if os.path.exists(label_file):
                    label = open(label_file).read().strip()
            except OSError:
                pass
            try:
                temp_c = int(open(temp_input).read().strip()) / 1000.0
            except (OSError, ValueError):
                continue
            if not (1 < temp_c < 130):
                continue

            key = label if label else os.path.basename(temp_input).replace("_input", "")
            if is_cpu:
                cpu_readings[key] = temp_c
            else:
                gpu_readings[key] = temp_c

    if not cpu_readings and not gpu_readings:
        return HardwareProbe(
            "Thermal", "dim",
            "No temperature sensors detected.",
            "hwmon drivers (k10temp, amdgpu) must be loaded for temperature monitoring.",
        )

    details_parts: list[str] = []
    hot: list[str] = []

    if cpu_readings:
        # Prefer Tdie for AMD (Tctl adds a 10°C offset), or Package for Intel
        cpu_display_temp = (
            cpu_readings.get("Tdie")
            or cpu_readings.get("Package id 0")
            or next(iter(cpu_readings.values()))
        )
        cpu_lines = "\n".join(f"  {k}: {v:.0f}°C" for k, v in sorted(cpu_readings.items()))
        details_parts.append(f"CPU:\n{cpu_lines}")
        if cpu_display_temp > 90:
            hot.append(f"CPU at {cpu_display_temp:.0f}°C — check cooling.")
        elif cpu_display_temp > 80:
            hot.append(f"CPU at {cpu_display_temp:.0f}°C — warm, monitor under load.")

    if gpu_readings:
        gpu_display_temp = (
            gpu_readings.get("junction")
            or gpu_readings.get("edge")
            or next(iter(gpu_readings.values()))
        )
        gpu_lines = "\n".join(f"  {k}: {v:.0f}°C" for k, v in sorted(gpu_readings.items()))
        details_parts.append(f"GPU:\n{gpu_lines}")
        if gpu_display_temp > 90:
            hot.append(f"GPU at {gpu_display_temp:.0f}°C — check airflow.")

    summary_parts: list[str] = []
    if cpu_readings:
        t = cpu_readings.get("Tdie") or cpu_readings.get("Package id 0") or next(iter(cpu_readings.values()))
        summary_parts.append(f"CPU {t:.0f}°C")
    if gpu_readings:
        t = gpu_readings.get("junction") or gpu_readings.get("edge") or next(iter(gpu_readings.values()))
        summary_parts.append(f"GPU {t:.0f}°C")

    summary = "Temperatures: " + ", ".join(summary_parts) + "."
    details = "\n\n".join(details_parts)
    status = "warn" if hot else "ok"
    action = "  ".join(hot) if hot else None

    return HardwareProbe("Thermal", status, summary + (" " + "  ".join(hot) if hot else ""), details, action)


def _peripheral_probe(usb_text: str) -> HardwareProbe:
    _GAMING_VIDS: dict[str, str] = {
        "1532": "Razer",
        "1b1c": "Corsair",
        "1038": "SteelSeries",
        "046d": "Logitech",
        "0b05": "ASUS ROG",
        "1e7d": "Roccat",
        "0951": "HyperX",
        "187c": "Alienware",
        "10f5": "Turtle Beach",
        "0fd9": "Elgato",
        "20a0": "Wooting",
    }

    found: dict[str, list[str]] = {}
    razer_found = False

    for line in usb_text.splitlines():
        m = re.search(r"ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)", line)
        if not m:
            continue
        vid, _pid, desc = m.group(1).lower(), m.group(2).lower(), m.group(3).strip()
        if vid not in _GAMING_VIDS:
            continue
        vendor = _GAMING_VIDS[vid]
        found.setdefault(vendor, []).append(desc or f"{vendor} device")
        if vid == "1532":
            razer_found = True

    if not found:
        return HardwareProbe(
            "Peripherals", "dim",
            "No gaming peripherals detected.",
            (
                "Supported: Razer (via OpenRazer), Corsair, SteelSeries, Logitech G,\n"
                "ASUS ROG, Roccat, HyperX, Wooting, Elgato, and Alienware.\n\n"
                "Connect peripherals via USB and press Refresh."
            ),
        )

    details_parts: list[str] = []
    for vendor, devices in sorted(found.items()):
        details_parts.append(f"{vendor}:\n" + "\n".join(f"  {d}" for d in devices))

    action_label: str | None = None
    action_cmd: list[str] | None = None

    if razer_found:
        r = _run_command(["systemctl", "--user", "is-active", "openrazer-daemon.service"], timeout=5)
        daemon_active = r is not None and r.returncode == 0
        if daemon_active:
            details_parts.append("OpenRazer daemon: active — RGB and DPI controls ready.")
        else:
            details_parts.append("OpenRazer daemon: not running — RGB and DPI controls unavailable.")
            action_label = "Start OpenRazer daemon"
            action_cmd = ["systemctl", "--user", "start", "openrazer-daemon.service"]

    n = sum(len(v) for v in found.values())
    vendors = list(found.keys())
    if len(vendors) == 1:
        summary = f"{n} {vendors[0]} device{'s' if n > 1 else ''} detected."
    else:
        summary = f"{n} gaming peripherals detected: {', '.join(vendors)}."

    if action_label:
        return HardwareProbe(
            "Peripherals", "warn",
            summary + " OpenRazer daemon not running.",
            "\n\n".join(details_parts),
            action_label,
            action_cmd=action_cmd,
        )

    return HardwareProbe("Peripherals", "ok", summary, "\n\n".join(details_parts))


def _displaylink_probe(usb_text: str, lsmod_text: str) -> HardwareProbe:
    found_desc: str | None = None
    for line in usb_text.splitlines():
        m = re.search(r"ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)", line)
        if not m:
            continue
        vid, _pid, desc = m.group(1).lower(), m.group(2).lower(), m.group(3).strip()
        if vid == "17e9":
            found_desc = desc or "DisplayLink dock/adapter"
            break

    if not found_desc:
        return HardwareProbe(
            "DisplayLink dock", "dim",
            "No DisplayLink dock or adapter detected.",
            (
                "DisplayLink USB/USB-C docks let you drive extra monitors from a "
                "single port. Connect one and press Refresh."
            ),
        )

    if re.search(r"^evdi\s", lsmod_text, re.MULTILINE):
        return HardwareProbe(
            "DisplayLink dock", "ok",
            f"{found_desc} connected — driver active.",
            "The evdi kernel module is loaded; extra displays through this dock should work.",
        )

    return HardwareProbe(
        "DisplayLink dock", "warn",
        f"{found_desc} detected, but the driver is not installed.",
        (
            "The evdi kernel module isn't loaded, so extra monitors on this dock "
            "won't show video.\n\nRun `ujust install-displaylink` in a terminal to "
            "install and sign the evdi driver, then reboot."
        ),
    )


def _storage_probe() -> HardwareProbe:
    usage = shutil.disk_usage("/home")
    free_pct = (usage.free / usage.total) * 100 if usage.total else 0
    trim = _run_command(["systemctl", "is-enabled", "fstrim.timer"], timeout=5)
    trim_enabled = trim is not None and trim.returncode == 0

    summary = f"/home has {free_pct:.1f}% free space."
    details = (
        f"Total: {usage.total / (1024**3):.1f} GiB\n"
        f"Used:  {(usage.total - usage.free) / (1024**3):.1f} GiB\n"
        f"Free:  {usage.free / (1024**3):.1f} GiB\n"
        f"TRIM timer: {'enabled' if trim_enabled else 'disabled'}"
    )
    if free_pct < 15:
        return HardwareProbe("Storage", "warn", summary, details, "Free up space to avoid update and install failures.")
    return HardwareProbe("Storage", "ok", summary, details)


def _platform_probe() -> HardwareProbe:
    virt = _run_command(["systemd-detect-virt"], timeout=5)
    is_vm = virt is not None and virt.returncode == 0
    virt_name = (virt.stdout.strip() or "virtual machine") if is_vm else None

    # Secure Boot state from EFI variable (4-byte attribute header + 1-byte value)
    _SB_VAR = "/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c"
    secure_boot: bool | None = None
    try:
        data = open(_SB_VAR, "rb").read()
        if len(data) >= 5:
            secure_boot = (data[4] == 1)
    except OSError:
        pass

    branch  = _branch_display_name(_current_branch())
    staged  = "yes" if _has_staged_update() else "no"

    if is_vm:
        spice = _run_command(["systemctl", "is-active", "spice-vdagentd.service"], timeout=5)
        spice_active = spice is not None and spice.returncode == 0
        return HardwareProbe(
            "Platform", "dim",
            f"Running inside {virt_name}.",
            (
                f"Environment: {virt_name}\n"
                f"spice-vdagentd: {'active' if spice_active else 'inactive'}\n"
                f"Branch: {branch}\nStaged update: {staged}"
            ),
            "Some gaming and driver checks behave differently in VMs.",
        )

    sb_label = {True: "enabled", False: "disabled", None: "unknown"}.get(secure_boot, "unknown")
    details = f"Branch: {branch}\nStaged update: {staged}\nSecure Boot: {sb_label}"

    if secure_boot:
        return HardwareProbe(
            "Platform", "warn",
            "Bare-metal, Secure Boot enabled — unsigned DKMS modules may not load.",
            details + (
                "\n\nSecure Boot is ON. DKMS modules (xone Xbox dongle, xpadneo Xbox BT)\n"
                "must be signed via MOK to load. If Xbox wireless support is missing,\n"
                "enroll the Machine Owner Key or disable Secure Boot in firmware settings."
            ),
            "If Xbox wireless is missing, check MOK enrollment or disable Secure Boot.",
        )

    return HardwareProbe("Platform", "ok", "Bare-metal environment detected.", details)


def _tail_file(path: str, max_lines: int = 80) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return ""
    return "".join(lines[-max_lines:]).strip()


def _system_hub_log_has_self_error(log_tail: str) -> bool:
    if not log_tail:
        return False
    sections = re.split(r"(?m)^==== .+ kyth-welcome launch ====$", log_tail)
    recent = sections[-1] if sections else log_tail
    # External tools opened from System Hub can inherit stderr into the launcher
    # log. Only flag messages that look like the Hub itself failed to start.
    hub_markers = (
        "kyth-welcome launch failed",
        "traceback (most recent call last)",
        'file "/usr/bin/kyth-welcome"',
        "qt.qpa.plugin",
        "could not load the qt platform plugin",
        "segmentation fault",
        "core dumped",
    )
    lowered = recent.lower()
    if any(marker in lowered for marker in hub_markers):
        return True
    return bool(re.search(r"(?m)^(error|failed|aborted):", recent, re.IGNORECASE))


def _system_hub_probe() -> HardwareProbe:
    app_path = "/usr/bin/kyth-welcome"
    launcher_path = "/usr/bin/kyth-welcome-launch"
    desktop_path = "/usr/share/applications/kyth-welcome.desktop"
    autostart_path = os.path.expanduser("~/.config/autostart/kyth-welcome.desktop")
    cache_home = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    log_path = os.path.join(cache_home, "kyth", "kyth-welcome.log")

    app_ok = os.path.isfile(app_path) and os.access(app_path, os.X_OK)
    launcher_ok = os.path.isfile(launcher_path) and os.access(launcher_path, os.X_OK)
    desktop_text = _tail_file(desktop_path, max_lines=40)
    desktop_uses_launcher = "Exec=/usr/bin/kyth-welcome-launch" in desktop_text
    autostart_text = _tail_file(autostart_path, max_lines=40)
    autostart_uses_launcher = (
        not os.path.exists(autostart_path)
        or "Exec=/usr/bin/kyth-welcome-launch" in autostart_text
    )
    log_tail = _tail_file(log_path)

    details = [
        f"{app_path}: {'executable' if app_ok else 'missing or not executable'}",
        f"{launcher_path}: {'executable' if launcher_ok else 'missing or not executable'}",
        f"{desktop_path}: {'uses launcher' if desktop_uses_launcher else 'missing or points directly at app'}",
        f"{autostart_path}: {'absent/complete' if not os.path.exists(autostart_path) else ('uses launcher' if autostart_uses_launcher else 'points directly at app')}",
        f"{log_path}: {'present' if log_tail else 'not present or empty'}",
    ]
    if log_tail:
        details.extend(["", "Recent launch log:", log_tail])

    if not app_ok:
        return HardwareProbe(
            "System Hub", "err",
            "System Hub executable is missing or not runnable.",
            "\n".join(details),
            "Reinstall /usr/bin/kyth-welcome from the current image or repository checkout.",
        )

    if not launcher_ok or not desktop_uses_launcher or not autostart_uses_launcher:
        return HardwareProbe(
            "System Hub", "warn",
            "System Hub is installed, but the launcher diagnostics wrapper is not fully active.",
            "\n".join(details),
            "Install kyth-welcome-launch and refresh the desktop entry so launch failures are logged.",
        )

    if _system_hub_log_has_self_error(log_tail):
        return HardwareProbe(
            "System Hub", "warn",
            "Recent System Hub launch log contains an error.",
            "\n".join(details),
            "Review the recent launch log included above.",
        )

    return HardwareProbe(
        "System Hub", "ok",
        "System Hub launcher and diagnostics wrapper are installed.",
        "\n".join(details),
    )


def _vaapi_failure_summary(output: str) -> tuple[str, str]:
    lowered = output.lower()

    if "permission denied" in lowered or "failed to open render node" in lowered:
        return (
            "VA-API cannot access the GPU render device.",
            "Confirm your user has render/video device access, then sign out and back in.",
        )

    if "radeonsi_drv_video.so" in lowered and (
        "resource allocation failed" in lowered
        or "init failed" in lowered
        or "va_openDriver() returns 2" in output
    ):
        return (
            "AMD VA-API driver was found but could not initialize.",
            "Reboot after Mesa/GPU driver updates; if it persists, verify mesa-dri-drivers provides mesa-va-drivers and check Graphics for amdgpu status.",
        )

    if "failed to open" in lowered or "driver_name" in lowered or "va_openDriver" in output:
        return (
            "VA-API driver could not be opened.",
            "Verify the matching VA-API driver package is installed for this GPU and no stale LIBVA_DRIVER_NAME override is set.",
        )

    return (
        "VA-API initialisation failed.",
        "Confirm your GPU driver is loaded (see Graphics).",
    )


def _mesa_vaapi_failure_context() -> tuple[str, str]:
    rpm = _run_command([
        "rpm",
        "-q",
        "--queryformat",
        "%{NAME} %{VERSION}-%{RELEASE}.%{ARCH}\n%{VENDOR}\n%{PACKAGER}\n",
        "mesa-dri-drivers",
        "mesa-vulkan-drivers",
        "libva",
    ], timeout=5)
    if rpm is None or rpm.returncode != 0:
        return "", ""

    details = rpm.stdout.strip()
    lowered = details.lower()
    if "negativo17" in lowered or "fedora-multimedia" in lowered:
        return (
            details,
            "Mesa/libva is installed from negativo17's fedora-multimedia repo; distro-sync the Mesa stack back to Fedora/RPM Fusion packages, then reboot.",
        )

    if "xxmitsu" in lowered or "copr" in lowered:
        return (
            details,
            "Mesa is installed from the mesa-git COPR; switch back to stable Fedora Mesa or wait for a fixed mesa-git snapshot.",
        )

    return details, ""


def _compact_vaapi_failure_details(primary_output: str, direct_probe_details: list[str]) -> str:
    attempts = [("$ vainfo", primary_output.strip())]
    for detail in direct_probe_details:
        command, _, probe_output = detail.partition("\n")
        attempts.append((command.strip(), probe_output.strip()))

    attempt_lines = []
    drivers = []
    errors = []
    for command, probe_output in attempts:
        if not probe_output:
            continue
        display_match = re.search(r"Trying display:\s*([^\n]+)", probe_output)
        display = display_match.group(1).strip() if display_match else "default display"
        attempt_lines.append(f"{command}: {display}")

        for driver in re.findall(r"Trying to open\s+([^\s]+)", probe_output):
            if driver not in drivers:
                drivers.append(driver)

        for line in probe_output.splitlines():
            normalized = line.strip()
            lowered = normalized.lower()
            if (
                "error:" in lowered
                or "failed with error code" in lowered
                or "va_opendriver()" in lowered
            ) and normalized not in errors:
                errors.append(normalized)

    lines = []
    if attempt_lines:
        lines.append("Probe attempts:")
        lines.extend(f"- {attempt}" for attempt in attempt_lines)
    if drivers:
        lines.extend(["", "VA-API driver:"])
        lines.extend(f"- {driver}" for driver in drivers)
    if errors:
        lines.extend(["", "Failure reported:"])
        lines.extend(f"- {error}" for error in errors[:5])

    if not lines:
        return primary_output.strip()
    return "\n".join(lines)


def _vaapi_profiles(output: str) -> list[str]:
    lowered = output.lower()
    profiles = []
    if "h264" in lowered or "avc" in lowered:
        profiles.append("H.264")
    if "h265" in lowered or "hevc" in lowered:
        profiles.append("H.265")
    if "av1" in lowered:
        profiles.append("AV1")
    if "vp9" in lowered:
        profiles.append("VP9")
    if "vp8" in lowered:
        profiles.append("VP8")
    return profiles


def _successful_vaapi_probe(vainfo: subprocess.CompletedProcess[str] | None) -> tuple[list[str], str] | None:
    if vainfo is None:
        return None
    output = (vainfo.stdout + vainfo.stderr).strip()
    if vainfo.returncode != 0:
        return None
    profiles = _vaapi_profiles(output)
    if not profiles:
        return None
    return profiles, output


def _codec_probe() -> HardwareProbe:
    sw_driver = (
        os.environ.get("MESA_LOADER_DRIVER_OVERRIDE", "")
        or os.environ.get("GALLIUM_DRIVER", "")
    )
    if "llvmpipe" in sw_driver.lower():
        env_lines = "\n".join(
            f"{k}={os.environ[k]}"
            for k in ("MESA_LOADER_DRIVER_OVERRIDE", "GALLIUM_DRIVER", "LIBGL_ALWAYS_SOFTWARE")
            if k in os.environ
        )
        skel_file = os.path.expanduser("~/.config/plasma-workspace/env/10-kyth-qemu-safe.sh")
        source = skel_file if os.path.exists(skel_file) else "~/.config/plasma-workspace/env/"
        return HardwareProbe(
            "Video Decode", "warn",
            "Software rendering is active in this session — VA-API requires hardware GPU access.",
            f"{env_lines}\n\nSet by {source} (QEMU compatibility fallback active on bare metal).",
            f"Delete {skel_file} and log out/in to restore hardware rendering.",
        )

    vainfo = _run_command(["vainfo"], timeout=10)
    if vainfo is None:
        return HardwareProbe(
            "Video Decode", "dim",
            "vainfo not available — cannot check VA-API support.",
            "Install libva-utils to inspect hardware video decode capabilities.",
        )

    direct_probe_details = []
    successful = _successful_vaapi_probe(vainfo)
    if successful is None:
        render_nodes = sorted(glob.glob("/dev/dri/renderD*"))
        for node in render_nodes:
            drm_vainfo = _run_command(["vainfo", "--display", "drm", "--device", node], timeout=10)
            if drm_vainfo is not None:
                direct_probe_details.append(
                    f"$ vainfo --display drm --device {node}\n"
                    f"{(drm_vainfo.stdout + drm_vainfo.stderr).strip()}"
                )
            successful = _successful_vaapi_probe(drm_vainfo)
            if successful is not None:
                profiles, drm_output = successful
                details = [
                    "$ vainfo",
                    (vainfo.stdout + vainfo.stderr).strip(),
                    f"$ vainfo --display drm --device {node}",
                    drm_output,
                ]
                return HardwareProbe(
                    "Video Decode", "ok",
                    f"VA-API hardware decode: {', '.join(profiles)}.",
                    "\n\n".join(part for part in details if part),
                )
    else:
        profiles, output = successful
        return HardwareProbe(
            "Video Decode", "ok",
            f"VA-API hardware decode: {', '.join(profiles)}.",
            output,
        )

    output = (vainfo.stdout + vainfo.stderr)
    if vainfo.returncode != 0 and "failed" in output.lower():
        summary, recommendation = _vaapi_failure_summary(output)
        details = _compact_vaapi_failure_details(output, direct_probe_details)
        mesa_details, mesa_recommendation = _mesa_vaapi_failure_context()
        if mesa_details:
            details = f"{details}\n\nMesa package:\n{mesa_details}"
        if mesa_recommendation:
            recommendation = mesa_recommendation
        return HardwareProbe(
            "Video Decode", "warn",
            summary,
            details,
            recommendation,
        )

    profiles = _vaapi_profiles(output)
    if not profiles:
        return HardwareProbe(
            "Video Decode", "warn",
            "VA-API is available but no recognised decode profiles were found.",
            (vainfo.stdout + vainfo.stderr).strip(),
        )

    return HardwareProbe(
        "Video Decode", "ok",
        f"VA-API hardware decode: {', '.join(profiles)}.",
        (vainfo.stdout + vainfo.stderr).strip(),
    )


def _collect_hardware_probes() -> list[HardwareProbe]:
    pci_text  = _command_stdout(["lspci"],  timeout=5)
    usb_text  = _command_stdout(["lsusb"],  timeout=5)
    lsmod_text = _command_stdout(["lsmod"], timeout=5)
    return [
        # Gaming-critical first
        _gpu_probe(pci_text, lsmod_text),
        _cpu_probe(),
        _display_probe(),
        _memory_probe(),
        # Input devices
        _controller_probe(usb_text, lsmod_text),
        _peripheral_probe(usb_text),
        _displaylink_probe(usb_text, lsmod_text),
        # System health
        _audio_probe(),
        _thermal_probe(),
        _connectivity_probe(pci_text, usb_text),
        _codec_probe(),
        _firmware_probe(),
        _storage_probe(),
        _platform_probe(),
        _system_hub_probe(),
    ]


def _diagnostics_report(probes: list[HardwareProbe]) -> str:
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    kernel = _command_stdout(["uname", "-r"], timeout=5) or "unknown"
    hostname = _command_stdout(["hostnamectl", "--static"], timeout=5) or _command_stdout(["hostname"], timeout=5) or "unknown"
    branch = _branch_display_name(_current_branch())
    staged = "yes" if _has_staged_update() else "no"
    rollback = "yes" if _has_rollback_deployment() else "no"
    fwupd = _run_command(["fwupdmgr", "get-updates"], timeout=20)
    if fwupd is None:
        fwupd_status = "fwupd unavailable"
    elif fwupd.returncode == 0:
        fwupd_status = "updates available"
    elif fwupd.returncode == 2:
        fwupd_status = "up to date"
    else:
        fwupd_status = f"check failed (exit {fwupd.returncode})"

    lines = [
        "KythOS Diagnostics Report",
        f"Generated: {timestamp}",
        "",
        "System",
        f"  Hostname:          {hostname}",
        f"  Kernel:            {kernel}",
        f"  Branch:            {branch}",
        f"  Update staged:     {staged}",
        f"  Rollback available:{rollback}",
        f"  Firmware state:    {fwupd_status}",
        "",
        "Checks",
    ]
    for probe in probes:
        lines.append(f"  {probe.title}: [{probe.status.upper()}] {probe.summary}")
        if probe.action:
            lines.append(f"    Action: {probe.action}")
    lines += ["", "Details"]
    for probe in probes:
        lines.append(f"[{probe.title}]")
        lines.append(probe.details.strip() or "No extra details.")
        if probe.action:
            lines.append(f"Suggested action: {probe.action}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _health_command_report() -> str:
    checks: list[tuple[str, list[str], int]] = [
        ("Daily-driver smoke check", ["/usr/bin/kyth-smoke-check", "--verbose"], 90),
        ("Post-update confidence", ["/usr/bin/kyth-post-update-check", "--force", "--no-notify"], 45),
        ("NVIDIA status", ["/usr/bin/kyth-nvidia-status"], 30),
        ("Controller readiness", ["/usr/bin/kyth-controller-check"], 30),
        ("Suspend/resume readiness", ["/usr/bin/kyth-resume-check"], 45),
        ("Raw support snapshot", ["/usr/bin/kyth-device-info"], 60),
    ]

    sections = ["", "KythOS Health Command Output", "==========================", ""]
    env = os.environ.copy()
    env.setdefault("SUDO_ASKPASS", "/usr/bin/ksshaskpass")
    for title, cmd, timeout in checks:
        sections.append(f"== {title} ==")
        exe = cmd[0]
        if not os.path.exists(exe) and shutil.which(exe) is None:
            sections.extend([f"missing: {exe}", ""])
            continue
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            output = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
            sections.append(f"command: {' '.join(shlex.quote(part) for part in cmd)}")
            sections.append(f"exit: {r.returncode}")
            if output:
                sections.append(output)
            if err:
                sections.append("")
                sections.append("stderr:")
                sections.append(err)
        except subprocess.TimeoutExpired:
            sections.append(f"timed out after {timeout}s")
        except Exception as exc:
            sections.append(f"failed to run: {exc}")
        sections.append("")
    return "\n".join(sections)


def _health_recommendations(report: str) -> str:
    checks: list[tuple[str, str]] = [
        ("kyth-default-flatpaks.service", "Default game apps are incomplete. Open Repair and click Retry Game Apps."),
        ("Vulkan", "Vulkan reported trouble. Open Hardware and check Graphics; reboot if a GPU driver was just updated."),
        ("PipeWire", "Desktop audio is not fully active. Open Repair and click Restart Audio."),
        ("WirePlumber", "Audio session management is not fully active. Open Repair and click Restart Audio."),
        ("Rollback deployment not visible", "Rollback is not visible yet. Run one OS update, reboot, then verify the previous deployment appears."),
        ("NVIDIA setup has failures", "NVIDIA setup needs attention. Open NVIDIA Drivers or Repair and retry the NVIDIA build."),
        ("NVIDIA setup needs attention", "NVIDIA may need a reboot or driver build. Open NVIDIA Drivers for the exact state."),
        ("Controller readiness has warnings", "Controller support is partially unverified. Open Controllers, pair or plug in a gamepad, then run ujust controller-check."),
        ("resume readiness has warnings", "Suspend/resume has warnings. Test Wi-Fi, Bluetooth, audio, display, and Vulkan after waking."),
        ("not daily-driver ready", "Daily-driver smoke check found a blocker. Review the FAIL lines below first."),
        ("PC drives", "A PC drive needs care. Use Move Files and fully shut down the other system before copying files."),
    ]
    recs: list[str] = []
    lower_report = report.lower()
    for needle, message in checks:
        if needle.lower() in lower_report and message not in recs:
            recs.append(message)

    if not recs:
        return ""

    lines = ["", "Recommended Fixes", "=================", ""]
    lines.extend(f"- {rec}" for rec in recs[:8])
    lines.append("")
    return "\n".join(lines)


def _remove_autostart():
    path = os.path.expanduser("~/.config/autostart/kyth-welcome.desktop")
    try:
        os.remove(path)
    except OSError:
        pass


def _is_first_run() -> bool:
    return not os.path.exists(_WIZARD_SENTINEL)


def _mark_wizard_done():
    try:
        os.makedirs(os.path.dirname(_WIZARD_SENTINEL), exist_ok=True)
        open(_WIZARD_SENTINEL, "w").close()
    except OSError:
        pass


# ── Usage profile (everyday / gaming) ─────────────────────────────────────────
# Chosen on the first-run wizard's welcome step; drives which app defaults the
# wizard pre-selects and which System Hub sections get the most prominence.
# Older installs used work/both; both are treated as the Everyday preset.
_PROFILE_PATH = os.path.expanduser("~/.local/share/kyth/profile")
_VALID_PROFILES = ("everyday", "gaming")
_PROFILE_ALIASES = {"work": "everyday", "both": "everyday"}


def _normalize_profile(profile: str) -> str:
    value = profile.strip().lower()
    value = _PROFILE_ALIASES.get(value, value)
    return value if value in _VALID_PROFILES else "everyday"


def _load_profile() -> str:
    try:
        with open(_PROFILE_PATH, encoding="utf-8") as fh:
            return _normalize_profile(fh.read())
    except OSError:
        return "everyday"


def _save_profile(profile: str) -> None:
    profile = _normalize_profile(profile)
    try:
        os.makedirs(os.path.dirname(_PROFILE_PATH), exist_ok=True)
        with open(_PROFILE_PATH, "w", encoding="utf-8") as fh:
            fh.write(profile + "\n")
    except OSError:
        pass


def _wait_for_display_setup(timeout: float = 8.0, interval: float = 0.25):
    autostart = os.path.expanduser("~/.config/autostart/kyth-set-resolution.desktop")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _run_command(["pgrep", "-af", "kyth-set-resolution"], timeout=2)
        running = bool(result is not None and result.returncode == 0 and result.stdout.strip())
        pending = os.path.exists(autostart)
        if not running and not pending:
            return
        time.sleep(interval)


# ── UI utilities ───────────────────────────────────────────────────────────────

def _restyle(widget: QWidget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)

# ── NTFS / Steam migration helpers ───────────────────────────────────────────

def _find_ntfs_drives() -> list[dict]:
    """Return other system NTFS and locked BitLocker partitions visible to lsblk."""
    try:
        r = subprocess.run(
            ["lsblk", "--json", "--output", "NAME,FSTYPE,SIZE,LABEL,MOUNTPOINT,PATH"],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(r.stdout)
    except Exception:
        return []

    results: list[dict] = []

    def _walk(devices: list):
        for dev in devices:
            if not isinstance(dev, dict):
                continue
            fstype = (dev.get("fstype") or "").lower()
            if fstype in ("ntfs", "ntfs3", "bitlocker"):
                name = dev.get("name") or ""
                path = dev.get("path") or (f"/dev/{name}" if name else "")
                if not path:
                    continue
                results.append({
                    "dev":   path,
                    "name":  name,
                    "size":  dev.get("size", "?"),
                    "label": dev.get("label") or "",
                    "mount": dev.get("mountpoint") or "",
                    "is_bitlocker": fstype == "bitlocker",
                })
            _walk(dev.get("children") or [])

    _walk(data.get("blockdevices", []))
    return results


def _find_steam_libraries(mount_point: str) -> list[str]:
    """Scan a mounted NTFS drive for steamapps directories."""
    found: list[str] = []
    # Known other system Steam install locations
    candidates = [
        os.path.join(mount_point, "Program Files (x86)", "Steam", "steamapps"),
        os.path.join(mount_point, "Program Files", "Steam", "steamapps"),
        os.path.join(mount_point, "SteamLibrary", "steamapps"),
        os.path.join(mount_point, "Steam", "steamapps"),
        os.path.join(mount_point, "Games", "Steam", "steamapps"),
        os.path.join(mount_point, "Games", "SteamLibrary", "steamapps"),
    ]
    for path in candidates:
        if os.path.isdir(path):
            found.append(path)
    # Shallow scan: check one level of subdirs for SteamLibrary/steamapps patterns
    try:
        for entry in os.scandir(mount_point):
            if not entry.is_dir(follow_symlinks=False):
                continue
            for sub in (
                os.path.join(entry.path, "steamapps"),
                os.path.join(entry.path, "SteamLibrary", "steamapps"),
            ):
                if os.path.isdir(sub) and sub not in found:
                    found.append(sub)
    except (PermissionError, OSError):
        pass
    return found


# Steam tooling entries that show up in appmanifests but are not games.
_STEAM_NON_GAME_PATTERNS = (
    "steamworks common redistributables",
    "steam linux runtime",
    "proton",
    "steamvr",
)


def _scan_steamapps_manifests(steamapps_dir: str) -> list[dict]:
    """List games recorded in a steamapps directory (works on read-only NTFS mounts)."""
    games: list[dict] = []
    seen: set[str] = set()
    for manifest in glob.glob(os.path.join(steamapps_dir, "appmanifest_*.acf")):
        data = _parse_steam_acf(manifest)
        name = data.get("name", "").strip()
        appid = data.get("appid", "").strip()
        if not name or (appid or name.lower()) in seen:
            continue
        lowered = name.lower()
        if any(lowered.startswith(pat) for pat in _STEAM_NON_GAME_PATTERNS):
            continue
        seen.add(appid or lowered)
        games.append({"name": name, "appid": appid})
    games.sort(key=lambda item: item["name"].lower())
    return games

# ── Page: Controllers ─────────────────────────────────────────────────────────

def _detect_controllers() -> dict:
    """Snapshot of all connected controllers and driver state. Thread-safe."""
    usb_text = _command_stdout(["lsusb"], timeout=6)
    lsmod_text = _command_stdout(["lsmod"], timeout=4)

    _GAMING_VIDS: dict[str, str] = {
        "045e": "Xbox", "054c": "PlayStation", "057e": "Nintendo",
        "2dc8": "8BitDo", "0f0d": "HORI", "28de": "Valve",
        "20d6": "PowerA", "0e6f": "PDP",
    }
    _XONE_DONGLE_PIDS = {"02e6", "02fe"}
    _DUALSENSE_PIDS   = {"0ce6", "0df2"}
    _DS4_PIDS         = {"05c4", "09cc", "0ba0"}
    _SWITCH_PRO_PID   = "2009"

    usb_controllers: list[tuple[str, str]] = []   # (display_name, type_key)
    xone_dongle = False
    dualsense_found = False
    ds4_found = False
    switch_pro_found = False

    for line in usb_text.splitlines():
        m = re.search(r"ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)", line)
        if not m:
            continue
        vid, pid, desc = m.group(1).lower(), m.group(2).lower(), m.group(3).strip()
        if vid not in _GAMING_VIDS:
            continue
        if vid == "045e" and pid in _XONE_DONGLE_PIDS:
            xone_dongle = True
            usb_controllers.append(("Xbox Wireless USB Dongle", "xbox_dongle"))
        elif vid == "054c" and pid in _DUALSENSE_PIDS:
            dualsense_found = True
            usb_controllers.append(("PlayStation 5 DualSense", "dualsense"))
        elif vid == "054c" and pid in _DS4_PIDS:
            ds4_found = True
            usb_controllers.append(("PlayStation 4 DualShock 4", "ds4"))
        elif vid == "057e" and pid == _SWITCH_PRO_PID:
            switch_pro_found = True
            usb_controllers.append(("Nintendo Switch Pro Controller", "switch_pro"))
        else:
            usb_controllers.append((desc or f"{_GAMING_VIDS[vid]} controller", "generic"))

    input_nodes: list[str] = []
    try:
        for name in sorted(os.listdir("/dev/input/by-id")):
            if any(t in name.lower() for t in ("joystick", "gamepad", "controller")):
                input_nodes.append(name)
    except OSError:
        pass

    lsmod_norm = lsmod_text.lower().replace("-", "_")

    dualsensectl_out = ""
    if dualsense_found and shutil.which("dualsensectl"):
        dualsensectl_out = _command_stdout(["dualsensectl", "status", "0"], timeout=3)

    # Secure Boot state
    secure_boot = False
    try:
        for ef in os.listdir("/sys/firmware/efi/efivars"):
            if ef.startswith("SecureBoot-"):
                data = open(f"/sys/firmware/efi/efivars/{ef}", "rb").read()
                secure_boot = len(data) >= 5 and data[4] == 1
                break
    except OSError:
        pass

    return {
        "usb_controllers":  usb_controllers,
        "input_nodes":      input_nodes,
        "xone_dongle":      xone_dongle,
        "xone_loaded":      "xone_hid"       in lsmod_norm,
        "xpadneo_loaded":   "xpadneo"        in lsmod_norm,
        "hid_ps_loaded":    "hid_playstation" in lsmod_norm,
        "dualsense_found":  dualsense_found,
        "ds4_found":        ds4_found,
        "switch_pro_found": switch_pro_found,
        "dualsensectl_out": dualsensectl_out,
        "secure_boot":      secure_boot,
        "jstest_available": bool(shutil.which("jstest-gtk")),
    }
