"""Local Flathub AppStream catalog parsing and caching — offline via 1h TTL cache."""

from __future__ import annotations

import glob
import os
from functools import lru_cache

from .config import load_json_config, save_json_config

_APPSTREAM_CACHE_PATH = os.path.expanduser("~/.cache/kyth-appstream.json")


def _ui_lang() -> str:
    lang = os.environ.get("LANG", "en")
    return lang.split(".")[0].split("_")[0]


def _as_localized(parent, tag: str, lang: str) -> str:
    if parent is None:
        return ""
    exact = None
    base = lang.split("-")[0]
    base_match = None
    untagged = None
    first = None
    for element in parent.findall(tag):
        if first is None and element.text:
            first = element.text.strip()
        element_lang = element.get("{http://www.w3.org/XML/1998/namespace}lang")
        if not element_lang:
            if element.text:
                untagged = element.text.strip()
            continue
        text = element.text.strip() if element.text else ""
        if element_lang == lang:
            exact = text
        elif element_lang == base and base_match is None:
            base_match = text
    return exact or base_match or untagged or first or ""


def _as_localized_desc(component, lang: str) -> str:
    if component.find("description") is None:
        return ""

    def extract(node) -> str:
        parts = []
        for child in node:
            if child.tag == "p" and child.text:
                parts.append(child.text.strip() + "\n")
            elif child.tag == "ul":
                parts.extend(
                    " - " + item.text.strip() + "\n"
                    for item in child.findall("li")
                    if item.text
                )
        return "".join(parts).strip()

    exact = None
    base = lang.split("-")[0]
    base_match = None
    untagged = None
    first = None
    for element in component.findall("description"):
        if first is None:
            first = extract(element)
        element_lang = element.get("{http://www.w3.org/XML/1998/namespace}lang")
        if not element_lang:
            untagged = extract(element)
            continue
        text = extract(element)
        if element_lang == lang:
            exact = text
        elif element_lang == base and base_match is None:
            base_match = text
    return exact or base_match or untagged or first or ""


def _component_url(component, url_type: str) -> str:
    for node in component.findall("url"):
        if node.get("type") == url_type and node.text:
            return node.text.strip()
    return ""


def _load_cached_catalog() -> dict | None:
    """R7: pre-parsed JSON helper — kyth-probe can write this so Hub never parses XML."""
    try:
        if os.path.exists(_APPSTREAM_CACHE_PATH):
            cached = load_json_config(_APPSTREAM_CACHE_PATH, default=None)
            if isinstance(cached, dict) and cached:
                return cached
    except Exception:
        pass
    return None


@lru_cache(maxsize=1)
def load_appstream_catalog() -> dict[str, dict]:
    try:
        import defusedxml.ElementTree as ET
    except ImportError:
        import xml.etree.ElementTree as ET  # fallback on minimal images / containers

    xml_path = "/var/lib/flatpak/appstream/flathub/x86_64/active/appstream.xml"
    if not os.path.exists(xml_path):
        matches = glob.glob("/var/lib/flatpak/appstream/flathub/x86_64/*/appstream.xml")
        xml_path = matches[0] if matches else ""
    if not xml_path:
        # Offline — use pre-parsed JSON (R7 future: kyth-probe writes this)
        cached = _load_cached_catalog()
        if cached is not None:
            return cached
        return {}
    try:
        xml_mtime = os.path.getmtime(xml_path)
        if os.path.exists(_APPSTREAM_CACHE_PATH) and os.path.getmtime(_APPSTREAM_CACHE_PATH) > xml_mtime:
            cached = load_json_config(_APPSTREAM_CACHE_PATH, default=None)
            if cached:
                return cached
    except OSError:
        pass
    try:
        root = ET.parse(xml_path).getroot()
    except Exception:
        # Parse failed — use pre-parsed JSON fallback (R7)
        cached = _load_cached_catalog()
        if cached is not None:
            return cached
        return {}

    catalog: dict[str, dict] = {}
    lang = _ui_lang()
    for component in root.findall("component"):
        app_id = (component.findtext("id") or "").strip()
        bundle = component.find("bundle")
        if not app_id or bundle is None or (bundle.get("type") or "") != "flatpak":
            continue
        categories_node = component.find("categories")
        screenshots = []
        screenshots_node = component.find("screenshots")
        if screenshots_node is not None:
            for screenshot in screenshots_node.findall("screenshot"):
                for image in screenshot.findall("image"):
                    if image.text and image.get("type") in ("thumbnail", "source"):
                        screenshots.append(image.text.strip())
                        break
        custom = component.find("custom")
        verified = False
        if custom is not None:
            verified = any(
                value.get("key") == "flathub::verification::verified"
                and (value.text or "").strip().lower() == "true"
                for value in custom.findall("value")
            )
        release = component.find("releases/release")
        developer = component.find("developer")
        catalog[app_id] = {
            "name": _as_localized(component, "name", lang) or app_id,
            "summary": _as_localized(component, "summary", lang),
            "description": _as_localized_desc(component, lang),
            "developer": _as_localized(developer, "name", lang) if developer is not None else "",
            "license": (component.findtext("project_license") or "").strip(),
            "homepage": _component_url(component, "homepage"),
            "categories": [
                (category.text or "").strip()
                for category in (categories_node.findall("category") if categories_node is not None else [])
                if (category.text or "").strip()
            ],
            "screenshots": screenshots,
            "verified": verified,
            "version": release.get("version") if release is not None else "",
        }
    save_json_config(_APPSTREAM_CACHE_PATH, catalog)
    return catalog


# W5: kyth-probe pre-warm hook — if probe wrote JSON, Hub will hit _load_cached_catalog first (see R7)
def warm_appstream_cache() -> bool:
    try:
        from kyth_shared.system.probe import read_section

        data = read_section("flatpak-apps", max_age=3600)
        if isinstance(data, dict) and data:
            save_json_config(_APPSTREAM_CACHE_PATH, data)
            return True
    except Exception:
        pass
    return False


_fp_component_url = _component_url
