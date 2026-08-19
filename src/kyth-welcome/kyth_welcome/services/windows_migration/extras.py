"""Windows partition extras: wallpaper, fonts, game saves, sticky notes, RDP."""
from __future__ import annotations

import glob
import logging
import os
import re
import shutil
import sqlite3
import tempfile

from kyth_welcome.services.command import run_sync

_logger = logging.getLogger(__name__)

from .storage import windows_folder_dest

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


def dir_contains_saves(root: str, max_entries: int = 1000, max_depth: int = 5) -> bool:
    """Bounded look for save-shaped content under root."""
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


_dir_contains_saves = dir_contains_saves


def scan_profile_game_saves(profile: dict) -> list[dict]:
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
            if dir_contains_saves(entry.path):
                hits.append({
                    "user": user, "src": entry.path,
                    "label": os.path.join(os.path.basename(rel), entry.name),
                })
    return hits


_scan_profile_game_saves = scan_profile_game_saves


def best_profile_wallpaper(profile_path: str) -> str:
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


_best_profile_wallpaper = best_profile_wallpaper


def image_extension(path: str) -> str:
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


_image_extension = image_extension


def read_sticky_notes(profile_path: str) -> list[str]:
    """Read note texts from the Sticky Notes app database (plum.sqlite).

    The database is copied to a temp dir first so sqlite's WAL replay never
    touches the (possibly read-only) PC drive.
    """
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
    except (OSError, ValueError, sqlite3.Error) as exc:
        _logger.debug("read_sticky_notes failed for %s: %s", profile_path, exc, exc_info=True)
        return []
    return notes


_read_sticky_notes = read_sticky_notes


def parse_rdp_file(path: str) -> dict | None:
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


_parse_rdp_file = parse_rdp_file


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


def scan_windows_extras(partitions: list) -> dict:
    """One worker-thread pass over mounted system partitions for extras cards."""
    wallpapers: list[dict] = []
    saves: list[dict] = []
    sticky: list[dict] = []
    rdp: list[dict] = []
    font_dirs: list[str] = []
    font_count = 0
    font_bytes = 0

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
            wp = best_profile_wallpaper(prof["path"])
            if wp:
                wallpapers.append({"user": user, "path": wp})
            user_fonts = os.path.join(
                prof["path"], "AppData", "Local", "Microsoft", "Windows", "Fonts")
            count, size = _count_fonts(user_fonts)
            if count:
                font_dirs.append(user_fonts)
                font_count += count
                font_bytes += size
            saves.extend(scan_profile_game_saves(prof))
            notes = read_sticky_notes(prof["path"])
            if notes:
                sticky.append({"user": user, "notes": notes})
            for pattern in ("Desktop/*.rdp", "Desktop/*/*.rdp",
                            "Documents/*.rdp", "Documents/*/*.rdp",
                            "Downloads/*.rdp"):
                for path in glob.glob(os.path.join(prof["path"], pattern)):
                    parsed = parse_rdp_file(path)
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


_scan_windows_extras = scan_windows_extras


def copy_windows_fonts(font_dirs: list[str]) -> tuple[int, int]:
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
    run_sync(["fc-cache", "-f", dest], capture_output=True, timeout=120, check=False)
    return copied, skipped


_copy_windows_fonts = copy_windows_fonts


def copy_game_saves(saves: list[dict]) -> tuple[int, int, str]:
    """Copy rescued save folders under ~/Documents; returns (ok, failed, dest)."""
    base = os.path.join(windows_folder_dest("Documents"), "Rescued Game Saves")
    ok = failed = 0
    for item in saves:
        sub = os.path.join(item["user"], item["label"]) if item["user"] else item["label"]
        target = os.path.join(base, sub)
        try:
            shutil.copytree(item["src"], target, dirs_exist_ok=True)
            ok += 1
        except (OSError, ValueError) as exc:
            _logger.debug("copy_game_saves failed for %s: %s", item.get("src"), exc, exc_info=True)
            failed += 1
    return ok, failed, base


_copy_game_saves = copy_game_saves


def export_sticky_notes(sticky: list[dict]) -> tuple[int, str]:
    """Write each note as a text file; returns (count, folder)."""
    base = os.path.join(windows_folder_dest("Documents"), "Sticky Notes")
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


_export_sticky_notes = export_sticky_notes


def import_rdp_bookmarks(connections: list[dict]) -> tuple[int, int]:
    """Add rdp:// bookmarks to KRDC's bookmarks.xbel; returns (added, dupes)."""
    import xml.etree.ElementTree as std_ET
    try:
        import defusedxml.ElementTree as ET
    except ImportError:
        ET = std_ET
    path = os.path.expanduser("~/.local/share/krdc/bookmarks.xbel")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path):
        tree = ET.parse(path)
        root = tree.getroot()
    else:
        root = std_ET.Element("xbel", {"folded": "no"})
        tree = std_ET.ElementTree(root)
    existing = {bm.get("href") for bm in root.iter("bookmark")}
    added = dupes = 0
    for conn in connections:
        user_part = f"{conn['username']}@" if conn["username"] else ""
        href = f"rdp://{user_part}{conn['host']}"
        if href in existing:
            dupes += 1
            continue
        bm = std_ET.SubElement(root, "bookmark", {"href": href})
        title = std_ET.SubElement(bm, "title")
        title.text = conn["name"]
        existing.add(href)
        added += 1
    if added:
        tree.write(path, encoding="UTF-8", xml_declaration=True)
    return added, dupes


_import_rdp_bookmarks = import_rdp_bookmarks
