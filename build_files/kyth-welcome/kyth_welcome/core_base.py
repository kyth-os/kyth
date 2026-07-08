import atexit
import glob
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


