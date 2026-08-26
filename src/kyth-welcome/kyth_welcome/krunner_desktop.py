"""KRunner search entries for System Hub — one NoDisplay .desktop file per
searchable page, generated from page_registry.SEARCH_ITEMS.

KDE's own System Settings KCMs are searchable via KRunner/kickoff without
appearing in the app grid using exactly this trick: a NoDisplay=true
.desktop entry with rich Keywords=. Reusing it here makes Hub's pages
searchable from anywhere in Plasma (Alt+Space) with no custom D-Bus
runner, no resident background process, and no second copy of the search
metadata to keep in sync — SEARCH_ITEMS + get_nav_groups (already
maintained for the in-Hub search box; see windows.py's _rank_search_results)
are the only source of truth this reads from.
"""
from __future__ import annotations

from pathlib import Path

from .page_registry import SEARCH_ITEMS, descriptors_from_nav_groups, get_nav_groups

LAUNCH_BIN = "/usr/bin/kyth-welcome-launch"


def _slugify(key: str) -> str:
    slug = "".join(ch if ch.isalnum() else "-" for ch in key.lower()).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "page"


def _entry_text(key: str, title: str, description: str, terms: tuple[str, ...]) -> str:
    keywords = ";".join(dict.fromkeys((title, key, *terms)))  # de-dupe, keep order
    comment = description or "Open in Kyth Hub"
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "NoDisplay=true\n"
        f"Name=Kyth Hub: {title}\n"
        f"Comment={comment}\n"
        f"Keywords={keywords};\n"
        f'Exec={LAUNCH_BIN} --page "{key}"\n'
        "Icon=kyth-welcome\n"
        "Terminal=false\n"
        "Categories=Settings;\n"
        "X-KDE-StartupNotify=false\n"
    )


def build_entries() -> dict[str, str]:
    """Return {slug: desktop-file-content} for every page SEARCH_ITEMS
    covers — the same set MainWindow's own search box can find."""
    nav_groups = get_nav_groups(lambda _key: None)
    descriptors = descriptors_from_nav_groups(nav_groups, SEARCH_ITEMS)
    entries: dict[str, str] = {}
    for descriptor in descriptors:
        if descriptor.key not in SEARCH_ITEMS:
            continue
        slug = f"kyth-hub-{_slugify(descriptor.key)}"
        entries[slug] = _entry_text(
            descriptor.key, descriptor.title, descriptor.search_description, descriptor.search_terms
        )
    return entries


def write_desktop_entries(dest_dir: str | Path) -> list[Path]:
    """Write every entry from build_entries() into dest_dir, one file per
    page. Returns the paths written — build-time codegen, not a runtime
    concern, so this is safe to call from a Dockerfile fragment."""
    directory = Path(dest_dir)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for slug, content in build_entries().items():
        path = directory / f"{slug}.desktop"
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written
