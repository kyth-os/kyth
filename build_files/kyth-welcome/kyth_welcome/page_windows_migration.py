import glob
import html
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

# __KYTH_GENERATED_IMPORTS__
from .core_base import (
    _human_bytes, _release_worker_when_finished, _restyle,
)
from .services.diagnostics import (
    _command_stdout, _run_command,
)
from .services.gaming import (
    DataWorker, TrackedThread,
)
from .services.software import (
    Worker, _finish_worker, _install_flatpak_inline, _is_flatpak_installed,
)
from .page_feedback import (  # noqa: E501
    _probe_windows_partitions,
)
from .qt import (  # noqa: E501
    QCheckBox, QComboBox, QDesktopServices, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QProgressBar, QPushButton, QThread, QTimer, QUrl, QVBoxLayout, Signal,
)
from .widgets import (  # noqa: E501
    Page, _make_card, _make_flow_step,
)

def _unlock_bitlocker_drive(dev: str, key: str) -> tuple[bool, str]:
    """Unlock a BitLocker partition via udisks and mount the cleartext device.

    cryptsetup's bitlk backend accepts either the user password or the 48-digit
    recovery key as the passphrase. Runs on a worker thread (polkit may prompt).
    """
    try:
        r = subprocess.run(
            ["udisksctl", "unlock", "-b", dev, "--key-file", "/dev/stdin"],
            input=key, capture_output=True, text=True, timeout=180,
        )
    except Exception as exc:
        return False, str(exc)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip() or "Unlock failed."
    # udisksctl prints: "Unlocked /dev/sda3 as /dev/dm-3."
    m = re.search(r"\bas (/dev/\S+?)\.?\s*$", r.stdout.strip())
    if not m:
        return True, "Unlocked — rescan to mount the drive."
    try:
        rm = subprocess.run(
            ["udisksctl", "mount", "-b", m.group(1)],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as exc:
        return False, str(exc)
    if rm.returncode != 0:
        return False, (rm.stderr or rm.stdout).strip() or "Mount failed."
    return True, rm.stdout.strip()


class WindowsLibraryWorker(TrackedThread):
    result = Signal(list)

    def run(self) -> None:
        try:
            partitions = _probe_windows_partitions()
        except Exception as exc:
            print(f"game library probe failed: {exc}", file=sys.stderr)
            partitions = []
        self.result.emit(partitions)


# ── Copy My Files ─────────────────────────────────────────────────────────────
# The source system stores profile folders under their English names on disk regardless
# of display language, so these source names are locale-safe. Destinations go
# through xdg-user-dir so localized Linux home folders are honoured.
_XDG_FOLDER_KEYS = {
    "Desktop": "DESKTOP",
    "Documents": "DOCUMENTS",
    "Downloads": "DOWNLOAD",
    "Pictures": "PICTURES",
    "Music": "MUSIC",
    "Videos": "VIDEOS",
}


def _windows_folder_dest(folder: str) -> str:
    home = os.path.expanduser("~")
    if folder == "Saved Games":
        return os.path.join(_windows_folder_dest("Documents"), "Saved Games")
    key = _XDG_FOLDER_KEYS.get(folder)
    if key:
        path = _command_stdout(["xdg-user-dir", key], timeout=5)
        # xdg-user-dir answers $HOME itself for unset entries; don't copy there.
        if path and os.path.abspath(path) != home:
            return path
    return os.path.join(home, folder)


def _folder_sizes_calc(paths: dict[str, str]):
    def _calc() -> dict[str, int]:
        sizes: dict[str, int] = {}
        for name, path in paths.items():
            try:
                out = subprocess.check_output(
                    ["du", "-sb", path], text=True, timeout=600,
                    stderr=subprocess.DEVNULL,
                )
                sizes[name] = int(out.split()[0])
            except Exception:
                sizes[name] = -1
        return sizes
    return _calc


class UserFilesCopyWorker(TrackedThread):
    """Copies selected profile folders into the home directory via rsync."""
    BLOCKS_CLOSE = True
    status = Signal(str)
    overall = Signal(int)          # 0–100 across all folders
    done = Signal(int, int, bool)  # (ok, failed, cancelled)

    def __init__(self, jobs: list[tuple[str, str, str]]):
        super().__init__()
        self._jobs = jobs  # (folder name, src, dst)
        self._proc: subprocess.Popen | None = None
        self._stop = False

    def stop(self):
        self._stop = True
        proc = self._proc
        if proc and proc.poll() is None:
            proc.terminate()

    def run(self):
        ok = failed = 0
        total = len(self._jobs) or 1
        for idx, (name, src, dst) in enumerate(self._jobs):
            if self._stop:
                break
            self.status.emit(f"Copying {name}…")
            code = self._copy_one(idx, total, name, src, dst)
            if self._stop:
                break
            # 24 = source files vanished mid-copy; harmless for a one-way import.
            if code in (0, 24):
                ok += 1
            else:
                failed += 1
            self.overall.emit(int((idx + 1) * 100 / total))
        self.done.emit(ok, failed, self._stop)

    def _copy_one(self, idx: int, total: int, name: str, src: str, dst: str) -> int:
        try:
            os.makedirs(dst, exist_ok=True)
        except OSError:
            return 1
        # -rt without -p/-o/-g: NTFS carries no useful Unix permissions, so new
        # files get normal home-folder modes. --update never overwrites a file
        # that is already newer on the KythOS side.
        cmd = [
            "rsync", "-rt", "--update", "--info=progress2", "--no-inc-recursive",
            src.rstrip("/") + "/", dst.rstrip("/") + "/",
        ]
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except OSError:
            return 1
        # progress2 updates end with \r, not \n, so read raw chunks, not lines.
        fd = self._proc.stdout.fileno()
        tail = b""
        last_pct = -1
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            tail = (tail + chunk)[-256:]
            pcts = re.findall(rb"(\d+)%", tail)
            if pcts:
                pct = min(100, int(pcts[-1]))
                if pct != last_pct:
                    last_pct = pct
                    self.overall.emit(int((idx * 100 + pct) / total))
                    self.status.emit(f"Copying {name} — {pct}%")
        self._proc.wait()
        return self._proc.returncode


# ── Hardware sanity check ─────────────────────────────────────────────────────
# "Did everything come along?" — the things the previous setup configured silently.
# Every probe degrades to skipping its row when the tool is missing.

def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _hw_display_row() -> tuple[str, str, str] | None:
    out = _strip_ansi(_command_stdout(["kscreen-doctor", "-o"], timeout=10))
    if not out:
        return None
    hdr = [v.lower() for v in re.findall(r"HDR:\s*([A-Za-z]+)", out)]
    vrr = [v.lower() for v in re.findall(r"VRR:\s*([A-Za-z]+)", out)]
    bits: list[str] = []
    status = "ok"
    if "enabled" in hdr:
        bits.append("HDR is on")
    elif "disabled" in hdr:
        bits.append("your display supports HDR but it's off — enable it in System Settings → Display & Monitor")
        status = "warn"
    elif hdr:
        bits.append("no HDR support advertised by the display")
    if any(v in ("automatic", "always") for v in vrr):
        bits.append("variable refresh rate (FreeSync/G-Sync) is active")
    elif "never" in vrr:
        bits.append("the display supports VRR but it's set to Never — switch it to Automatic for smoother gaming")
        status = "warn"
    elif vrr:
        bits.append("no variable refresh rate support")
    if not bits:
        return None
    joined = "; ".join(bits)
    text = joined[0].upper() + joined[1:] + "."
    if status == "ok" and not any(v == "enabled" for v in hdr) and not any(v in ("automatic", "always") for v in vrr):
        status = "dim"
    return (status, "Display", text)


def _collect_hw_sanity() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []

    state = _command_stdout(["nmcli", "-t", "-f", "STATE", "general"], timeout=5)
    if state:
        if state.startswith("connected"):
            rows.append(("ok", "Network", "Connected to the internet."))
        else:
            rows.append(("warn", "Network", "Not connected — click the network icon in the system tray to join your Wi-Fi."))

    display = _hw_display_row()
    if display:
        rows.append(display)

    lp = _run_command(["lpstat", "-p"], timeout=8)
    if lp is not None:
        printers = [ln for ln in lp.stdout.splitlines() if ln.startswith("printer")]
        if printers:
            rows.append(("ok", "Printer", f"{len(printers)} printer{'s' if len(printers) != 1 else ''} configured and ready."))
        else:
            rows.append(("warn", "Printer", "No printers set up yet. Plug one in (or have a network printer on), then run Set Up Printer."))

    rf = _command_stdout(["rfkill", "list", "bluetooth"], timeout=5)
    if rf.strip():
        if "soft blocked: yes" in rf.lower() or "hard blocked: yes" in rf.lower():
            rows.append(("warn", "Bluetooth", "Bluetooth is turned off (blocked). Enable it from the system tray or System Settings."))
        else:
            rows.append(("ok", "Bluetooth", "Bluetooth adapter is on. Pair devices from the system tray."))

    if glob.glob("/sys/class/power_supply/BAT*"):
        prof = _command_stdout(["powerprofilesctl", "get"], timeout=5)
        if prof:
            rows.append(("ok", "Power", f"Laptop power profile: {prof}. Switch profiles from the battery icon in the tray."))

    return rows


# ── Browser bookmark import ───────────────────────────────────────────────────
_CHROMIUM_BOOKMARK_STORES = (
    ("Chrome", "AppData/Local/Google/Chrome/User Data"),
    ("Edge", "AppData/Local/Microsoft/Edge/User Data"),
    ("Brave", "AppData/Local/BraveSoftware/Brave-Browser/User Data"),
    ("Vivaldi", "AppData/Local/Vivaldi/User Data"),
)
# Opera keeps its Bookmarks file directly in the profile dir, no "User Data" level.
_OPERA_BOOKMARK_DIR = "AppData/Roaming/Opera Software/Opera Stable"


def _read_chromium_bookmarks(path: str) -> list[tuple[str, str]]:
    """(title, url) pairs from a Chromium-format Bookmarks JSON file."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _walk(node):
        if not isinstance(node, dict):
            return
        if node.get("type") == "url":
            url = node.get("url", "")
            if url.startswith(("http://", "https://")) and url not in seen:
                seen.add(url)
                out.append((node.get("name", "") or url, url))
        for child in node.get("children") or []:
            _walk(child)

    for root in (data.get("roots") or {}).values():
        _walk(root)
    return out


def _read_firefox_bookmarks(places_path: str) -> list[tuple[str, str]]:
    """(title, url) pairs from a Firefox places.sqlite (read via a temp copy)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    try:
        shutil.copyfile(places_path, tmp.name)
        con = sqlite3.connect(tmp.name)
        try:
            rows = con.execute(
                "SELECT b.title, p.url FROM moz_bookmarks b"
                " JOIN moz_places p ON b.fk = p.id WHERE b.type = 1"
            ).fetchall()
        finally:
            con.close()
    finally:
        os.unlink(tmp.name)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for title, url in rows:
        if url and url.startswith(("http://", "https://")) and url not in seen:
            seen.add(url)
            out.append((title or url, url))
    return out


def _scan_windows_bookmarks(profiles: list[dict]) -> list[dict]:
    """Find bookmark stores in Windows user profiles. Runs on a worker thread."""
    sources: list[dict] = []
    for prof in profiles:
        base, user = prof.get("path", ""), prof.get("name", "")
        candidates: list[tuple[str, str]] = []
        for browser, rel in _CHROMIUM_BOOKMARK_STORES:
            for found in glob.glob(os.path.join(base, rel, "*", "Bookmarks")):
                candidates.append((browser, found))
        opera = os.path.join(base, _OPERA_BOOKMARK_DIR, "Bookmarks")
        if os.path.isfile(opera):
            candidates.append(("Opera", opera))
        for browser, path in candidates:
            try:
                entries = _read_chromium_bookmarks(path)
            except Exception:
                continue
            if not entries:
                continue
            prof_dir = os.path.basename(os.path.dirname(path))
            label = browser if prof_dir in ("Default", "Opera Stable") else f"{browser} ({prof_dir})"
            sources.append({"browser": label, "user": user, "entries": entries})
        for places in glob.glob(os.path.join(base, "AppData/Roaming/Mozilla/Firefox/Profiles", "*", "places.sqlite")):
            try:
                entries = _read_firefox_bookmarks(places)
            except Exception:
                continue
            if entries:
                sources.append({"browser": "Firefox", "user": user, "entries": entries})
    return sources


def _write_bookmarks_html(sources: list[dict], dest: str) -> int:
    """Write a Netscape bookmarks HTML file that every browser's importer accepts."""
    parts = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>\n",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">\n',
        "<TITLE>Bookmarks</TITLE>\n",
        "<H1>Bookmarks from another system</H1>\n",
        "<DL><p>\n",
    ]
    total = 0
    for src in sources:
        parts.append(f"  <DT><H3>{html.escape(src['browser'])} — {html.escape(src['user'])}</H3>\n  <DL><p>\n")
        for title, url in src["entries"]:
            parts.append(f'    <DT><A HREF="{html.escape(url, quote=True)}">{html.escape(title)}</A>\n')
            total += 1
        parts.append("  </DL><p>\n")
    parts.append("</DL><p>\n")
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write("".join(parts))
    return total


_DYNAMIC_LOCK_CONFIG = os.path.expanduser("~/.config/kyth-dynamic-lock.json")


def _load_dynamic_lock_config() -> dict:
    try:
        with open(_DYNAMIC_LOCK_CONFIG, "r", encoding="utf-8") as fh:
            config = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return config if isinstance(config, dict) else {}


def _save_dynamic_lock_config(config: dict) -> None:
    directory = os.path.dirname(_DYNAMIC_LOCK_CONFIG)
    os.makedirs(directory, exist_ok=True)
    temp_path = f"{_DYNAMIC_LOCK_CONFIG}.tmp"
    with open(temp_path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)
        fh.write("\n")
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, _DYNAMIC_LOCK_CONFIG)


def _kdeconnect_devices() -> list[dict]:
    if shutil.which("kdeconnect-cli") is None:
        return []
    _run_command(["kdeconnect-cli", "--refresh"], timeout=8)
    all_result = _run_command(
        ["kdeconnect-cli", "--list-devices", "--id-name-only"], timeout=12,
    )
    available_result = _run_command(
        ["kdeconnect-cli", "--list-available", "--id-only"], timeout=12,
    )
    if all_result is None or all_result.returncode != 0:
        return []
    available = set()
    if available_result is not None and available_result.returncode == 0:
        available = {
            line.strip() for line in available_result.stdout.splitlines() if line.strip()
        }
    devices = []
    for row in all_result.stdout.splitlines():
        parts = row.strip().split(maxsplit=1)
        if not parts:
            continue
        device_id = parts[0]
        devices.append({
            "id": device_id,
            "name": parts[1] if len(parts) > 1 else device_id,
            "reachable": device_id in available,
        })
    return sorted(devices, key=lambda item: item["name"].lower())


def _run_kdeconnect_action(device_id: str, action: str) -> tuple[bool, str]:
    result = _run_command(
        ["kdeconnect-cli", "--device", device_id, action], timeout=20,
    )
    if result is None:
        return False, "KDE Connect did not respond."
    detail = (result.stdout or result.stderr).strip()
    return result.returncode == 0, detail


def _mount_kdeconnect_device(device_id: str) -> tuple[bool, str]:
    mounted, detail = _run_kdeconnect_action(device_id, "--mount")
    if not mounted:
        return False, detail
    result = _run_command(
        ["kdeconnect-cli", "--device", device_id, "--get-mount-point"], timeout=12,
    )
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return False, "The device connected, but its file location was not reported."
    return True, result.stdout.strip()


def _send_kdeconnect_sms(
    device_id: str, destination: str, message: str,
) -> tuple[bool, str]:
    result = _run_command([
        "kdeconnect-cli", "--device", device_id,
        "--send-sms", message, "--destination", destination,
    ], timeout=30)
    if result is None:
        return False, "KDE Connect did not respond."
    detail = (result.stdout or result.stderr).strip()
    return result.returncode == 0, detail


def _configure_dynamic_lock_service(enabled: bool) -> tuple[bool, str]:
    helper = "/usr/bin/kyth-dynamic-lock"
    unit = "/usr/lib/systemd/user/kyth-dynamic-lock.service"
    if not os.path.exists(helper) or not os.path.exists(unit):
        return False, "Dynamic Lock will be available after the next KythOS update and restart."
    _run_command(["systemctl", "--user", "daemon-reload"], timeout=20)
    action = "enable" if enabled else "disable"
    result = _run_command(
        ["systemctl", "--user", action, "--now", "kyth-dynamic-lock.service"],
        timeout=30,
    )
    if result is None or result.returncode != 0:
        detail = "" if result is None else (result.stderr or result.stdout).strip()
        return False, detail or "Could not update the Dynamic Lock service."
    return True, "Dynamic Lock is on." if enabled else "Dynamic Lock is off."


# ── PC drive extras: wallpaper, fonts, game saves, notes, RDP ───────────
# Everything here reads from the mounted system partitions found by
# _probe_windows_partitions and never writes to them.

_FONT_EXTS = (".ttf", ".ttc", ".otf")

# AppData top-level folders that are launcher caches, browser profiles, or OS
# plumbing — never game saves. Lowercased exact matches.
_APPDATA_SKIP = {
    "adobe", "amd", "battle.net", "blizzard entertainment", "brave",
    "bravesoftware", "cache", "comms", "connecteddevicesplatform",
    "crashdumps", "d3dscache", "discord", "dropbox", "epicgameslauncher",
    "google", "gog.com", "intel", "microsoft", "mozilla", "ngc", "nvidia",
    "nvidia corporation", "onedrive", "opera software", "packages",
    "peernetworking", "programs", "publishers", "slack", "spotify",
    "squirreltemp", "steam", "temp", "ubisoft game launcher", "unity",
    "vivaldi", "zoom",
}
_SAVE_DIR_RE = re.compile(r"^(saves?|savegames?|savedata|saved games|save files)$", re.I)
_SAVE_FILE_RE = re.compile(r"\.(sav|save|sl2|sl3|ess|fos|rpgsave)$", re.I)


def _dir_contains_saves(root: str, max_entries: int = 1000, max_depth: int = 5) -> bool:
    """Bounded look for save-shaped content under root — a dir named like
    'Saves' or files with well-known save extensions."""
    stack = [(root, 0)]
    seen = 0
    while stack:
        path, depth = stack.pop()
        try:
            with os.scandir(path) as it:
                for entry in it:
                    seen += 1
                    if seen > max_entries:
                        return False
                    if entry.is_dir(follow_symlinks=False):
                        if _SAVE_DIR_RE.match(entry.name):
                            return True
                        if depth + 1 < max_depth:
                            stack.append((entry.path, depth + 1))
                    elif _SAVE_FILE_RE.search(entry.name):
                        return True
        except OSError:
            continue
    return False


def _scan_profile_game_saves(profile: dict) -> list[dict]:
    hits: list[dict] = []
    base = profile["path"]
    user = profile["name"]
    # Dedicated save roots: every subfolder is game data by definition.
    for rel in ("Documents/My Games", "Saved Games"):
        root = os.path.join(base, rel)
        try:
            entries = sorted(os.scandir(root), key=lambda e: e.name.lower())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                hits.append({
                    "user": user, "src": entry.path,
                    "label": os.path.join(os.path.basename(rel), entry.name),
                })
    # AppData: only folders that actually look like they hold saves.
    for rel in ("AppData/Local", "AppData/LocalLow", "AppData/Roaming"):
        root = os.path.join(base, rel)
        try:
            entries = sorted(os.scandir(root), key=lambda e: e.name.lower())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            if entry.name.lower() in _APPDATA_SKIP:
                continue
            if _dir_contains_saves(entry.path):
                hits.append({
                    "user": user, "src": entry.path,
                    "label": os.path.join(os.path.basename(rel), entry.name),
                })
    return hits


def _best_profile_wallpaper(profile_path: str) -> str:
    """Highest-resolution wallpaper file Windows cached for this profile."""
    themes = os.path.join(
        profile_path, "AppData", "Roaming", "Microsoft", "Windows", "Themes")
    candidates = glob.glob(os.path.join(themes, "CachedFiles", "*"))
    transcoded = os.path.join(themes, "TranscodedWallpaper")
    if os.path.isfile(transcoded):
        candidates.append(transcoded)
    best, best_size = "", 0
    for path in candidates:
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size > best_size:
            best, best_size = path, size
    return best


def _image_extension(path: str) -> str:
    """TranscodedWallpaper has no extension; sniff the magic bytes."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return ".jpg"
    if head.startswith(b"\x89PNG"):
        return ".png"
    if head.startswith(b"BM"):
        return ".bmp"
    return ".jpg"


def _read_sticky_notes(profile_path: str) -> list[str]:
    """Read note texts from the Sticky Notes app database (plum.sqlite).

    The database is copied to a temp dir first so sqlite's WAL replay never
    touches the (possibly read-only) PC drive."""
    src_dir = os.path.join(
        profile_path, "AppData", "Local", "Packages",
        "Microsoft.MicrosoftStickyNotes_8wekyb3d8bbwe", "LocalState")
    db = os.path.join(src_dir, "plum.sqlite")
    if not os.path.isfile(db):
        return []
    notes: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="kyth-sticky-") as tmp:
            for suffix in ("", "-wal", "-shm"):
                src = db + suffix
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(tmp, "plum.sqlite" + suffix))
            conn = sqlite3.connect(os.path.join(tmp, "plum.sqlite"))
            try:
                rows = conn.execute("SELECT Text FROM Note").fetchall()
            finally:
                conn.close()
        for (text,) in rows:
            if not text:
                continue
            # Sticky Notes embeds per-paragraph "\id=<guid>" markers.
            clean = re.sub(r"\\id=[0-9a-fA-F-]{36}\s?", "", str(text)).strip()
            if clean:
                notes.append(clean)
    except Exception:
        return []
    return notes


def _parse_rdp_file(path: str) -> dict | None:
    """Pull host and username out of a Windows .rdp file (usually UTF-16)."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(65536)
    except OSError:
        return None
    if raw.startswith(b"\xff\xfe"):
        text = raw.decode("utf-16", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
    host = username = ""
    for line in text.splitlines():
        if line.lower().startswith("full address:s:"):
            host = line.split(":s:", 1)[1].strip()
        elif line.lower().startswith("username:s:"):
            username = line.split(":s:", 1)[1].strip()
    if not host:
        return None
    return {
        "name": os.path.splitext(os.path.basename(path))[0],
        "host": host,
        "username": username,
        "path": path,
    }


def _scan_windows_extras(partitions: list) -> dict:
    """One worker-thread pass over the mounted system partitions for the
    wallpaper / fonts / game-saves / sticky-notes / RDP cards."""
    wallpapers: list[dict] = []
    saves: list[dict] = []
    sticky: list[dict] = []
    rdp: list[dict] = []
    font_dirs: list[str] = []
    font_count = 0
    font_bytes = 0

    def _count_fonts(path: str) -> tuple[int, int]:
        count = size = 0
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_file() and entry.name.lower().endswith(_FONT_EXTS):
                        count += 1
                        try:
                            size += entry.stat().st_size
                        except OSError:
                            pass
        except OSError:
            pass
        return count, size

    for part in partitions:
        mount = part.get("mountpoint") or ""
        if mount:
            count, size = _count_fonts(os.path.join(mount, "Windows", "Fonts"))
            if count:
                font_dirs.append(os.path.join(mount, "Windows", "Fonts"))
                font_count += count
                font_bytes += size
            # Ubisoft Connect keeps saves outside the user profile.
            ubi = os.path.join(
                mount, "Program Files (x86)", "Ubisoft",
                "Ubisoft Game Launcher", "savegames")
            if os.path.isdir(ubi):
                saves.append({"user": "", "src": ubi, "label": "Ubisoft savegames"})
        for prof in part.get("user_profiles") or []:
            user = prof["name"]
            wp = _best_profile_wallpaper(prof["path"])
            if wp:
                wallpapers.append({"user": user, "path": wp})
            user_fonts = os.path.join(
                prof["path"], "AppData", "Local", "Microsoft", "Windows", "Fonts")
            count, size = _count_fonts(user_fonts)
            if count:
                font_dirs.append(user_fonts)
                font_count += count
                font_bytes += size
            saves.extend(_scan_profile_game_saves(prof))
            notes = _read_sticky_notes(prof["path"])
            if notes:
                sticky.append({"user": user, "notes": notes})
            for pattern in ("Desktop/*.rdp", "Desktop/*/*.rdp",
                            "Documents/*.rdp", "Documents/*/*.rdp",
                            "Downloads/*.rdp"):
                for path in glob.glob(os.path.join(prof["path"], pattern)):
                    parsed = _parse_rdp_file(path)
                    if parsed:
                        parsed["user"] = user
                        rdp.append(parsed)
    return {
        "wallpapers": wallpapers,
        "fonts": {"dirs": font_dirs, "count": font_count, "bytes": font_bytes},
        "saves": saves,
        "sticky": sticky,
        "rdp": rdp,
    }


def _copy_windows_fonts(font_dirs: list[str]) -> tuple[int, int]:
    """Copy font files into the user font dir; returns (copied, skipped)."""
    dest = os.path.expanduser("~/.local/share/fonts/windows-carryover")
    os.makedirs(dest, exist_ok=True)
    copied = skipped = 0
    for font_dir in font_dirs:
        try:
            entries = list(os.scandir(font_dir))
        except OSError:
            continue
        for entry in entries:
            if not (entry.is_file() and entry.name.lower().endswith(_FONT_EXTS)):
                continue
            target = os.path.join(dest, entry.name)
            if os.path.exists(target):
                skipped += 1
                continue
            try:
                shutil.copy2(entry.path, target)
                copied += 1
            except OSError:
                skipped += 1
    subprocess.run(["fc-cache", "-f", dest], capture_output=True, timeout=120)
    return copied, skipped


def _copy_game_saves(saves: list[dict]) -> tuple[int, int, str]:
    """Copy rescued save folders under ~/Documents; returns (ok, failed, dest)."""
    base = os.path.join(_windows_folder_dest("Documents"), "Rescued Game Saves")
    ok = failed = 0
    for item in saves:
        sub = os.path.join(item["user"], item["label"]) if item["user"] else item["label"]
        target = os.path.join(base, sub)
        try:
            shutil.copytree(item["src"], target, dirs_exist_ok=True)
            ok += 1
        except Exception:
            failed += 1
    return ok, failed, base


def _export_sticky_notes(sticky: list[dict]) -> tuple[int, str]:
    """Write each note as a text file; returns (count, folder)."""
    base = os.path.join(_windows_folder_dest("Documents"), "Sticky Notes")
    count = 0
    for source in sticky:
        folder = os.path.join(base, source["user"]) if len(sticky) > 1 else base
        os.makedirs(folder, exist_ok=True)
        for idx, text in enumerate(source["notes"], start=1):
            first_line = text.splitlines()[0][:40].strip() or "Note"
            safe = re.sub(r'[<>:"/\\|?*\n]', "", first_line)
            path = os.path.join(folder, f"{idx:02d} — {safe}.txt")
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text + "\n")
                count += 1
            except OSError:
                pass
    return count, base


def _import_rdp_bookmarks(connections: list[dict]) -> tuple[int, int]:
    """Add rdp:// bookmarks to KRDC's bookmarks.xbel; returns (added, dupes)."""
    import defusedxml.ElementTree as ET
    path = os.path.expanduser("~/.local/share/krdc/bookmarks.xbel")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path):
        tree = ET.parse(path)
        root = tree.getroot()
    else:
        root = ET.Element("xbel", {"folded": "no"})
        tree = ET.ElementTree(root)
    existing = {bm.get("href") for bm in root.iter("bookmark")}
    added = dupes = 0
    for conn in connections:
        user_part = f"{conn['username']}@" if conn["username"] else ""
        href = f"rdp://{user_part}{conn['host']}"
        if href in existing:
            dupes += 1
            continue
        bm = ET.SubElement(root, "bookmark", {"href": href})
        title = ET.SubElement(bm, "title")
        title.text = conn["name"]
        existing.add(href)
        added += 1
    if added:
        tree.write(path, encoding="UTF-8", xml_declaration=True)
    return added, dupes


# ── Page: Move Files ──────────────────────────────────────────────────
class WindowsMigrationPage(Page):
    def __init__(self, navigate=None):
        super().__init__()
        self._navigate = navigate or (lambda _: None)
        self._worker: WindowsLibraryWorker | None = None
        self._files_profiles: list[tuple[dict, dict]] = []
        self._files_checks: list[tuple[QCheckBox, str, str, str]] = []
        self._files_sizes_key = ""
        self._folder_sizes_cache: dict[str, dict] = {}
        self._files_sizes_workers: dict[str, DataWorker] = {}
        self._files_copy_worker: UserFilesCopyWorker | None = None
        self._bm_worker: DataWorker | None = None
        self._bm_sources: list[dict] = []
        self._bm_dest = ""
        self._hw_worker: DataWorker | None = None
        self._extras: dict = {}
        self._extras_worker: DataWorker | None = None
        self._fonts_copy_worker: DataWorker | None = None
        self._saves_copy_worker: DataWorker | None = None
        self._wsl_worker: Worker | None = None
        self._phone_worker: DataWorker | None = None
        self._phone_action_worker: DataWorker | None = None
        self._dynamic_lock_worker: DataWorker | None = None

        self._page_header(
            "Apps",
            "Move Files",
            "Bring your files, games, and familiar habits over without touching the original install.",
        )

        intro, intro_layout = _make_card("card-accent-ok")
        intro_title = QLabel("Start here if this is your first week on KythOS")
        intro_title.setObjectName("card-title")
        intro_layout.addWidget(intro_title)
        intro_body = QLabel(
            "KythOS can read PC drives, copy personal files, import Steam libraries, "
            "and point you toward the right app path for original installers. PC drives "
            "are treated carefully: migration tools read from them and copy into your home folder."
        )
        intro_body.setObjectName("card-copy")
        intro_body.setWordWrap(True)
        intro_layout.addWidget(intro_body)
        intro_btns = QHBoxLayout()
        intro_btns.setSpacing(8)
        for label, page in (
            ("Install Familiar Apps", "App Store"),
            ("Move Steam Games", "Gaming"),
            ("Back Up Saves", "Gaming"),
            ("Open File Manager", None),
        ):
            btn = QPushButton(label)
            if page:
                btn.clicked.connect(lambda _=False, key=page: self._navigate(key))
            else:
                btn.clicked.connect(lambda _=False: subprocess.Popen(["dolphin", os.path.expanduser("~")]) if shutil.which("dolphin") else QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.expanduser("~"))))
            intro_btns.addWidget(btn)
        intro_btns.addStretch()
        intro_layout.addLayout(intro_btns)
        self._add(intro)

        flow_card, flow_layout = _make_card()
        flow_title = QLabel("Migration path")
        flow_title.setObjectName("card-title")
        flow_layout.addWidget(flow_title)
        for i, (title, copy) in enumerate((
            ("Scan PC drives", "Detect NTFS, BitLocker, hibernation state, user folders, Steam libraries, and safe mount points."),
            ("Choose what to copy", "Select personal folders, bookmarks, saves, or game libraries. The PC drive is the source, not the destination."),
            ("Copy into KythOS", "Files land in your home folder or Steam library on a Linux-formatted disk. Windows stays untouched."),
            ("Finish the habits", "Set up cloud sync, shortcuts, phone pairing, printer setup, and PowerToys equivalents from this page."),
        ), 1):
            flow_layout.addWidget(_make_flow_step(i, title, copy))
        self._add(flow_card)

        checklist, checklist_layout = _make_card()
        checklist_title = QLabel("Windows switch checklist")
        checklist_title.setObjectName("card-title")
        checklist_layout.addWidget(checklist_title)
        for status, title, text in (
            ("ok", "Apps", "Use App Store for trending Flatpaks, starter packs, AppImages, and installed apps."),
            ("ok", "Games", "Use Steam, Heroic, Lutris, or Bottles instead of running random original installers directly."),
            ("warn", "Files", "Use Copy My Files below: scan your PC drive, then copy Documents, Pictures, Music, and Videos into your home folder."),
            ("warn", "Bookmarks", "Export Chrome, Edge, or Firefox bookmarks below; passwords come across via browser sync."),
            ("warn", "Saves", "Install Ludusavi before moving large libraries or experimenting with mods."),
            ("dim", "Updates", "KythOS updates stage a new OS image. Reboot when ready; rollbacks stay available."),
        ):
            checklist_layout.addWidget(self._make_migration_row(status, title, text))
        self._add(checklist)

        # Hardware sanity — the things the previous setup configured silently
        hw_card, hw_layout = _make_card()
        hw_top = QHBoxLayout()
        hw_title = QLabel("Did everything come along? Quick hardware check")
        hw_title.setObjectName("card-title")
        hw_top.addWidget(hw_title)
        hw_top.addStretch()
        hw_again_btn = QPushButton("Check Again")
        hw_again_btn.clicked.connect(self._run_hw_sanity)
        hw_top.addWidget(hw_again_btn)
        hw_layout.addLayout(hw_top)
        hw_body = QLabel(
            "Network, display (HDR and variable refresh), printers, Bluetooth, and power — "
            "the things Windows set up silently, checked here so you don't have to hunt for drivers."
        )
        hw_body.setObjectName("card-copy")
        hw_body.setWordWrap(True)
        hw_layout.addWidget(hw_body)
        self._hw_status = QLabel("Checking…")
        self._hw_status.setObjectName("card-copy")
        hw_layout.addWidget(self._hw_status)
        self._hw_rows = QVBoxLayout()
        self._hw_rows.setSpacing(6)
        hw_layout.addLayout(self._hw_rows)
        hw_btns = QHBoxLayout()
        hw_btns.setSpacing(8)
        self._hw_printer_btn = QPushButton("Set Up Printer")
        self._hw_printer_btn.setToolTip("Runs: ujust setup-printer")
        self._hw_printer_btn.hide()
        self._hw_printer_btn.clicked.connect(
            lambda _=False: self._run_ujust("setup-printer", self._hw_printer_btn))
        hw_btns.addWidget(self._hw_printer_btn)
        hw_open_btn = QPushButton("Open Hardware")
        hw_open_btn.clicked.connect(lambda _=False: self._navigate("Hardware"))
        hw_btns.addWidget(hw_open_btn)
        hw_btns.addStretch()
        hw_layout.addLayout(hw_btns)
        self._add(hw_card)
        # Pages are built eagerly at startup; defer the subprocess probes.
        QTimer.singleShot(900, self._run_hw_sanity)

        # Dual-boot clock fix card
        clock_card, clock_layout = _make_card("card-accent-warn")
        clock_title = QLabel("Dual-booting? Fix the clock.")
        clock_title.setObjectName("card-title")
        clock_layout.addWidget(clock_title)
        clock_body = QLabel(
            "After booting KythOS, Windows often shows the wrong time — sometimes off by several hours. "
            "This happens because Windows and Linux disagree about whether the hardware clock stores "
            "local time or UTC. One command fixes it permanently with no reboot needed."
        )
        clock_body.setObjectName("card-copy")
        clock_body.setWordWrap(True)
        clock_layout.addWidget(clock_body)
        clock_btns = QHBoxLayout()
        clock_btns.setSpacing(8)
        clock_fix_btn = QPushButton("Fix Dual-Boot Clock")
        clock_fix_btn.setObjectName("primary")
        clock_fix_btn.setToolTip("Runs: sudo timedatectl set-local-rtc 1 --adjust-system-clock")
        clock_fix_btn.clicked.connect(lambda _=False: self._run_ujust("fix-dualboot-clock", clock_fix_btn))
        clock_btns.addWidget(clock_fix_btn)
        clock_btns.addStretch()
        clock_layout.addLayout(clock_btns)
        self._add(clock_card)

        # Windows keyboard muscle memory
        shortcuts_card, shortcuts_layout = _make_card()
        shortcuts_title = QLabel("Keep your Windows keyboard shortcuts")
        shortcuts_title.setObjectName("card-title")
        shortcuts_layout.addWidget(shortcuts_title)
        shortcuts_body = QLabel(
            "Most familiar shortcuts already work on KythOS: Win+L locks, Win+D shows the desktop, "
            "Alt+Tab switches windows, Win+. opens the emoji picker. This adds the rest:"
        )
        shortcuts_body.setObjectName("card-copy")
        shortcuts_body.setWordWrap(True)
        shortcuts_layout.addWidget(shortcuts_body)
        for keys, what in (
            ("Win+E", "Open the file manager (Dolphin)"),
            ("Win+Shift+S", "Snip a region of the screen (Spectacle)"),
            ("Win+V", "Show clipboard history at the cursor"),
        ):
            row = QHBoxLayout()
            row.setSpacing(10)
            keys_lbl = QLabel(keys)
            keys_lbl.setStyleSheet(
                "font-family: monospace; font-size:12px; font-weight:600; color:#cccccc; "
                "background:#252526; border:1px solid #3c3c3c; border-radius:3px; padding:2px 8px;"
            )
            keys_lbl.setMinimumWidth(110)
            row.addWidget(keys_lbl)
            what_lbl = QLabel(what)
            what_lbl.setObjectName("card-copy")
            row.addWidget(what_lbl, 1)
            shortcuts_layout.addLayout(row)
        self._shortcuts_status = QLabel("")
        self._shortcuts_status.setObjectName("card-copy")
        self._shortcuts_status.setWordWrap(True)
        shortcuts_layout.addWidget(self._shortcuts_status)
        shortcuts_btns = QHBoxLayout()
        shortcuts_btns.setSpacing(8)
        shortcuts_apply_btn = QPushButton("Apply Familiar Shortcuts")
        shortcuts_apply_btn.setObjectName("primary")
        shortcuts_apply_btn.clicked.connect(self._apply_windows_shortcuts)
        shortcuts_btns.addWidget(shortcuts_apply_btn)
        shortcuts_revert_btn = QPushButton("Restore KDE Defaults")
        shortcuts_revert_btn.clicked.connect(self._revert_windows_shortcuts)
        shortcuts_btns.addWidget(shortcuts_revert_btn)
        shortcuts_btns.addStretch()
        shortcuts_layout.addLayout(shortcuts_btns)
        self._add(shortcuts_card)

        # PowerToys equivalents built into Plasma and Dolphin
        powertoys_card, powertoys_layout = _make_card()
        powertoys_title = QLabel("PowerToys equivalents — already built in")
        powertoys_title.setObjectName("card-title")
        powertoys_layout.addWidget(powertoys_title)
        powertoys_body = QLabel(
            "The names are different, but the useful PowerToys workflows are here "
            "without another background utility."
        )
        powertoys_body.setObjectName("card-copy")
        powertoys_body.setWordWrap(True)
        powertoys_layout.addWidget(powertoys_body)
        for title, summary in (
            ("PowerToys Run", "Press Alt+Space for KRunner: launch apps, search files, calculate, convert units, and run commands."),
            ("FancyZones", "Press Win+T for the KDE tile editor, or drag windows while holding Shift to use your tile layout."),
            ("Always on Top", "Right-click a title bar → More Actions → Keep Above Others; assign a custom shortcut in System Settings."),
            ("PowerRename", "Select multiple files in Dolphin and press F2 for batch rename with find-and-replace and numbering."),
            ("Keyboard Manager", "System Settings → Keyboard → Shortcuts remaps global shortcuts and application actions."),
            ("Awake", "Use Power Management settings, or Game Night Mode on the Gaming page to prevent sleep while playing."),
            ("Color Picker / Text Extractor", "Spectacle covers region capture and annotation; dedicated color-picker and OCR apps are available in the App Store."),
        ):
            powertoys_layout.addWidget(self._make_migration_row("ok", title, summary))
        powertoys_btns = QHBoxLayout()
        powertoys_btns.setSpacing(8)
        run_btn = QPushButton("Open PowerToys Run")
        run_btn.setObjectName("primary")
        run_btn.clicked.connect(self._open_krunner)
        powertoys_btns.addWidget(run_btn)
        shortcuts_btn = QPushButton("Open Keyboard Shortcuts")
        shortcuts_btn.clicked.connect(
            lambda _=False: self._open_settings_module("kcm_keys", "Keyboard Shortcuts")
        )
        powertoys_btns.addWidget(shortcuts_btn)
        rules_btn = QPushButton("Open Window Rules")
        rules_btn.clicked.connect(
            lambda _=False: self._open_settings_module("kcm_kwinrules", "Window Rules")
        )
        powertoys_btns.addWidget(rules_btn)
        powertoys_btns.addStretch()
        powertoys_layout.addLayout(powertoys_btns)
        self._powertoys_status = QLabel("")
        self._powertoys_status.setObjectName("card-copy")
        self._powertoys_status.setWordWrap(True)
        powertoys_layout.addWidget(self._powertoys_status)
        self._add(powertoys_card)

        # Terminal & shell tools card
        shell_card, shell_layout = _make_card()
        shell_title = QLabel("Terminal & Shell Tools")
        shell_title.setObjectName("card-title")
        shell_layout.addWidget(shell_title)
        shell_body = QLabel(
            "KythOS ships a pre-configured terminal experience — no manual plugin installs. "
            "Every new account gets eza (better ls), bat (syntax-highlighted cat), fd (better find), "
            "ripgrep (fast search), fzf (Ctrl+R fuzzy history), zoxide (smart cd that learns your habits), "
            "git-delta (beautiful diffs), and starship (git-aware prompt). "
            "Fish and Zsh both have autosuggestions and syntax highlighting out of the box. "
            "To switch to fish: open Konsole → Settings → Edit Profiles → Command → /usr/bin/fish."
        )
        shell_body.setObjectName("card-copy")
        shell_body.setWordWrap(True)
        shell_layout.addWidget(shell_body)
        for win_tool, linux_equiv in [
            ("cmd / PowerShell", "Konsole with zsh/fish — autosuggestions + syntax highlighting"),
            ("Terminal tabs", "Konsole profiles or zellij (modern terminal multiplexer)"),
            ("Everything (search)", "fd / ripgrep — 10–100× faster, respects .gitignore"),
            ("notepad.exe", "helix (hx) — modal editor with LSP, no config needed"),
            ("grep / findstr", "rg (ripgrep) — alias: search <pattern>"),
        ]:
            shell_layout.addWidget(self._make_migration_row("ok", win_tool, linux_equiv))
        shell_btns = QHBoxLayout()
        shell_btns.setSpacing(8)
        open_konsole_btn = QPushButton("Open Terminal")
        open_konsole_btn.clicked.connect(
            lambda _=False: self._run_background(["konsole"])
        )
        shell_btns.addWidget(open_konsole_btn)
        shell_btns.addStretch()
        shell_layout.addLayout(shell_btns)
        self._add(shell_card)

        # OneDrive / cloud sync card
        onedrive_card, onedrive_layout = _make_card()
        onedrive_title = QLabel("OneDrive & Google Drive sync")
        onedrive_title.setObjectName("card-title")
        onedrive_layout.addWidget(onedrive_title)
        onedrive_body = QLabel(
            "KythOS includes a built-in Cloud Storage wizard that connects OneDrive and Google Drive "
            "via rclone — free, open-source, and background-sync capable. Files stay in a folder "
            "in your home directory and sync automatically. No paid client needed."
        )
        onedrive_body.setObjectName("card-copy")
        onedrive_body.setWordWrap(True)
        onedrive_layout.addWidget(onedrive_body)
        onedrive_btns = QHBoxLayout()
        onedrive_btns.setSpacing(8)
        onedrive_open_btn = QPushButton("Set Up Cloud Storage")
        onedrive_open_btn.setObjectName("primary")
        onedrive_open_btn.clicked.connect(lambda _=False: self._navigate("Cloud Storage"))
        onedrive_btns.addWidget(onedrive_open_btn)
        onedrive_btns.addStretch()
        onedrive_layout.addLayout(onedrive_btns)
        self._add(onedrive_card)

        # Nearby Sharing equivalents
        nearby_card, nearby_layout = _make_card("card-accent-ok")
        nearby_title = QLabel("Nearby Sharing → LocalSend and KDE Connect")
        nearby_title.setObjectName("card-title")
        nearby_layout.addWidget(nearby_title)
        nearby_body = QLabel(
            "Send files directly over your local network without uploading them first. "
            "LocalSend works across Windows, macOS, Linux, Android, and iPhone; KDE Connect "
            "adds phone notifications, clipboard sharing, and a Dolphin right-click action "
            "named Send to Nearby Device."
        )
        nearby_body.setObjectName("card-copy")
        nearby_body.setWordWrap(True)
        nearby_layout.addWidget(nearby_body)
        nearby_btns = QHBoxLayout()
        nearby_btns.setSpacing(8)
        self._localsend_btn = QPushButton()
        self._localsend_btn.setObjectName("primary")
        self._localsend_btn.clicked.connect(self._open_or_install_localsend)
        nearby_btns.addWidget(self._localsend_btn)
        send_btn = QPushButton("Send a File")
        send_btn.setToolTip("Choose files, then select a paired KDE Connect device.")
        send_btn.clicked.connect(self._send_nearby_files)
        nearby_btns.addWidget(send_btn)
        pair_btn = QPushButton("Pair a Phone or PC")
        pair_btn.clicked.connect(self._open_kde_connect)
        nearby_btns.addWidget(pair_btn)
        nearby_btns.addStretch()
        nearby_layout.addLayout(nearby_btns)
        self._nearby_status = QLabel("")
        self._nearby_status.setObjectName("card-copy")
        self._nearby_status.setWordWrap(True)
        nearby_layout.addWidget(self._nearby_status)
        self._refresh_localsend_btn()
        self._add(nearby_card)

        # Phone Link replacement
        phone_card, phone_layout = _make_card("card-accent-ok")
        phone_title = QLabel("Phone Link → Connected Devices")
        phone_title.setObjectName("card-title")
        phone_layout.addWidget(phone_title)
        phone_body = QLabel(
            "On Windows you had Phone Link; KythOS has KDE Connect built in. Pair your phone "
            "over Wi-Fi to see and answer notifications on the desktop, send files both ways, "
            "share the clipboard, control media, ring a lost phone, and optionally lock this PC "
            "when your trusted device leaves. Both devices must be on the same network."
        )
        phone_body.setObjectName("card-copy")
        phone_body.setWordWrap(True)
        phone_layout.addWidget(phone_body)

        device_row = QHBoxLayout()
        device_row.setSpacing(8)
        device_row.addWidget(QLabel("Paired device:"))
        self._phone_device = QComboBox()
        self._phone_device.setMinimumWidth(260)
        self._phone_device.currentIndexChanged.connect(self._update_phone_controls)
        device_row.addWidget(self._phone_device)
        refresh_phone_btn = QPushButton("Refresh")
        refresh_phone_btn.clicked.connect(self._refresh_phone_devices)
        device_row.addWidget(refresh_phone_btn)
        open_phone_btn = QPushButton("Pair / Manage Devices")
        open_phone_btn.clicked.connect(self._open_kde_connect)
        device_row.addWidget(open_phone_btn)
        device_row.addStretch()
        phone_layout.addLayout(device_row)

        phone_actions = QHBoxLayout()
        phone_actions.setSpacing(8)
        self._phone_action_buttons = []
        for label, action, tip in (
            ("Ping", "--ping", "Show a test notification on the selected device."),
            ("Ring Device", "--ring", "Ring the selected device so you can find it."),
            ("Send Clipboard", "--send-clipboard", "Send the current desktop clipboard to the selected device."),
            ("Send Text", "--send-sms", "Send an SMS through a paired Android phone."),
            ("Browse Files", "--mount", "Mount the selected device and open its shared files in Dolphin."),
        ):
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.clicked.connect(
                lambda _=False, selected_action=action: self._run_phone_action(selected_action)
            )
            phone_actions.addWidget(btn)
            self._phone_action_buttons.append(btn)
        phone_actions.addStretch()
        phone_layout.addLayout(phone_actions)

        dynamic_lock_row = QHBoxLayout()
        dynamic_lock_row.setSpacing(8)
        self._dynamic_lock_check = QCheckBox("Dynamic Lock: lock this PC when the device leaves")
        dynamic_lock_row.addWidget(self._dynamic_lock_check)
        dynamic_lock_row.addWidget(QLabel("Wait:"))
        self._dynamic_lock_grace = QComboBox()
        for label, seconds in (("30 seconds", 30), ("1 minute", 60), ("2 minutes", 120)):
            self._dynamic_lock_grace.addItem(label, seconds)
        dynamic_lock_row.addWidget(self._dynamic_lock_grace)
        save_lock_btn = QPushButton("Save Trusted Device")
        save_lock_btn.clicked.connect(self._save_dynamic_lock)
        dynamic_lock_row.addWidget(save_lock_btn)
        dynamic_lock_row.addStretch()
        phone_layout.addLayout(dynamic_lock_row)

        lock_config = _load_dynamic_lock_config()
        self._dynamic_lock_check.setChecked(lock_config.get("enabled") is True)
        try:
            grace = int(lock_config.get("grace_seconds") or 60)
        except (TypeError, ValueError):
            grace = 60
        for idx in range(self._dynamic_lock_grace.count()):
            if self._dynamic_lock_grace.itemData(idx) == grace:
                self._dynamic_lock_grace.setCurrentIndex(idx)
                break
        self._phone_status = QLabel("")
        self._phone_status.setObjectName("card-copy")
        self._phone_status.setWordWrap(True)
        phone_layout.addWidget(self._phone_status)
        phone_btns = QHBoxLayout()
        phone_btns.setSpacing(8)
        phone_android_btn = QPushButton("Android App")
        phone_android_btn.clicked.connect(lambda _=False: QDesktopServices.openUrl(
            QUrl("https://play.google.com/store/apps/details?id=org.kde.kdeconnect_tp")))
        phone_btns.addWidget(phone_android_btn)
        phone_ios_btn = QPushButton("iPhone App")
        phone_ios_btn.clicked.connect(lambda _=False: QDesktopServices.openUrl(
            QUrl("https://apps.apple.com/app/kde-connect/id1580245991")))
        phone_btns.addWidget(phone_ios_btn)
        phone_btns.addStretch()
        phone_layout.addLayout(phone_btns)
        self._add(phone_card)
        QTimer.singleShot(0, self._refresh_phone_devices)

        score_card, score_layout = _make_card("card-accent-ok")
        score_title = QLabel("Switch Readiness")
        score_title.setObjectName("card-title")
        score_layout.addWidget(score_title)
        self._migration_score_lbl = QLabel(
            "Scan drives to estimate migration readiness. KythOS looks at launchers, save tools, PC drives, and safe copy paths."
        )
        self._migration_score_lbl.setObjectName("card-copy")
        self._migration_score_lbl.setWordWrap(True)
        score_layout.addWidget(self._migration_score_lbl)
        score_btns = QHBoxLayout()
        for label, page in (("Install Launchers", "Gaming"), ("Back Up Saves", "Gaming"), ("Cloud Storage", "Cloud Storage")):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, key=page: self._navigate(key))
            score_btns.addWidget(btn)
        score_btns.addStretch()
        score_layout.addLayout(score_btns)
        self._add(score_card)

        drives, drives_layout = _make_card()
        drives_top = QHBoxLayout()
        drives_title = QLabel("PC drives")
        drives_title.setObjectName("card-title")
        drives_top.addWidget(drives_title)
        drives_top.addStretch()
        refresh_btn = QPushButton("Scan Drives")
        refresh_btn.setObjectName("primary")
        refresh_btn.clicked.connect(self._scan_windows_drives)
        drives_top.addWidget(refresh_btn)
        drives_layout.addLayout(drives_top)
        drives_desc = QLabel(
            "Looks for NTFS partitions, hibernation/dirty flags, Windows user folders, mount points, and Steam folders. "
            "If a drive is hibernated, boot the other system once and choose full Shut Down before copying from it."
        )
        drives_desc.setObjectName("card-copy")
        drives_desc.setWordWrap(True)
        drives_layout.addWidget(drives_desc)
        ntfs_warn = QLabel(
            "⚠  Browse and copy files from PC drives freely — but don't add one as a Steam "
            "library or launch games from it. Proton needs a Linux-formatted disk; games run "
            "straight off NTFS break in confusing ways. Use Copy Games to KythOS instead."
        )
        ntfs_warn.setObjectName("card-copy")
        ntfs_warn.setWordWrap(True)
        ntfs_warn.setStyleSheet("color: #d4a843;")
        drives_layout.addWidget(ntfs_warn)
        self._drive_status = QLabel("Click Scan Drives to look for system partitions.")
        self._drive_status.setObjectName("card-copy")
        self._drive_status.setWordWrap(True)
        drives_layout.addWidget(self._drive_status)
        self._drive_progress = QProgressBar()
        self._drive_progress.setRange(0, 0)
        self._drive_progress.hide()
        drives_layout.addWidget(self._drive_progress)
        self._drive_rows = QVBoxLayout()
        self._drive_rows.setSpacing(8)
        drives_layout.addLayout(self._drive_rows)
        self._add(drives)

        # ── Copy My Files ─────────────────────────────────────────────────────
        files_card, files_layout = _make_card()
        files_title = QLabel("Copy your files from another system")
        files_title.setObjectName("card-title")
        files_layout.addWidget(files_title)
        self._files_intro = QLabel(
            "Click Scan Drives above — your Windows user folders show up here, and one click "
            "copies Documents, Pictures, Music, Videos, and more into your KythOS home folder. "
            "The Windows side is never modified."
        )
        self._files_intro.setObjectName("card-copy")
        self._files_intro.setWordWrap(True)
        files_layout.addWidget(self._files_intro)
        self._files_profile_combo = QComboBox()
        self._files_profile_combo.hide()
        self._files_profile_combo.currentIndexChanged.connect(self._on_files_profile_changed)
        files_layout.addWidget(self._files_profile_combo)
        self._files_rows = QVBoxLayout()
        self._files_rows.setSpacing(4)
        files_layout.addLayout(self._files_rows)
        self._files_space_lbl = QLabel("")
        self._files_space_lbl.setObjectName("card-copy")
        files_layout.addWidget(self._files_space_lbl)
        self._files_status = QLabel("")
        self._files_status.setObjectName("card-copy")
        self._files_status.setWordWrap(True)
        files_layout.addWidget(self._files_status)
        self._files_progress = QProgressBar()
        self._files_progress.setRange(0, 100)
        self._files_progress.hide()
        files_layout.addWidget(self._files_progress)
        files_btns = QHBoxLayout()
        files_btns.setSpacing(8)
        self._files_copy_btn = QPushButton("Copy Selected Folders")
        self._files_copy_btn.setObjectName("primary")
        self._files_copy_btn.hide()
        self._files_copy_btn.clicked.connect(self._start_files_copy)
        files_btns.addWidget(self._files_copy_btn)
        self._files_cancel_btn = QPushButton("Cancel")
        self._files_cancel_btn.hide()
        self._files_cancel_btn.clicked.connect(self._cancel_files_copy)
        files_btns.addWidget(self._files_cancel_btn)
        files_btns.addStretch()
        files_layout.addLayout(files_btns)
        self._add(files_card)

        # ── Browser bookmarks ─────────────────────────────────────────────────
        bm_card, bm_layout = _make_card()
        bm_title = QLabel("Bring your browser bookmarks")
        bm_title.setObjectName("card-title")
        bm_layout.addWidget(bm_title)
        bm_body = QLabel(
            "Bookmarks are read straight off the PC drive — Chrome, Edge, Brave, Vivaldi, "
            "Opera, and Firefox — and saved as one standard bookmarks file that any browser can "
            "import. Passwords can't be copied (Windows encrypts them per-machine); sign into "
            "Firefox Sync or your Google account to bring those across."
        )
        bm_body.setObjectName("card-copy")
        bm_body.setWordWrap(True)
        bm_layout.addWidget(bm_body)
        self._bm_status = QLabel("Scan drives above — bookmarks are found automatically.")
        self._bm_status.setObjectName("card-copy")
        self._bm_status.setWordWrap(True)
        bm_layout.addWidget(self._bm_status)
        self._bm_rows = QVBoxLayout()
        self._bm_rows.setSpacing(6)
        bm_layout.addLayout(self._bm_rows)
        bm_btns = QHBoxLayout()
        bm_btns.setSpacing(8)
        self._bm_export_btn = QPushButton("Save Bookmarks File")
        self._bm_export_btn.setObjectName("primary")
        self._bm_export_btn.hide()
        self._bm_export_btn.clicked.connect(self._export_bookmarks)
        bm_btns.addWidget(self._bm_export_btn)
        self._bm_show_btn = QPushButton("Show File")
        self._bm_show_btn.hide()
        self._bm_show_btn.clicked.connect(lambda _=False: QDesktopServices.openUrl(
            QUrl.fromLocalFile(os.path.dirname(self._bm_dest))) if self._bm_dest else None)
        bm_btns.addWidget(self._bm_show_btn)
        bm_btns.addStretch()
        bm_layout.addLayout(bm_btns)
        self._add(bm_card)

        # ── Windows wallpaper ─────────────────────────────────────────────────
        wp_card, wp_layout = _make_card()
        wp_title = QLabel("Keep your Windows wallpaper")
        wp_title.setObjectName("card-title")
        wp_layout.addWidget(wp_title)
        wp_body = QLabel(
            "Your desktop background comes straight off the PC drive and is saved "
            "into Pictures — one click and the desktop feels like home."
        )
        wp_body.setObjectName("card-copy")
        wp_body.setWordWrap(True)
        wp_layout.addWidget(wp_body)
        self._wp_status = QLabel("Scan drives above — wallpapers are found automatically.")
        self._wp_status.setObjectName("card-copy")
        self._wp_status.setWordWrap(True)
        wp_layout.addWidget(self._wp_status)
        self._wp_combo = QComboBox()
        self._wp_combo.hide()
        wp_layout.addWidget(self._wp_combo)
        wp_btns = QHBoxLayout()
        wp_btns.setSpacing(8)
        self._wp_apply_btn = QPushButton("Use This Wallpaper")
        self._wp_apply_btn.setObjectName("primary")
        self._wp_apply_btn.hide()
        self._wp_apply_btn.clicked.connect(self._apply_windows_wallpaper)
        wp_btns.addWidget(self._wp_apply_btn)
        wp_btns.addStretch()
        wp_layout.addLayout(wp_btns)
        self._add(wp_card)

        # ── system fonts ─────────────────────────────────────────────────────
        fonts_card, fonts_layout = _make_card()
        fonts_title = QLabel("Bring your system fonts")
        fonts_title.setObjectName("card-title")
        fonts_layout.addWidget(fonts_title)
        fonts_body = QLabel(
            "Modern documents use Segoe UI, Calibri, and Cambria — fonts the downloadable "
            "core-fonts set doesn't include. Copying your own fonts from the original install "
            "on this PC makes documents render identically here."
        )
        fonts_body.setObjectName("card-copy")
        fonts_body.setWordWrap(True)
        fonts_layout.addWidget(fonts_body)
        self._fonts_status = QLabel("Scan drives above — system font folders are found automatically.")
        self._fonts_status.setObjectName("card-copy")
        self._fonts_status.setWordWrap(True)
        fonts_layout.addWidget(self._fonts_status)
        fonts_btns = QHBoxLayout()
        fonts_btns.setSpacing(8)
        self._fonts_btn = QPushButton("Copy Windows Fonts")
        self._fonts_btn.setObjectName("primary")
        self._fonts_btn.hide()
        self._fonts_btn.clicked.connect(self._copy_fonts_clicked)
        fonts_btns.addWidget(self._fonts_btn)
        fonts_btns.addStretch()
        fonts_layout.addLayout(fonts_btns)
        self._add(fonts_card)

        # ── Game saves rescue ─────────────────────────────────────────────────
        saves_card, saves_layout = _make_card()
        saves_title = QLabel("Rescue game saves from the PC drive")
        saves_title.setObjectName("card-title")
        saves_layout.addWidget(saves_title)
        saves_body = QLabel(
            "Saves hide in My Games, Saved Games, AppData, and Ubisoft's launcher folder. "
            "This finds them and copies everything into Documents → Rescued Game Saves, "
            "so nothing is lost when the PC drive goes away. Ludusavi can help place "
            "them into each game's new home."
        )
        saves_body.setObjectName("card-copy")
        saves_body.setWordWrap(True)
        saves_layout.addWidget(saves_body)
        self._saves_status = QLabel("Scan drives above — save locations are found automatically.")
        self._saves_status.setObjectName("card-copy")
        self._saves_status.setWordWrap(True)
        saves_layout.addWidget(self._saves_status)
        self._saves_rows = QVBoxLayout()
        self._saves_rows.setSpacing(4)
        saves_layout.addLayout(self._saves_rows)
        saves_btns = QHBoxLayout()
        saves_btns.setSpacing(8)
        self._saves_btn = QPushButton("Copy All Found Saves")
        self._saves_btn.setObjectName("primary")
        self._saves_btn.hide()
        self._saves_btn.clicked.connect(self._copy_saves_clicked)
        saves_btns.addWidget(self._saves_btn)
        self._saves_show_btn = QPushButton("Show Folder")
        self._saves_show_btn.hide()
        self._saves_show_btn.clicked.connect(lambda _=False: QDesktopServices.openUrl(
            QUrl.fromLocalFile(os.path.join(_windows_folder_dest("Documents"), "Rescued Game Saves"))))
        saves_btns.addWidget(self._saves_show_btn)
        saves_btns.addStretch()
        saves_layout.addLayout(saves_btns)
        self._add(saves_card)

        # ── Sticky Notes ──────────────────────────────────────────────────────
        sticky_card, sticky_layout = _make_card()
        sticky_title = QLabel("Bring your Sticky Notes")
        sticky_title.setObjectName("card-title")
        sticky_layout.addWidget(sticky_title)
        sticky_body = QLabel(
            "Notes from the Windows Sticky Notes app are read from the drive and saved as "
            "text files in Documents → Sticky Notes. For the same look here, right-click "
            "the desktop → Add Widgets → Sticky Note, then paste a note in."
        )
        sticky_body.setObjectName("card-copy")
        sticky_body.setWordWrap(True)
        sticky_layout.addWidget(sticky_body)
        self._sticky_status = QLabel("Scan drives above — Sticky Notes are found automatically.")
        self._sticky_status.setObjectName("card-copy")
        self._sticky_status.setWordWrap(True)
        sticky_layout.addWidget(self._sticky_status)
        sticky_btns = QHBoxLayout()
        sticky_btns.setSpacing(8)
        self._sticky_btn = QPushButton("Export Notes")
        self._sticky_btn.setObjectName("primary")
        self._sticky_btn.hide()
        self._sticky_btn.clicked.connect(self._export_sticky_clicked)
        sticky_btns.addWidget(self._sticky_btn)
        self._sticky_show_btn = QPushButton("Show Folder")
        self._sticky_show_btn.hide()
        self._sticky_show_btn.clicked.connect(lambda _=False: QDesktopServices.openUrl(
            QUrl.fromLocalFile(os.path.join(_windows_folder_dest("Documents"), "Sticky Notes"))))
        sticky_btns.addWidget(self._sticky_show_btn)
        sticky_btns.addStretch()
        sticky_layout.addLayout(sticky_btns)
        self._add(sticky_card)

        # ── Remote Desktop connections ────────────────────────────────────────
        rdp_card, rdp_layout = _make_card()
        rdp_title = QLabel("Remote Desktop connections")
        rdp_title.setObjectName("card-title")
        rdp_layout.addWidget(rdp_title)
        rdp_body = QLabel(
            "Saved .rdp files from your Windows Desktop, Documents, and Downloads become "
            "bookmarks in KRDC — the built-in Remote Desktop client (the mstsc equivalent)."
        )
        rdp_body.setObjectName("card-copy")
        rdp_body.setWordWrap(True)
        rdp_layout.addWidget(rdp_body)
        self._rdp_status = QLabel("Scan drives above — saved connections are found automatically.")
        self._rdp_status.setObjectName("card-copy")
        self._rdp_status.setWordWrap(True)
        rdp_layout.addWidget(self._rdp_status)
        rdp_btns = QHBoxLayout()
        rdp_btns.setSpacing(8)
        self._rdp_btn = QPushButton("Add to KRDC")
        self._rdp_btn.setObjectName("primary")
        self._rdp_btn.hide()
        self._rdp_btn.clicked.connect(self._import_rdp_clicked)
        rdp_btns.addWidget(self._rdp_btn)
        self._rdp_open_btn = QPushButton("Open KRDC")
        self._rdp_open_btn.hide()
        self._rdp_open_btn.clicked.connect(
            lambda _=False: subprocess.Popen(["krdc"]) if shutil.which("krdc") else None)
        rdp_btns.addWidget(self._rdp_open_btn)
        rdp_btns.addStretch()
        rdp_layout.addLayout(rdp_btns)
        self._add(rdp_card)

        exe_card, exe_layout = _make_card()
        exe_title = QLabel("What about .exe installers?")
        exe_title.setObjectName("card-title")
        exe_layout.addWidget(exe_title)
        exe_body = QLabel(
            "For games, start with Steam, Heroic, or Lutris. For standalone compatibility apps, "
            "use Bottles so each app gets its own isolated Windows-like environment. "
            "If a native Linux or Flatpak version exists, prefer that first."
        )
        exe_body.setObjectName("card-copy")
        exe_body.setWordWrap(True)
        exe_layout.addWidget(exe_body)
        exe_btns = QHBoxLayout()
        exe_btns.setSpacing(8)
        bottles_btn = QPushButton("Install Bottles")
        bottles_btn.clicked.connect(lambda _=False, b=bottles_btn: _install_flatpak_inline(
            self, b, "com.usebottles.bottles", "Bottles"))
        exe_btns.addWidget(bottles_btn)
        software_btn = QPushButton("Open App Store")
        software_btn.clicked.connect(lambda _=False: self._navigate("App Store"))
        exe_btns.addWidget(software_btn)
        exe_btns.addStretch()
        exe_layout.addLayout(exe_btns)
        self._add(exe_card)

        # ── WSL equivalent ────────────────────────────────────────────────────
        wsl_card, wsl_layout = _make_card()
        wsl_title = QLabel("Where's my WSL?")
        wsl_title.setObjectName("card-title")
        wsl_layout.addWidget(wsl_title)
        wsl_body = QLabel(
            "For Linux subsystem workflows gave you a Linux environment inside your OS. Here the whole OS "
            "is Linux — but the same workflow exists as Distrobox: full distros in containers "
            "that share your home folder, with no VM overhead. One click creates an Ubuntu "
            "environment; opening a terminal in it works just like typing wsl in PowerShell."
        )
        wsl_body.setObjectName("card-copy")
        wsl_body.setWordWrap(True)
        wsl_layout.addWidget(wsl_body)
        self._wsl_status = QLabel("")
        self._wsl_status.setObjectName("card-copy")
        self._wsl_status.setWordWrap(True)
        wsl_layout.addWidget(self._wsl_status)
        wsl_btns = QHBoxLayout()
        wsl_btns.setSpacing(8)
        self._wsl_create_btn = QPushButton("Create Ubuntu Box")
        self._wsl_create_btn.setObjectName("primary")
        self._wsl_create_btn.clicked.connect(self._create_wsl_box)
        wsl_btns.addWidget(self._wsl_create_btn)
        self._wsl_open_btn = QPushButton("Open Ubuntu Terminal")
        self._wsl_open_btn.clicked.connect(self._open_wsl_terminal)
        wsl_btns.addWidget(self._wsl_open_btn)
        wsl_btns.addStretch()
        wsl_layout.addLayout(wsl_btns)
        self._add(wsl_card)

        self._stretch()

    def _make_migration_row(self, status: str, title: str, summary: str) -> QFrame:
        row = QFrame()
        row.setObjectName({
            "ok": "hw-card-ok",
            "warn": "hw-card-warn",
            "err": "hw-card-err",
            "dim": "hw-card-dim",
        }.get(status, "hw-card-dim"))
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(10)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("card-summary")
        title_lbl.setMinimumWidth(110)
        layout.addWidget(title_lbl)
        summary_lbl = QLabel(summary)
        summary_lbl.setObjectName("card-copy")
        summary_lbl.setWordWrap(True)
        layout.addWidget(summary_lbl, 1)
        return row

    # kglobalshortcutsrc writes: (group path, key, value). Non-service entries
    # use the "active,default,description" triple format.
    _WINDOWS_SHORTCUT_KEYS = (
        (("services", "org.kde.dolphin.desktop"), "_launch", "Meta+E"),
        (("org.kde.spectacle.desktop",), "RectangularRegionScreenShot",
         "Meta+Shift+S,Meta+Shift+S,Capture Rectangular Region"),
        (("klipper",), "show-on-mouse-pos",
         "Meta+V,Meta+V,Show Clipboard Items at Mouse Position"),
    )

    def _run_shortcut_change(self, delete: bool) -> bool:
        if not shutil.which("kwriteconfig6"):
            self._shortcuts_status.setText("kwriteconfig6 not found — is this a KDE session?")
            return False
        ok = True
        for groups, key, value in self._WINDOWS_SHORTCUT_KEYS:
            cmd = ["kwriteconfig6", "--file", "kglobalshortcutsrc"]
            for group in groups:
                cmd += ["--group", group]
            cmd += ["--key", key]
            cmd += ["--delete"] if delete else [value]
            try:
                ok = subprocess.run(cmd, capture_output=True, timeout=10).returncode == 0 and ok
            except Exception:
                ok = False
        # kglobalaccel only rereads the file on restart.
        subprocess.run(
            ["systemctl", "--user", "restart", "plasma-kglobalaccel.service"],
            capture_output=True, timeout=10,
        )
        return ok

    def _apply_windows_shortcuts(self):
        if self._run_shortcut_change(delete=False):
            self._shortcuts_status.setText(
                "✓ familiar shortcuts applied — try Win+E. If a shortcut doesn't respond, sign out and back in."
            )

    def _revert_windows_shortcuts(self):
        if self._run_shortcut_change(delete=True):
            self._shortcuts_status.setText("✓ KDE default shortcuts restored.")

    def _open_kde_connect(self):
        for cmd in (["kdeconnect-app"], ["kcmshell6", "kcm_kdeconnect"], ["systemsettings", "kcm_kdeconnect"]):
            if shutil.which(cmd[0]):
                subprocess.Popen(cmd)
                self._phone_status.setText("")
                return
        self._phone_status.setText(
            "KDE Connect isn't available in this session — install it from the App Store, "
            "or check System Settings → Connected Devices."
        )

    def _selected_phone_device(self) -> dict | None:
        data = self._phone_device.currentData()
        return data if isinstance(data, dict) else None

    def _refresh_phone_devices(self):
        if self._phone_worker is not None and self._phone_worker.isRunning():
            return
        self._phone_status.setObjectName("card-copy")
        _restyle(self._phone_status)
        self._phone_status.setText("Looking for paired devices…")
        worker = DataWorker("kdeconnect-devices", _kdeconnect_devices)
        worker.result.connect(self._on_phone_devices)
        worker.failed.connect(
            lambda _key, message: self._phone_status.setText(
                f"Could not query KDE Connect: {message}"
            )
        )
        self._phone_worker = worker
        _release_worker_when_finished(self, "_phone_worker", worker)
        worker.start()

    def _on_phone_devices(self, _key: str, devices: list[dict]):
        config = _load_dynamic_lock_config()
        configured_id = str(config.get("device_id") or "")
        if configured_id and not any(item["id"] == configured_id for item in devices):
            devices.append({
                "id": configured_id,
                "name": str(config.get("device_name") or "Trusted device"),
                "reachable": False,
            })

        self._phone_device.blockSignals(True)
        self._phone_device.clear()
        selected_index = 0
        for idx, device in enumerate(devices):
            state = "Connected" if device["reachable"] else "Offline"
            self._phone_device.addItem(f"{device['name']} — {state}", device)
            if device["id"] == configured_id:
                selected_index = idx
        if devices:
            self._phone_device.setCurrentIndex(selected_index)
        else:
            self._phone_device.addItem("No paired devices found", None)
        self._phone_device.blockSignals(False)
        self._update_phone_controls()

        connected = sum(1 for item in devices if item["reachable"])
        if connected:
            self._phone_status.setText(
                f"{connected} connected device{'s' if connected != 1 else ''}. "
                "Notifications and clipboard sharing are managed by KDE Connect."
            )
        elif devices:
            self._phone_status.setText(
                "Paired device found, but it is offline. Wake it and put both devices on the same network."
            )
        else:
            self._phone_status.setText(
                "No paired devices yet. Install KDE Connect on your phone, then choose Pair / Manage Devices."
            )

    def _update_phone_controls(self, _index: int = -1):
        device = self._selected_phone_device()
        reachable = bool(device and device.get("reachable"))
        for btn in self._phone_action_buttons:
            btn.setEnabled(reachable)

    def _run_phone_action(self, action: str):
        if self._phone_action_worker is not None and self._phone_action_worker.isRunning():
            return
        device = self._selected_phone_device()
        if not device or not device.get("reachable"):
            self._phone_status.setText("Choose a connected device first.")
            return
        labels = {
            "--ping": "Sending ping",
            "--ring": "Ringing device",
            "--send-clipboard": "Sending clipboard",
            "--send-sms": "Sending text message",
            "--mount": "Connecting device files",
        }
        destination = ""
        message = ""
        if action == "--send-sms":
            destination, accepted = QInputDialog.getText(
                self, "Send Text Message", "Phone number:"
            )
            if not accepted or not destination.strip():
                return
            message, accepted = QInputDialog.getMultiLineText(
                self, "Send Text Message", "Message:"
            )
            if not accepted or not message.strip():
                return
        self._phone_status.setObjectName("card-copy")
        _restyle(self._phone_status)
        self._phone_status.setText(f"{labels.get(action, 'Contacting device')}…")
        if action == "--mount":
            fn = lambda: _mount_kdeconnect_device(device["id"])
        elif action == "--send-sms":
            fn = lambda: _send_kdeconnect_sms(
                device["id"], destination.strip(), message.strip()
            )
        else:
            fn = lambda: _run_kdeconnect_action(device["id"], action)
        worker = DataWorker(f"phone-action:{action}", fn)
        worker.result.connect(self._on_phone_action)
        worker.failed.connect(
            lambda _key, message: self._phone_status.setText(f"Device action failed: {message}")
        )
        self._phone_action_worker = worker
        _release_worker_when_finished(self, "_phone_action_worker", worker)
        worker.start()

    def _on_phone_action(self, key: str, result: tuple[bool, str]):
        ok, detail = result
        action = key.partition(":")[2]
        if ok and action == "--mount":
            QDesktopServices.openUrl(QUrl.fromLocalFile(detail))
            self._phone_status.setText("Device files opened in the file manager.")
        elif ok:
            messages = {
                "--ping": "Ping sent.",
                "--ring": "The device should be ringing now.",
                "--send-clipboard": "Clipboard sent to the device.",
                "--send-sms": "Text message sent through the paired phone.",
            }
            self._phone_status.setText(messages.get(action, detail or "Done."))
        else:
            self._phone_status.setText(detail or "The device action failed.")

    def _save_dynamic_lock(self):
        if self._dynamic_lock_worker is not None and self._dynamic_lock_worker.isRunning():
            return
        enabled = self._dynamic_lock_check.isChecked()
        device = self._selected_phone_device()
        if enabled and not device:
            self._phone_status.setText("Pair and select a trusted device before enabling Dynamic Lock.")
            return
        config = {
            "enabled": enabled,
            "device_id": device["id"] if device else "",
            "device_name": device["name"] if device else "",
            "grace_seconds": int(self._dynamic_lock_grace.currentData() or 60),
        }
        try:
            _save_dynamic_lock_config(config)
        except OSError as exc:
            self._phone_status.setText(f"Could not save Dynamic Lock: {exc}")
            return
        self._phone_status.setText("Saving Dynamic Lock settings…")
        worker = DataWorker(
            "dynamic-lock", lambda: _configure_dynamic_lock_service(enabled)
        )
        worker.result.connect(self._on_dynamic_lock_saved)
        worker.failed.connect(
            lambda _key, message: self._phone_status.setText(
                f"Could not update Dynamic Lock: {message}"
            )
        )
        self._dynamic_lock_worker = worker
        _release_worker_when_finished(self, "_dynamic_lock_worker", worker)
        worker.start()

    def _on_dynamic_lock_saved(self, _key: str, result: tuple[bool, str]):
        ok, detail = result
        self._phone_status.setText(detail)
        self._phone_status.setObjectName("status-ok" if ok else "status-warn")
        _restyle(self._phone_status)

    def _refresh_localsend_btn(self):
        installed = _is_flatpak_installed("org.localsend.localsend_app")
        self._localsend_btn.setText("Open LocalSend" if installed else "Install LocalSend")

    def _open_or_install_localsend(self):
        app_id = "org.localsend.localsend_app"
        if _is_flatpak_installed(app_id):
            try:
                subprocess.Popen(["flatpak", "run", app_id])
                self._nearby_status.setText("LocalSend opened. Devices on the same network appear automatically.")
            except OSError as exc:
                self._nearby_status.setText(f"Could not open LocalSend: {exc}")
            return

        def _installed(code: int):
            if code == 0:
                self._localsend_btn.setEnabled(True)
                self._refresh_localsend_btn()
                self._nearby_status.setText("LocalSend installed — open it on both devices to start sharing.")

        _install_flatpak_inline(
            self, self._localsend_btn, app_id, "LocalSend", done_cb=_installed,
        )

    def _send_nearby_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Send files to a nearby device", os.path.expanduser("~")
        )
        if not paths:
            return
        helper = "/usr/bin/kyth-nearby-share"
        if not os.path.exists(helper):
            self._nearby_status.setText(
                "Nearby Sharing is available after applying the latest KythOS update and restarting."
            )
            return
        try:
            subprocess.Popen([helper, *paths])
            self._nearby_status.setText("Choose the destination device in the Nearby Sharing prompt.")
        except OSError as exc:
            self._nearby_status.setText(f"Could not start Nearby Sharing: {exc}")

    def _open_krunner(self):
        for cmd in (
            ["krunner"],
            ["qdbus6", "org.kde.krunner", "/App", "display"],
            ["qdbus-qt6", "org.kde.krunner", "/App", "display"],
            ["qdbus", "org.kde.krunner", "/App", "display"],
        ):
            if shutil.which(cmd[0]):
                try:
                    subprocess.Popen(cmd)
                    self._powertoys_status.setText("")
                    return
                except OSError:
                    continue
        self._powertoys_status.setText("KRunner is not available in this session. Press Alt+Space after signing into Plasma.")

    def _open_settings_module(self, module: str, label: str):
        for cmd in (["kcmshell6", module], ["systemsettings", module], ["systemsettings"]):
            if shutil.which(cmd[0]):
                try:
                    subprocess.Popen(cmd)
                    self._powertoys_status.setText("")
                    return
                except OSError:
                    continue
        self._powertoys_status.setText(f"Could not open {label} in this session.")

    # ── Hardware sanity ───────────────────────────────────────────────────────

    def _run_hw_sanity(self):
        if self._hw_worker is not None and self._hw_worker.isRunning():
            return
        self._hw_status.setText("Checking…")
        self._hw_status.show()
        worker = DataWorker("hw-sanity", _collect_hw_sanity)
        worker.result.connect(self._on_hw_sanity)
        self._hw_worker = worker
        _release_worker_when_finished(self, "_hw_worker", worker)
        worker.start()

    def _on_hw_sanity(self, _key: str, rows: list):
        self._clear_layout(self._hw_rows)
        if not rows:
            self._hw_status.setText("Could not run the hardware checks in this session.")
            return
        self._hw_status.hide()
        printer_missing = False
        for status, title, text in rows:
            if title == "Printer" and status == "warn":
                printer_missing = True
            self._hw_rows.addWidget(self._make_migration_row(status, title, text))
        self._hw_printer_btn.setVisible(printer_missing)

    # ── Copy My Files ─────────────────────────────────────────────────────────

    def _set_files_status(self, text: str, obj: str = "card-copy"):
        self._files_status.setText(text)
        self._files_status.setObjectName(obj)
        _restyle(self._files_status)

    def _populate_files_card(self, partitions: list):
        if self._files_copy_worker is not None and self._files_copy_worker.isRunning():
            return  # don't yank the folder list out from under a running copy
        self._files_profiles = [
            (part, prof)
            for part in partitions
            for prof in (part.get("user_profiles") or [])
        ]
        self._files_profile_combo.blockSignals(True)
        self._files_profile_combo.clear()
        for part, prof in self._files_profiles:
            where = part.get("label") or part.get("device") or "PC drive"
            self._files_profile_combo.addItem(f"{prof['name']} — {where}")
        self._files_profile_combo.blockSignals(False)
        if not self._files_profiles:
            self._files_intro.setText(
                "No Windows user folders found. If the drive is hibernated, boot the other system once, "
                "choose a full Shut Down, then rescan."
            )
            self._files_profile_combo.hide()
            self._files_copy_btn.hide()
            self._files_space_lbl.setText("")
            self._clear_layout(self._files_rows)
            self._files_checks = []
            return
        self._files_intro.setText(
            "Pick the Windows user to copy from, tick the folders you want, then start the copy. "
            "The Windows side is never modified, and newer files already in your home folder are kept."
        )
        self._files_profile_combo.show()
        self._files_copy_btn.show()
        self._set_files_status("")
        self._files_profile_combo.setCurrentIndex(0)
        self._on_files_profile_changed(0)

    def _on_files_profile_changed(self, idx: int):
        self._clear_layout(self._files_rows)
        self._files_checks = []
        if not (0 <= idx < len(self._files_profiles)):
            return
        _part, prof = self._files_profiles[idx]
        home = os.path.expanduser("~")
        for folder in prof.get("folders") or []:
            src = os.path.join(prof["path"], folder)
            dst = _windows_folder_dest(folder)
            cb = QCheckBox(f"{folder} — calculating size… → {dst.replace(home, '~', 1)}")
            # Downloads is mostly installer debris; everything else defaults on.
            cb.setChecked(folder != "Downloads")
            self._files_checks.append((cb, folder, src, dst))
            self._files_rows.addWidget(cb)
        free = shutil.disk_usage(home).free
        self._files_space_lbl.setText(f"Free space in your home folder: {_human_bytes(free)}.")
        key = prof["path"]
        self._files_sizes_key = key
        cached = self._folder_sizes_cache.get(key)
        if cached is not None:
            self._apply_folder_sizes(cached)
            return
        if key in self._files_sizes_workers and self._files_sizes_workers[key].isRunning():
            return
        paths = {folder: src for _, folder, src, _ in self._files_checks}
        worker = DataWorker(key, _folder_sizes_calc(paths))
        worker.result.connect(self._on_folder_sizes)
        self._files_sizes_workers[key] = worker
        worker.finished.connect(lambda w=worker, k=key: (self._files_sizes_workers.pop(k, None), w.deleteLater()))
        worker.start()

    def _on_folder_sizes(self, key: str, sizes: dict):
        self._folder_sizes_cache[key] = sizes
        if key == self._files_sizes_key:
            self._apply_folder_sizes(sizes)

    def _apply_folder_sizes(self, sizes: dict):
        home = os.path.expanduser("~")
        for cb, folder, _src, dst in self._files_checks:
            size = sizes.get(folder, -1)
            size_txt = _human_bytes(size) if size >= 0 else "size unknown"
            cb.setText(f"{folder} — {size_txt} → {dst.replace(home, '~', 1)}")

    def _start_files_copy(self):
        if self._files_copy_worker is not None and self._files_copy_worker.isRunning():
            return
        jobs = [(folder, src, dst) for cb, folder, src, dst in self._files_checks if cb.isChecked()]
        if not jobs:
            self._set_files_status("Tick at least one folder to copy.", "status-warn")
            return
        sizes = self._folder_sizes_cache.get(self._files_sizes_key) or {}
        needed = sum(s for s in (sizes.get(folder, -1) for folder, _, _ in jobs) if s > 0)
        free = shutil.disk_usage(os.path.expanduser("~")).free
        if needed > free:
            self._set_files_status(
                f"Not enough free space: the selected folders hold {_human_bytes(needed)} "
                f"but only {_human_bytes(free)} is free in your home folder.", "status-err")
            return
        for cb, *_ in self._files_checks:
            cb.setEnabled(False)
        self._files_profile_combo.setEnabled(False)
        self._files_copy_btn.setEnabled(False)
        self._files_cancel_btn.show()
        self._files_progress.setValue(0)
        self._files_progress.show()
        self._set_files_status("Starting copy…")
        worker = UserFilesCopyWorker(jobs)
        worker.status.connect(self._files_status.setText)
        worker.overall.connect(self._files_progress.setValue)
        worker.done.connect(self._on_files_copy_done)
        self._files_copy_worker = worker
        _release_worker_when_finished(self, "_files_copy_worker", worker)
        worker.start()

    def _cancel_files_copy(self):
        worker = self._files_copy_worker
        if worker is not None and worker.isRunning():
            self._files_cancel_btn.setEnabled(False)
            self._set_files_status("Cancelling…", "status-warn")
            worker.stop()

    def _on_files_copy_done(self, ok: int, failed: int, cancelled: bool):
        self._files_progress.hide()
        self._files_cancel_btn.hide()
        self._files_cancel_btn.setEnabled(True)
        self._files_copy_btn.setEnabled(True)
        self._files_profile_combo.setEnabled(True)
        for cb, *_ in self._files_checks:
            cb.setEnabled(True)
        if cancelled:
            self._set_files_status(
                "Copy cancelled. Files copied so far are kept; run it again to resume.", "status-warn")
        elif failed:
            self._set_files_status(
                f"Copied {ok} folder(s); {failed} had errors. If the other system wasn't shut down fully, "
                "boot it once, choose Shut Down, and try again.", "status-err")
        else:
            self._set_files_status(f"✓ Copied {ok} folder(s) into your home folder.", "status-ok")

    # ── Browser bookmarks ─────────────────────────────────────────────────────

    def _start_bookmark_scan(self, partitions: list):
        profiles = [prof for part in partitions for prof in (part.get("user_profiles") or [])]
        self._clear_layout(self._bm_rows)
        self._bm_export_btn.hide()
        self._bm_show_btn.hide()
        if not profiles:
            self._bm_status.setText("No Windows user profiles found — nothing to read bookmarks from.")
            return
        if self._bm_worker is not None and self._bm_worker.isRunning():
            return
        self._bm_status.setText("Looking for browser bookmarks…")
        worker = DataWorker("bookmarks", lambda: _scan_windows_bookmarks(profiles))
        worker.result.connect(self._on_bookmarks_found)
        self._bm_worker = worker
        _release_worker_when_finished(self, "_bm_worker", worker)
        worker.start()

    def _on_bookmarks_found(self, _key: str, sources: list):
        self._bm_sources = sources
        self._clear_layout(self._bm_rows)
        if not sources:
            self._bm_status.setText("No browser bookmarks found on the scanned drives.")
            return
        total = sum(len(src["entries"]) for src in sources)
        self._bm_status.setText(
            f"Found {total} bookmark{'s' if total != 1 else ''} in "
            f"{len(sources)} browser profile{'s' if len(sources) != 1 else ''}:"
        )
        for src in sources:
            self._bm_rows.addWidget(self._make_migration_row(
                "ok", src["browser"],
                f"{len(src['entries'])} bookmarks — Windows user {src['user']}",
            ))
        self._bm_export_btn.show()

    def _export_bookmarks(self):
        if not self._bm_sources:
            return
        dest = os.path.join(_windows_folder_dest("Documents"), "Windows Bookmarks.html")
        try:
            total = _write_bookmarks_html(self._bm_sources, dest)
        except OSError as exc:
            self._bm_status.setText(f"Could not write the bookmarks file: {exc}")
            return
        self._bm_dest = dest
        home = os.path.expanduser("~")
        self._bm_status.setText(
            f"✓ Saved {total} bookmarks to {dest.replace(home, '~', 1)}. In your browser, open "
            "the bookmark manager (Ctrl+Shift+O) and choose Import bookmarks from HTML."
        )
        self._bm_show_btn.show()

    # ── PC drive extras ──────────────────────────────────────────────────

    def _start_extras_scan(self, partitions: list):
        if self._extras_worker is not None and self._extras_worker.isRunning():
            return
        self._extras = {}
        usable = [
            part for part in partitions
            if part.get("mountpoint") or part.get("user_profiles")
        ]
        if not usable:
            no_drive = "No readable PC drive — scan or unlock one above first."
            for lbl in (self._wp_status, self._fonts_status, self._saves_status,
                        self._sticky_status, self._rdp_status):
                lbl.setText(no_drive)
            for widget in (self._wp_combo, self._wp_apply_btn, self._fonts_btn,
                           self._saves_btn, self._sticky_btn, self._rdp_btn):
                widget.hide()
            self._clear_layout(self._saves_rows)
            return
        for lbl in (self._wp_status, self._fonts_status, self._saves_status,
                    self._sticky_status, self._rdp_status):
            lbl.setText("Looking on the PC drive…")
        worker = DataWorker("win-extras", lambda: _scan_windows_extras(usable))
        worker.result.connect(self._on_extras)
        worker.failed.connect(
            lambda _key, message: self._wp_status.setText(
                f"Could not read the PC drive: {message}"))
        self._extras_worker = worker
        _release_worker_when_finished(self, "_extras_worker", worker)
        worker.start()

    def _on_extras(self, _key: str, extras: dict):
        self._extras = extras

        wallpapers = extras.get("wallpapers") or []
        self._wp_combo.clear()
        if wallpapers:
            for item in wallpapers:
                self._wp_combo.addItem(f"Wallpaper of Windows user {item['user']}", item["path"])
            self._wp_combo.setVisible(len(wallpapers) > 1)
            self._wp_apply_btn.show()
            self._wp_status.setText(
                f"Found the desktop wallpaper for {len(wallpapers)} Windows "
                f"user{'s' if len(wallpapers) != 1 else ''}."
            )
        else:
            self._wp_combo.hide()
            self._wp_apply_btn.hide()
            self._wp_status.setText("No cached wallpaper found on the PC drive.")

        fonts = extras.get("fonts") or {}
        if fonts.get("count"):
            self._fonts_btn.show()
            self._fonts_status.setText(
                f"Found {fonts['count']} font files ({_human_bytes(fonts['bytes'])}) "
                "in the system font folders."
            )
        else:
            self._fonts_btn.hide()
            self._fonts_status.setText("No font folders found on the PC drive.")

        saves = extras.get("saves") or []
        self._clear_layout(self._saves_rows)
        if saves:
            for item in saves[:8]:
                where = f"Windows user {item['user']}" if item["user"] else "Drive-level launcher folder"
                self._saves_rows.addWidget(self._make_migration_row("ok", item["label"], where))
            if len(saves) > 8:
                self._saves_rows.addWidget(self._make_migration_row(
                    "dim", f"+{len(saves) - 8} more", "All found locations are copied together."))
            self._saves_btn.show()
            self._saves_status.setText(
                f"Found {len(saves)} likely save location{'s' if len(saves) != 1 else ''}:"
            )
        else:
            self._saves_btn.hide()
            self._saves_status.setText("No game save folders found on the PC drive.")

        sticky = extras.get("sticky") or []
        total_notes = sum(len(src["notes"]) for src in sticky)
        if total_notes:
            self._sticky_btn.show()
            users = ", ".join(src["user"] for src in sticky)
            self._sticky_status.setText(
                f"Found {total_notes} sticky note{'s' if total_notes != 1 else ''} "
                f"from another system user{'s' if len(sticky) != 1 else ''} {users}."
            )
        else:
            self._sticky_btn.hide()
            self._sticky_status.setText("No Sticky Notes found on the PC drive.")

        rdp = extras.get("rdp") or []
        if rdp:
            self._rdp_btn.show()
            preview = ", ".join(f"{c['name']} ({c['host']})" for c in rdp[:4])
            if len(rdp) > 4:
                preview += f", +{len(rdp) - 4} more"
            self._rdp_status.setText(
                f"Found {len(rdp)} saved connection{'s' if len(rdp) != 1 else ''}: {preview}"
            )
        else:
            self._rdp_btn.hide()
            self._rdp_status.setText("No saved .rdp connection files found on the PC drive.")

    def _apply_windows_wallpaper(self):
        src = self._wp_combo.currentData()
        if not src:
            wallpapers = self._extras.get("wallpapers") or []
            src = wallpapers[0]["path"] if wallpapers else ""
        if not src:
            return
        dest_dir = _windows_folder_dest("Pictures")
        dest = os.path.join(dest_dir, "Windows Wallpaper" + _image_extension(src))
        try:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(src, dest)
        except OSError as exc:
            self._wp_status.setText(f"Could not copy the wallpaper: {exc}")
            return
        home = os.path.expanduser("~")
        shown = dest.replace(home, "~", 1)
        if shutil.which("plasma-apply-wallpaperimage"):
            result = _run_command(["plasma-apply-wallpaperimage", dest], timeout=30)
            if result is not None and result.returncode == 0:
                self._wp_status.setText(f"✓ Wallpaper applied — saved to {shown}.")
                return
        self._wp_status.setText(
            f"✓ Saved to {shown}. Right-click the desktop → Configure Desktop and "
            "Wallpaper to apply it."
        )

    def _copy_fonts_clicked(self):
        if self._fonts_copy_worker is not None and self._fonts_copy_worker.isRunning():
            return
        dirs = list((self._extras.get("fonts") or {}).get("dirs") or [])
        if not dirs:
            return
        self._fonts_btn.setEnabled(False)
        self._fonts_status.setText("Copying fonts…")
        worker = DataWorker("fonts-copy", lambda: _copy_windows_fonts(dirs))

        def _done(_key: str, result: tuple):
            copied, skipped = result
            self._fonts_btn.setEnabled(True)
            extra = f" ({skipped} already present)" if skipped else ""
            self._fonts_status.setText(
                f"✓ Installed {copied} fonts{extra}. Apps pick them up immediately; "
                "documents now render with their original fonts."
            )
        worker.result.connect(_done)
        worker.failed.connect(
            lambda _key, message: (
                self._fonts_btn.setEnabled(True),
                self._fonts_status.setText(f"Could not copy fonts: {message}"),
            ))
        self._fonts_copy_worker = worker
        _release_worker_when_finished(self, "_fonts_copy_worker", worker)
        worker.start()

    def _copy_saves_clicked(self):
        if self._saves_copy_worker is not None and self._saves_copy_worker.isRunning():
            return
        saves = list(self._extras.get("saves") or [])
        if not saves:
            return
        self._saves_btn.setEnabled(False)
        self._saves_status.setText("Copying save folders…")
        worker = DataWorker("saves-copy", lambda: _copy_game_saves(saves))

        def _done(_key: str, result: tuple):
            ok, failed, base = result
            self._saves_btn.setEnabled(True)
            home = os.path.expanduser("~")
            text = f"✓ Copied {ok} save folder{'s' if ok != 1 else ''} to {base.replace(home, '~', 1)}."
            if failed:
                text += f" {failed} could not be read — if the other system wasn't fully shut down, boot it once and retry."
            self._saves_status.setText(text)
            self._saves_show_btn.show()
        worker.result.connect(_done)
        worker.failed.connect(
            lambda _key, message: (
                self._saves_btn.setEnabled(True),
                self._saves_status.setText(f"Could not copy saves: {message}"),
            ))
        self._saves_copy_worker = worker
        _release_worker_when_finished(self, "_saves_copy_worker", worker)
        worker.start()

    def _export_sticky_clicked(self):
        sticky = self._extras.get("sticky") or []
        if not sticky:
            return
        try:
            count, base = _export_sticky_notes(sticky)
        except OSError as exc:
            self._sticky_status.setText(f"Could not export the notes: {exc}")
            return
        home = os.path.expanduser("~")
        self._sticky_status.setText(
            f"✓ Exported {count} note{'s' if count != 1 else ''} to {base.replace(home, '~', 1)}."
        )
        self._sticky_show_btn.show()

    def _import_rdp_clicked(self):
        rdp = self._extras.get("rdp") or []
        if not rdp:
            return
        try:
            added, dupes = _import_rdp_bookmarks(rdp)
        except Exception as exc:
            self._rdp_status.setText(f"Could not write the KRDC bookmarks: {exc}")
            return
        text = f"✓ Added {added} connection{'s' if added != 1 else ''} to KRDC bookmarks."
        if dupes:
            text += f" {dupes} already existed."
        self._rdp_status.setText(text)
        self._rdp_open_btn.show()

    # ── WSL equivalent ────────────────────────────────────────────────────────

    def _create_wsl_box(self):
        if self._wsl_worker is not None and self._wsl_worker.isRunning():
            return
        self._wsl_create_btn.setEnabled(False)
        self._wsl_status.setText(
            "Creating the Ubuntu box — the first run downloads the image (a few hundred MB)…"
        )
        script = (
            "set -e\n"
            "command -v distrobox >/dev/null 2>&1 || { echo 'distrobox is not installed.'; exit 1; }\n"
            "if distrobox list --no-color 2>/dev/null | awk -F'|' '{print $2}' | grep -qw ubuntu; then\n"
            "    echo 'already exists'\n"
            "    exit 0\n"
            "fi\n"
            "distrobox create --image ubuntu:24.04 --name ubuntu --yes\n"
        )
        worker = Worker(["bash", "-c", script])

        def _done(code: int):
            self._wsl_create_btn.setEnabled(True)
            if code == 0:
                self._wsl_status.setText(
                    "✓ Ubuntu box ready. Open Ubuntu Terminal drops you at a bash prompt "
                    "with apt available — your home folder is shared with KythOS."
                )
            else:
                self._wsl_status.setText(
                    "Could not create the Ubuntu box. Check the network connection and try again."
                )
        worker.done.connect(_done)
        self._wsl_worker = worker
        _release_worker_when_finished(self, "_wsl_worker", worker)
        worker.start()

    def _open_wsl_terminal(self):
        if not shutil.which("konsole"):
            self._wsl_status.setText("Konsole is not available in this session.")
            return
        subprocess.Popen(["konsole", "-e", "distrobox", "enter", "ubuntu"])
        self._wsl_status.setText(
            "If the box doesn't exist yet, the terminal will say so — use Create Ubuntu Box first."
        )

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _clear_drive_rows(self):
        self._clear_layout(self._drive_rows)

    def _scan_windows_drives(self):
        if self._worker and self._worker.isRunning():
            return
        self._clear_drive_rows()
        self._drive_progress.show()
        self._drive_status.setText("Scanning NTFS partitions…")
        self._drive_status.setObjectName("subheading")
        _restyle(self._drive_status)
        self._worker = WindowsLibraryWorker()
        self._worker.result.connect(self._on_windows_drives)
        self._worker.start()

    def _on_windows_drives(self, partitions: list):
        self._drive_progress.hide()
        _finish_worker(self)
        if not partitions:
            self._drive_status.setText("No Windows/NTFS partitions found.")
            self._drive_status.setObjectName("status-warn")
            self._migration_score_lbl.setText("Switch readiness: 2/5. Install your launchers and Ludusavi, then connect your PC drive or cloud backup when ready.")
            _restyle(self._drive_status)
            self._populate_files_card([])
            self._start_bookmark_scan([])
            self._start_extras_scan([])
            return
        self._drive_status.setText(f"Found {len(partitions)} Windows-style partition{'s' if len(partitions) != 1 else ''}.")
        self._drive_status.setObjectName("status-ok")
        _restyle(self._drive_status)
        locked = sum(1 for p in partitions if p.get("is_bitlocker"))
        clean = sum(1 for p in partitions if not p.get("is_dirty") and not p.get("is_hibernated") and not p.get("is_bitlocker"))
        steam = sum(len(p.get("steam_paths") or []) for p in partitions)
        profiles = sum(len(p.get("user_profiles") or []) for p in partitions)
        score = 2 + (1 if clean else 0) + (1 if steam else 0) + (1 if profiles else 0)
        score_text = (
            f"Switch readiness: {score}/5. Found {clean} safely readable drive(s), "
            f"{steam} Steam folder(s), and {profiles} Windows user profile(s). "
            "Back up saves with Ludusavi before copying large libraries."
        )
        if locked:
            score_text += (
                f" {locked} drive(s) are BitLocker-encrypted — unlock them below "
                "to copy files and bookmarks."
            )
        self._migration_score_lbl.setText(score_text)
        for part in partitions:
            self._drive_rows.addWidget(self._make_drive_row(part))
        self._populate_files_card(partitions)
        self._start_bookmark_scan(partitions)
        self._start_extras_scan(partitions)

    def _run_ujust(self, recipe: str, btn: QPushButton):
        btn.setEnabled(False)
        orig = btn.text()
        btn.setText("Running…")
        worker = Worker(["bash", "-c", f"ujust {recipe}"])
        def _done(code: int, b=btn, o=orig):
            b.setEnabled(True)
            b.setText("✓ Done" if code == 0 else o)
        worker.done.connect(_done)
        worker.start()
        self._worker = worker

    def _make_drive_row(self, part: dict) -> QFrame:
        if part.get("is_bitlocker"):
            return self._make_bitlocker_row(part)
        status = "warn" if part.get("is_dirty") or part.get("is_hibernated") else "ok"
        label = part.get("label") or part.get("device") or "PC drive"
        if part.get("windows_root"):
            label = f"Windows (C:) — {label}" if part.get("label") else "Windows (C:)"
        mount = part.get("mountpoint") or "not mounted"
        steam_count = len(part.get("steam_paths") or [])
        profile_count = len(part.get("user_profiles") or [])
        summary = (
            f"{part.get('device', '')} · {part.get('size', '')} · {mount} · "
            f"{profile_count} user profile{'s' if profile_count != 1 else ''} · "
            f"{steam_count} Steam folder{'s' if steam_count != 1 else ''}"
        )
        if part.get("is_hibernated"):
            summary += " · hibernated"
        elif part.get("is_dirty"):
            summary += " · needs Windows shutdown"
        row = self._make_migration_row(status, label, summary)
        layout = row.layout()
        if part.get("mountpoint"):
            open_btn = QPushButton("Open Drive")
            open_btn.clicked.connect(
                lambda _=False, path=part["mountpoint"]: QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            )
            layout.addWidget(open_btn)
        profiles = part.get("user_profiles") or []
        if profiles:
            profile = profiles[0]
            files_btn = QPushButton("Open Windows Files")
            files_btn.clicked.connect(
                lambda _=False, path=profile["path"]: QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            )
            files_btn.setToolTip(", ".join(profile.get("folders") or []))
            layout.addWidget(files_btn)
        steam_paths = part.get("steam_paths") or []
        if steam_paths:
            steam_btn = QPushButton("Open Steam Library")
            steam_btn.setToolTip(
                "Read-only browsing is fine. Don't add this folder as a Steam library on "
                "KythOS — copy the games to your Linux disk instead."
            )
            steam_btn.clicked.connect(
                lambda _=False, path=steam_paths[0]: QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            )
            layout.addWidget(steam_btn)
        gaming_btn = QPushButton("Copy Games to KythOS")
        gaming_btn.setToolTip("Opens Gaming → Steam Library migration: scans this drive and copies games to your Linux disk.")
        gaming_btn.clicked.connect(lambda _=False: self._navigate("Gaming"))
        layout.addWidget(gaming_btn)
        return row

    def _make_bitlocker_row(self, part: dict) -> QFrame:
        label = part.get("label") or part.get("device") or "PC drive"
        summary = (
            f"{part.get('device', '')} · {part.get('size', '')} · "
            "locked with BitLocker — unlock to copy files, bookmarks, and games"
        )
        row = self._make_migration_row("warn", f"{label} (BitLocker)", summary)
        unlock_btn = QPushButton("Unlock Drive…")
        unlock_btn.setObjectName("primary")
        unlock_btn.setToolTip(
            "Enter your BitLocker password or the 48-digit recovery key. "
            "Find the recovery key at aka.ms/myrecoverykey (sign in with the "
            "Microsoft account used on the Windows PC)."
        )
        unlock_btn.clicked.connect(
            lambda _=False, d=part.get("device", ""), b=unlock_btn: self._unlock_bitlocker(d, b)
        )
        row.layout().addWidget(unlock_btn)
        return row

    def _unlock_bitlocker(self, dev: str, btn: QPushButton):
        if not dev:
            return
        key, ok = QInputDialog.getText(
            self, "Unlock BitLocker drive",
            f"Enter the BitLocker password or 48-digit recovery key for {dev}.\n"
            "Recovery key: aka.ms/myrecoverykey (Microsoft account of the Windows PC).",
            QLineEdit.EchoMode.Password,
        )
        key = (key or "").strip()
        if not ok or not key:
            return
        btn.setEnabled(False)
        btn.setText("Unlocking…")
        self._drive_status.setText(f"Unlocking {dev}…")
        self._drive_status.setObjectName("subheading")
        _restyle(self._drive_status)
        worker = DataWorker("bitlocker", lambda: _unlock_bitlocker_drive(dev, key))
        worker.result.connect(self._on_bitlocker_unlock)
        self._bitlocker_worker = worker
        _release_worker_when_finished(self, "_bitlocker_worker", worker)
        worker.start()

    def _on_bitlocker_unlock(self, _key: str, result: tuple):
        ok, message = result
        if ok:
            # Rescan so the now-visible NTFS partition gets the full treatment
            # (user profiles, Steam folders, bookmarks, file copy).
            self._scan_windows_drives()
        else:
            self._drive_status.setText(f"BitLocker unlock failed: {message}")
            self._drive_status.setObjectName("status-warn")
            _restyle(self._drive_status)
            self._clear_drive_rows()
            self._on_windows_drives_requery()

    def _on_windows_drives_requery(self):
        """Rebuild drive rows without resetting status (after failed unlock)."""
        worker = WindowsLibraryWorker()
        worker.result.connect(lambda parts: [
            self._drive_rows.addWidget(self._make_drive_row(p)) for p in parts
        ])
        self._requery_worker = worker
        _release_worker_when_finished(self, "_requery_worker", worker)
        worker.start()
