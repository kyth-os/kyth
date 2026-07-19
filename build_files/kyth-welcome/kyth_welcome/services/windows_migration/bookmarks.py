"""Read Windows browser bookmarks and export Netscape HTML for import."""
from __future__ import annotations

import glob
import html
import json
import os
import shutil
import sqlite3
import tempfile

_CHROMIUM_BOOKMARK_STORES = (
    ("Chrome", "AppData/Local/Google/Chrome/User Data"),
    ("Edge", "AppData/Local/Microsoft/Edge/User Data"),
    ("Brave", "AppData/Local/BraveSoftware/Brave-Browser/User Data"),
    ("Vivaldi", "AppData/Local/Vivaldi/User Data"),
)
# Opera keeps its Bookmarks file directly in the profile dir, no "User Data" level.
_OPERA_BOOKMARK_DIR = "AppData/Roaming/Opera Software/Opera Stable"


def read_chromium_bookmarks(path: str) -> list[tuple[str, str]]:
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


_read_chromium_bookmarks = read_chromium_bookmarks


def read_firefox_bookmarks(places_path: str) -> list[tuple[str, str]]:
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


_read_firefox_bookmarks = read_firefox_bookmarks


def scan_windows_bookmarks(profiles: list[dict]) -> list[dict]:
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
                entries = read_chromium_bookmarks(path)
            except Exception:
                continue
            if not entries:
                continue
            prof_dir = os.path.basename(os.path.dirname(path))
            label = browser if prof_dir in ("Default", "Opera Stable") else f"{browser} ({prof_dir})"
            sources.append({"browser": label, "user": user, "entries": entries})
        for places in glob.glob(os.path.join(base, "AppData/Roaming/Mozilla/Firefox/Profiles", "*", "places.sqlite")):
            try:
                entries = read_firefox_bookmarks(places)
            except Exception:
                continue
            if entries:
                sources.append({"browser": "Firefox", "user": user, "entries": entries})
    return sources


_scan_windows_bookmarks = scan_windows_bookmarks


def write_bookmarks_html(sources: list[dict], dest: str) -> int:
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


_write_bookmarks_html = write_bookmarks_html
