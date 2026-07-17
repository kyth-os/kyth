import glob
import os
import shlex
import shutil
from urllib.parse import urlsplit

from .process import (
    _FLATPAK_CACHE_TTL,
    _command_stdout,
    _is_live_session,
    _probe_cached,
    _run_command,
)
from .runtime import Worker, _finish_worker  # re-exported for page imports

_IS_LIVE = _is_live_session()

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

def _installed_flatpak_ids() -> frozenset | None:
    """One `flatpak list` snapshot instead of a `flatpak info` spawn per app.
    Returns None when the listing itself fails (flatpak missing/broken)."""
    def fetch() -> frozenset | None:
        result = _run_command(["flatpak", "list", "--app", "--columns=application"], timeout=10)
        if result is None or result.returncode != 0:
            return None
        return frozenset(ln.strip() for ln in result.stdout.splitlines() if ln.strip())

    return _probe_cached("flatpak-apps", _FLATPAK_CACHE_TTL, fetch)
 # _installed_flatpak_ids

def _is_flatpak_installed(app_id: str) -> bool:
    ids = _installed_flatpak_ids()
    if ids is not None:
        return app_id in ids
    result = _run_command(["flatpak", "info", app_id], timeout=8)
    return result is not None and result.returncode == 0
 # _is_flatpak_installed

def _chromium_app_window_id(browser: str, url: str) -> str:
    """Wayland app id / X11 WM_CLASS a Chromium-family browser gives a window
    opened with --app=url: <prefix>-<host>_<path with / as _>-<profile>.
    --class/--name are ignored on Wayland, so StartupWMClass must carry this
    generated id for the task bar to match the window to its .desktop file."""
    parts = urlsplit(url)
    name = f"{parts.hostname or ''}_{parts.path or '/'}".replace("/", "_")
    return f"{_CHROMIUM_APP_ID_PREFIX[browser]}-{name}-Default"
 # _chromium_app_window_id

def _chromium_app_window_cmd(url: str) -> tuple[list[str], str] | None:
    """Build a command that opens url as a dedicated app window, plus the
    window class the browser will assign to it, or None.

    KythOS ships Brave as a Flatpak, not a native chromium-browser binary, so
    native binaries are only found on systems where the user installed one.
    If no Chromium-based browser is available, falls back to Firefox.
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

    # Fall back to Firefox if no Chromium-based browser is available
    if shutil.which("firefox"):
        return ["firefox", "--new-window", url], "firefox"
    if _is_flatpak_installed("org.mozilla.firefox"):
        return ["flatpak", "run", "org.mozilla.firefox", "--new-window", url], "org.mozilla.firefox"

    return None
 # _chromium_app_window_cmd

def flatpak_install_shell_command(app_id: str, extra_cmd: str = "") -> str:
    """Shell command that ensures Flathub exists then installs *app_id*."""
    cmd = (
        "flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"
        f" && flatpak install -y --or-update flathub {shlex.quote(app_id)}"
    )
    if extra_cmd:
        cmd += f" && {extra_cmd}"
    return cmd
 # flatpak_install_shell_command


def _install_flatpak_inline(owner: object, btn, app_id: str, name: str,
                            extra_cmd: str = "", done_cb=None) -> None:
    """Compat wrapper — UI implementation lives in ``kyth_welcome.actions``."""
    from ..actions import _install_flatpak_inline as _ui_install

    return _ui_install(owner, btn, app_id, name, extra_cmd=extra_cmd, done_cb=done_cb)
 # _install_flatpak_inline

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
 # _first_run_app_setup_state

def _davinci_flatpak_app_id() -> str | None:
    for app_id in (
        "com.blackmagic.Resolve",
        "com.blackmagic.ResolveStudio",
        "com.blackmagicdesign.resolve",
    ):
        if _is_flatpak_installed(app_id):
            return app_id
    return None
 # _davinci_flatpak_app_id

def _davinci_download_dir() -> str:
    candidate = _command_stdout(["xdg-user-dir", "DOWNLOAD"])
    if candidate:
        candidate = os.path.expanduser(candidate)
        if os.path.isdir(candidate):
            return candidate
    return os.path.expanduser("~/Downloads")
 # _davinci_download_dir

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
 # _davinci_zip_candidates


_APPSTREAM_CACHE_PATH = os.path.expanduser("~/.cache/kyth-appstream.json")


def _ui_lang() -> str:
    lang = os.environ.get("LANG", "en")
    return lang.split(".")[0].split("_")[0]


def _as_localized(parent, tag: str, lang: str) -> str:
    import xml.etree.ElementTree as ET
    if parent is None:
        return ""
    exact = None
    base = lang.split("-")[0]
    base_match = None
    untagged = None
    first = None

    for el in parent.findall(tag):
        if first is None and el.text:
            first = el.text.strip()
        el_lang = el.get("{http://www.w3.org/XML/1998/namespace}lang")
        if not el_lang:
            if el.text:
                untagged = el.text.strip()
            continue
        text = el.text.strip() if el.text else ""
        if el_lang == lang:
            exact = text
        elif el_lang == base and base_match is None:
            base_match = text
    return exact or base_match or untagged or first or ""


def _as_localized_desc(component, lang: str) -> str:
    import xml.etree.ElementTree as ET
    desc_node = component.find("description")
    if desc_node is None:
        return ""

    def _extract(node) -> str:
        parts = []
        for child in node:
            if child.tag == "p" and child.text:
                parts.append(child.text.strip() + "\n")
            elif child.tag == "ul":
                for li in child.findall("li"):
                    if li.text:
                        parts.append(" - " + li.text.strip() + "\n")
        return "".join(parts).strip()

    exact = None
    base = lang.split("-")[0]
    base_match = None
    untagged = None
    first = None

    for el in component.findall("description"):
        if first is None:
            first = _extract(el)
        el_lang = el.get("{http://www.w3.org/XML/1998/namespace}lang")
        if not el_lang:
            untagged = _extract(el)
            continue
        text = _extract(el)
        if el_lang == lang:
            exact = text
        elif el_lang == base and base_match is None:
            base_match = text
    return exact or base_match or untagged or first or ""


def _fp_component_url(component, url_type: str) -> str:
    for url_node in component.findall("url"):
        if url_node.get("type") == url_type and url_node.text:
            return url_node.text.strip()
    return ""


def load_appstream_catalog() -> dict[str, dict]:
    import xml.etree.ElementTree as ET
    import glob
    from .config import load_json_config, save_json_config

    xml_path = "/var/lib/flatpak/appstream/flathub/x86_64/active/appstream.xml"
    if not os.path.exists(xml_path):
        matches = glob.glob("/var/lib/flatpak/appstream/flathub/x86_64/*/appstream.xml")
        xml_path = matches[0] if matches else ""
    if not xml_path:
        return {}

    try:
        xml_mtime = os.path.getmtime(xml_path)
        if os.path.exists(_APPSTREAM_CACHE_PATH):
            cache_mtime = os.path.getmtime(_APPSTREAM_CACHE_PATH)
            if cache_mtime > xml_mtime:
                cached = load_json_config(_APPSTREAM_CACHE_PATH, default=None)
                if cached:
                    return cached
    except Exception:
        pass

    catalog: dict[str, dict] = {}
    try:
        root = ET.parse(xml_path).getroot()
    except Exception:
        return {}

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
            for value in custom.findall("value"):
                if value.get("key") == "flathub::verification::verified":
                    verified = (value.text or "").strip().lower() == "true"
        releases = component.find("releases")
        version = ""
        if releases is not None:
            release = releases.find("release")
            if release is not None:
                version = release.get("version") or ""
        developer_node = component.find("developer")
        catalog[app_id] = {
            "name": _as_localized(component, "name", lang) or app_id,
            "summary": _as_localized(component, "summary", lang),
            "description": _as_localized_desc(component, lang),
            "developer": (_as_localized(developer_node, "name", lang) if developer_node is not None else (component.findtext("developer/name") or "").strip()),
            "license": (component.findtext("project_license") or "").strip(),
            "homepage": _fp_component_url(component, "homepage"),
            "categories": [
                (cat.text or "").strip()
                for cat in (categories_node.findall("category") if categories_node is not None else [])
                if (cat.text or "").strip()
            ],
            "screenshots": screenshots,
            "verified": verified,
            "version": version,
        }

    save_json_config(_APPSTREAM_CACHE_PATH, catalog)
    return catalog
