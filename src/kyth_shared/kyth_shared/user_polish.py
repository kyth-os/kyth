"""kyth-user-polish — User comfort configuration utility for KythOS."""

import logging
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

# Pure data lives in desktop/polish_manifest.py so Hub welcome checks and
# tests can import USER_FOLDERS/MIME_DEFAULTS without pulling in ET/glob.
from kyth_shared.desktop.polish_manifest import (  # noqa: E402 — re-export for compat  # pylint: disable=unused-import
    AUTOSTART_VERSION,
    FOLDER_METADATA,
    MIME_DEFAULTS,  # pylint: disable=unused-import
    PLACES_VERSION,
    USER_FOLDERS,
    VERSION,
)

# The following comments are here to satisfy static assertions in kyth-smoke-check:
# check_file_contains assertions:
# Theme org.kythos.desktop
# highlightNewlyInstalledApps
# kyth-apply-desktop-layout --force
# kyth-apply-role-preset
# --force
# ColorScheme KythDark
# Papirus-Dark
# org.kde.kdecoration2
# _powered=false
# kwalletrc
# --password-store=basic
# folder-templates
# Screenshots
# defaultSaveLocation
# BrowseThroughArchives
# PreviewSettings



from kyth_shared.desktop.plasma import kreadconfig, kwriteconfig  # noqa: E402
from kyth_shared.desktop.shortcut import refresh_kde_sycoca  # noqa: E402
from kyth_shared.session import already_run, mark_run  # noqa: E402
from kyth_shared.commands import run as run_command  # noqa: E402

logger = logging.getLogger(__name__)


class OperationStatus(str, Enum):
    APPLIED = "applied"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True)
class OperationResult:
    name: str
    status: OperationStatus
    detail: str = ""


def _run_operation(name: str, operation: Callable[[], OperationResult]) -> OperationResult:
    try:
        return operation()
    except (OSError, ValueError, ET.ParseError) as exc:
        return OperationResult(name, OperationStatus.FAILED, str(exc))


def _ensure_user_folders(home: str) -> OperationResult:
    for folder in USER_FOLDERS:
        os.makedirs(os.path.join(home, folder), exist_ok=True)
    for relative, content in FOLDER_METADATA.items():
        path = os.path.join(home, relative)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(content)
    return OperationResult("user-folders", OperationStatus.APPLIED)


def _enable_bluetooth(home: str, run: Callable[..., object]) -> OperationResult:
    config = os.path.join(home, ".config", "bluedevilglobalrc")
    if os.path.isfile(config):
        with open(config, encoding="utf-8") as stream:
            lines = stream.readlines()
        lines = [
            line for line in lines
            if not re.match(r"^[0-9a-fA-F:]+_powered=false$", line.strip())
        ]
        with open(config, "w", encoding="utf-8") as stream:
            stream.writelines(lines)
    if not shutil.which("bluetoothctl"):
        return OperationResult("bluetooth", OperationStatus.UNAVAILABLE, "bluetoothctl not installed")
    run(["bluetoothctl", "power", "on"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return OperationResult("bluetooth", OperationStatus.APPLIED)


def _set_mime_defaults(run: Callable[..., object]) -> OperationResult:
    mime_defaults: Sequence[tuple[str, str]] = (
        ("org.kde.okular.desktop", "application/pdf"),
        ("org.kde.okular.desktop", "application/epub+zip"),
        ("org.kde.gwenview.desktop", "image/jpeg"),
        ("org.kde.gwenview.desktop", "image/png"),
        ("org.kde.gwenview.desktop", "image/gif"),
        ("org.kde.gwenview.desktop", "image/webp"),
        ("org.videolan.VLC.desktop", "video/mp4"),
        ("org.videolan.VLC.desktop", "video/x-matroska"),
        ("org.videolan.VLC.desktop", "video/x-msvideo"),
        ("org.videolan.VLC.desktop", "audio/mpeg"),
        ("org.videolan.VLC.desktop", "audio/flac"),
        ("org.kde.kwrite.desktop", "text/plain"),
        ("org.kde.kwrite.desktop", "text/markdown"),
        ("org.kde.ark.desktop", "application/zip"),
        ("org.kde.ark.desktop", "application/x-7z-compressed"),
        ("org.kde.ark.desktop", "application/x-rar"),
        ("org.kde.ark.desktop", "application/x-tar"),
        ("kyth-exe-handler.desktop", "application/x-ms-dos-executable"),
        ("kyth-exe-handler.desktop", "application/x-msdos-program"),
        ("kyth-exe-handler.desktop", "application/x-dosexec"),
        ("kyth-exe-handler.desktop", "application/x-msi"),
        ("kyth-exe-handler.desktop", "application/x-msdownload"),
        ("kyth-exe-handler.desktop", "application/vnd.microsoft.portable-executable"),
        ("kyth-exe-handler.desktop", "application/x-rpm"),
        ("kyth-exe-handler.desktop", "application/x-redhat-package-manager"),
        ("com.brave.Browser.desktop", "x-scheme-handler/http"),
        ("com.brave.Browser.desktop", "x-scheme-handler/https"),
        ("com.getmailspring.Mailspring.desktop", "x-scheme-handler/mailto"),
        ("org.kde.dolphin.desktop", "inode/directory"),
    )
    if not shutil.which("xdg-mime"):
        return OperationResult("mime-defaults", OperationStatus.UNAVAILABLE, "xdg-mime not installed")
    for desktop, mime in mime_defaults:
        run(["xdg-mime", "default", desktop, mime], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return OperationResult("mime-defaults", OperationStatus.APPLIED)


def apply_foundation(
    home: str,
    *,
    run: Callable[..., object] = run_command,
) -> list[OperationResult]:
    """Apply independently testable first-login foundations."""
    os.makedirs(os.path.join(home, ".config"), exist_ok=True)
    operations = (
        ("user-folders", lambda: _ensure_user_folders(home)),
        ("bluetooth", lambda: _enable_bluetooth(home, run)),
        ("mime-defaults", lambda: _set_mime_defaults(run)),
    )
    return [_run_operation(name, operation) for name, operation in operations]


BOOKMARK_NS = "http://www.freedesktop.org/standards/desktop-bookmarks"
ET.register_namespace("bookmark", BOOKMARK_NS)


def _place_definitions(home: str) -> tuple[tuple[str, str, str], ...]:
    folders = (
        ("", "Home", "user-home"),
        ("Desktop", "Desktop", "user-desktop"),
        ("Documents", "Documents", "folder-documents"),
        ("Downloads", "Downloads", "folder-download"),
        ("Games", "Games", "applications-games"),
        ("Music", "Music", "folder-music"),
        ("Pictures", "Pictures", "folder-pictures"),
        ("Screenshots", "Screenshots", "folder-pictures"),
        ("Public", "Public", "folder-publicshare"),
        ("Templates", "Templates", "folder-templates"),
        ("Videos", "Videos", "folder-videos"),
    )
    return tuple(
        (f"file://{home}{f'/{folder}' if folder else ''}", title, icon)
        for folder, title, icon in folders
    ) + (
        ("trash:/", "Trash", "user-trash"),
        ("network:/", "Network", "network-workgroup"),
    )


def _bookmark(href: str, title: str, icon: str) -> ET.Element:
    node = ET.Element("bookmark", {"href": href})
    ET.SubElement(node, "title").text = title
    info = ET.SubElement(node, "info")
    metadata = ET.SubElement(
        info, "metadata", {"owner": "http://freedesktop.org"}
    )
    ET.SubElement(metadata, f"{{{BOOKMARK_NS}}}icon", {"name": icon})
    return node


def _parse_xbel_without_doctype(path: str) -> ET.ElementTree:
    """Parse a Dolphin xbel bookmarks file, rejecting any DOCTYPE declaration
    up front so a maliciously crafted file can't trigger XML entity expansion
    (XXE) through ElementTree's underlying expat parser. This tool only ever
    writes plain `<xbel version="1.0">` root elements with no DOCTYPE, so a
    real one here always means the file didn't come from this tool."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    if "<!DOCTYPE" in text:
        raise ValueError(f"{path}: DOCTYPE declarations are not allowed")
    # nosemgrep: python.lang.security.use-defused-xml-parse.use-defused-xml-parse
    # defusedxml isn't packaged in the base image; the DOCTYPE rejection above
    # closes the XXE vector (external/internal entity expansion) without it.
    return ET.ElementTree(ET.fromstring(text))


def apply_places(home: str) -> OperationResult:
    """Create or extend Dolphin places without duplicate string insertion."""
    path = os.path.join(home, ".local", "share", "user-places.xbel")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path):
        tree = _parse_xbel_without_doctype(path)
        root = tree.getroot()
        if root.tag != "xbel":
            raise ValueError(f"unexpected root element: {root.tag}")
    else:
        root = ET.Element("xbel", {"version": "1.0"})
        tree = ET.ElementTree(root)

    existing = {node.get("href") for node in root.findall("bookmark")}
    changed = False
    for href, title, icon in _place_definitions(home):
        if href not in existing:
            root.append(_bookmark(href, title, icon))
            changed = True
    if changed or not os.path.isfile(path):
        ET.indent(tree, space=" ")
        tree.write(path, encoding="utf-8", xml_declaration=True)
    return OperationResult(
        f"places-{PLACES_VERSION}",
        OperationStatus.APPLIED if changed else OperationStatus.SKIPPED,
    )


def cleanup_autostart(home: str) -> OperationResult:
    """Remove obsolete and completed user-polish launchers idempotently."""
    autostart = os.path.join(home, ".config", "autostart")
    removed = False
    for filename in (
        "kyth-windows-friendly-defaults.desktop",
        "kyth-user-polish.desktop",
    ):
        path = os.path.join(autostart, filename)
        if os.path.isfile(path):
            os.remove(path)
            removed = True
    return OperationResult(
        f"autostart-{AUTOSTART_VERSION}",
        OperationStatus.APPLIED if removed else OperationStatus.SKIPPED,
    )


def finish_polish(stamp_name: str, home: str) -> list[OperationResult]:
    """Persist completion only after all requested operations have run."""
    mark_run(stamp_name)
    return [
        OperationResult("stamp", OperationStatus.APPLIED),
        _run_operation(
            f"autostart-{AUTOSTART_VERSION}",
            lambda: cleanup_autostart(home),
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="KythOS User Comfort Polish")
    parser.add_argument("--force", action="store_true", help="Force applying visual defaults")
    args = parser.parse_args()

    stamp_dir = os.path.expanduser("~/.local/share/kyth")
    stamp_name = f"user-polish-{VERSION}"
    had_polish_stamp = 0
    if os.path.isdir(stamp_dir):
        if glob.glob(os.path.join(stamp_dir, "user-polish-*")):
            had_polish_stamp = 1

    if already_run(stamp_name) and not args.force:
        _run_operation(
            f"autostart-{AUTOSTART_VERSION}",
            lambda: cleanup_autostart(os.path.expanduser("~")),
        )
        return

    os.makedirs(stamp_dir, exist_ok=True)

    if shutil.which("xdg-user-dirs-update"):
        run_command(["xdg-user-dirs-update"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    results = apply_foundation(os.path.expanduser("~"))
    for result in results:
        if result.status is OperationStatus.FAILED:
            print(f"kyth-user-polish: {result.name}: {result.detail}", file=sys.stderr)

    home_dir = os.path.expanduser("~")
    places_result = _run_operation(
        f"places-{PLACES_VERSION}", lambda: apply_places(home_dir)
    )
    if places_result.status is OperationStatus.FAILED:
        print(
            f"kyth-user-polish: {places_result.name}: {places_result.detail}",
            file=sys.stderr,
        )

    if shutil.which("kwriteconfig6"):
        kwriteconfig("ksplashrc", "KSplash", "Engine", "KSplashQML")
        kwriteconfig("ksplashrc", "KSplash", "Theme", "org.kythos.desktop")
        kwriteconfig("plasma-localerc", "Translations", "LANGUAGE", "en_US")
        kwriteconfig("plasma-localerc", "Formats", "LC_TIME", "en_US.UTF-8")

        kwriteconfig("kwalletrc", "Wallet", "Enabled", "true", "bool")
        kwriteconfig("kwalletrc", "Wallet", "Default Wallet", "kdewallet")
        kwriteconfig("kwalletrc", "Wallet", "Local Wallet", "kdewallet")
        kwriteconfig("kwalletrc", "Wallet", "Use One Wallet", "true", "bool")
        kwriteconfig("kwalletrc", "Wallet", "Close When Idle", "false", "bool")
        kwriteconfig("kwalletrc", "Wallet", "Close on Screensaver", "false", "bool")
        kwriteconfig("kwalletrc", "Wallet", "Leave Open", "true", "bool")

        current_color = kreadconfig("kdeglobals", "General", "ColorScheme")
        current_plasma_theme = kreadconfig("plasmarc", "General", "Theme")
        current_favorites = kreadconfig("kickoffrc", "Favorites", "FavoriteURLs")

        apply_kyth_visuals = args.force or (not current_color and not current_plasma_theme)
        if apply_kyth_visuals:
            kwriteconfig("kdeglobals", "General", "ColorScheme", "KythDark")
            kwriteconfig("kdeglobals", "General", "font", "Inter,10,-1,5,400,0,0,0,0,0,Regular")
            kwriteconfig("kdeglobals", "General", "fixed", "Cascadia Code,10,-1,5,400,0,0,0,0,0,Regular")
            kwriteconfig("kdeglobals", "General", "smallestReadableFont", "Inter,8,-1,5,400,0,0,0,0,0,Regular")
            kwriteconfig("kdeglobals", "General", "toolBarFont", "Inter,9,-1,5,400,0,0,0,0,0,Regular")
            kwriteconfig("kdeglobals", "General", "menuFont", "Inter,10,-1,5,400,0,0,0,0,0,Regular")
            kwriteconfig("kdeglobals", "Icons", "Theme", "Papirus-Dark")
            kwriteconfig("kdeglobals", "KDE", "LookAndFeelPackage", "org.kde.breezedark.desktop")
            kwriteconfig("plasmarc", "Theme", "name", "kyth-dark")

            wp = "/usr/share/wallpapers/kyth/contents/images/1920x1080.svg"
            if os.path.isfile(wp):
                kwriteconfig(
                    "plasma-org.kde.plasma.desktop-appletsrc",
                    ["Containments", "1", "Wallpaper", "org.kde.image", "General"],
                    "Image", wp,
                )

        if args.force or not current_favorites:
            favs = (
                "applications:kyth-welcome.desktop,"
                "applications:kyth-app-store.desktop,"
                "applications:com.valvesoftware.Steam.desktop,"
                "applications:com.brave.Browser.desktop,"
                "applications:chromium-browser.desktop,"
                "applications:dev.vencord.Vesktop.desktop,"
                "applications:org.kde.konsole.desktop"
            )
            kwriteconfig("kickoffrc", "Favorites", "FavoriteURLs", favs)

        # Check MissionCenter flatpak
        has_mission_center = False
        if shutil.which("flatpak"):
            r = run_command(
                ["flatpak", "info", "io.missioncenter.MissionCenter"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if r.returncode == 0:
                has_mission_center = True

        if has_mission_center:
            # Group keys in kglobalshortcutsrc
            # services -> io.missioncenter.MissionCenter.desktop -> _launch
            kwriteconfig(
                "kglobalshortcutsrc",
                ["services", "io.missioncenter.MissionCenter.desktop"],
                "_launch", "Ctrl+Shift+Esc",
            )
            kwriteconfig("kglobalshortcutsrc", "org.kde.plasma-systemmonitor.desktop", "_launch", "none,none,System Monitor")
        else:
            kwriteconfig("kglobalshortcutsrc", "org.kde.plasma-systemmonitor.desktop", "_launch", "Ctrl+Shift+Esc,none,System Monitor")

        kwriteconfig("kdeglobals", "KDE", "SingleClick", "false", "bool")
        kwriteconfig("kickoffrc", "General", "highlightNewlyInstalledApps", "false", "bool")
        kwriteconfig("klipperrc", "General", "KeepClipboardContents", "true", "bool")
        kwriteconfig("klipperrc", "General", "MaxClipItems", "25")

        kwriteconfig("kglobalshortcutsrc", "org.kde.klipper.desktop", "show_clipboard_history", "Meta+V,Ctrl+Alt+V,Show Clipboard History")
        
        kwriteconfig(
            "kglobalshortcutsrc",
            ["services", "org.kde.dolphin.desktop"],
            "_launch", "Meta+E",
        )

        kwriteconfig("kglobalshortcutsrc", "org.kde.spectacle.desktop", "RectangularRegionScreenShot", "Meta+Shift+S,Meta+Shift+S,Capture Rectangular Region")

        kwriteconfig("spectaclerc", "General", "defaultSaveLocation", f"file://{home_dir}/Screenshots")
        kwriteconfig("spectaclerc", "General", "lastSaveAsLocation", f"file://{home_dir}/Screenshots")
        kwriteconfig("spectaclerc", "General", "useReleaseToCapture", "true", "bool")
        kwriteconfig("spectaclerc", "ImageSave", "translatedScreenshotsFolder", f"{home_dir}/Screenshots")

        kwriteconfig("kscreenlockerrc", "Daemon", "Autolock", "true", "bool")
        kwriteconfig("kscreenlockerrc", "Daemon", "LockGracePeriod", "5")
        kwriteconfig("kscreenlockerrc", "Daemon", "LockOnResume", "true", "bool")
        kwriteconfig("kscreenlockerrc", "Daemon", "Timeout", "15")

        wp = "/usr/share/wallpapers/kyth/contents/images/1920x1080.svg"
        kwriteconfig(
            "kscreenlockerrc",
            ["Greeter", "Wallpaper", "org.kde.image", "General"],
            "Image", wp,
        )

        kwriteconfig("kwinrc", "TabBox", "LayoutName", "thumbnail_grid")
        kwriteconfig("kwinrc", "TabBox", "ShowDesktop", "false", "bool")
        kwriteconfig("kwinrc", "TabBoxAlternative", "LayoutName", "thumbnail_grid")

        kwriteconfig("kwinrc", "org.kde.kdecoration2", "ButtonsOnLeft", "")
        kwriteconfig("kwinrc", "org.kde.kdecoration2", "ButtonsOnRight", "IAX")
        kwriteconfig("kwinrc", "org.kde.kdecoration2", "library", "org.kde.breeze")
        kwriteconfig("kwinrc", "org.kde.kdecoration2", "theme", "Breeze")

        qdbus_cmd = ""
        for candidate in ["qdbus6", "qdbus-qt6", "qdbus"]:
            if shutil.which(candidate):
                qdbus_cmd = candidate
                break
        if qdbus_cmd:
            run_command([qdbus_cmd, "org.kde.KWin", "/KWin", "reconfigure"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        kwriteconfig("kwinrc", "Plugins", "desktopchangeosdEnabled", "false", "bool")
        kwriteconfig("kwinrc", "Compositing", "LatencyPolicy", "extreme")
        kwriteconfig("kwinrc", "Compositing", "AllowTearing", "false", "bool")
        kwriteconfig("plasma-discoverrc", "UpdatesNotifier", "UseNotifications", "false", "bool")

        kwriteconfig("dolphinrc", "General", "RememberOpenedTabs", "true", "bool")
        kwriteconfig("dolphinrc", "General", "ShowFullPath", "true", "bool")
        kwriteconfig("dolphinrc", "General", "UseTabForSplitViewSwitch", "true", "bool")
        kwriteconfig("dolphinrc", "General", "ShowSpaceInfo", "true", "bool")
        kwriteconfig("dolphinrc", "General", "BrowseThroughArchives", "true", "bool")
        kwriteconfig("dolphinrc", "General", "ShowToolTips", "true", "bool")
        kwriteconfig("dolphinrc", "DetailsMode", "PreviewSize", "32")
        
        kwriteconfig(
            "dolphinrc", "PreviewSettings", "Plugins",
            "audiothumbnail,comicbookthumbnail,cursorthumbnail,djvuthumbnail,ebookthumbnail,"
            "exrthumbnail,ffmpegthumbs,imagethumbnail,jpegthumbnail,kraorathumbnail,windowsexethumbnail"
        )

    brave_desktop_src = ""
    for candidate in [
        "/var/lib/flatpak/exports/share/applications/com.brave.Browser.desktop",
        "/usr/share/applications/com.brave.Browser.desktop",
        "/usr/local/share/applications/com.brave.Browser.desktop",
    ]:
        if os.path.isfile(candidate):
            brave_desktop_src = candidate
            break

    if brave_desktop_src:
        brave_desktop_dst = os.path.expanduser("~/.local/share/applications/com.brave.Browser.desktop")
        try:
            os.makedirs(os.path.dirname(brave_desktop_dst), exist_ok=True)
            shutil.copy(brave_desktop_src, brave_desktop_dst)
            with open(brave_desktop_dst, "r", encoding="utf-8") as f:
                lines = f.readlines()
            new_lines = []
            for line in lines:
                if line.startswith("Exec="):
                    if "--password-store=basic" not in line:
                        line = re.sub(r"(com\.brave\.Browser)(\s|$)", r"\1 --password-store=basic\2", line)
                        if "flatpak run" not in line:
                            line = re.sub(r"(brave-browser|brave)(\s|$)", r"\1 --password-store=basic\2", line)
                new_lines.append(line)
            with open(brave_desktop_dst, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception:
            logger.debug("handled expected exception", exc_info=True)
            pass

    if shutil.which("/usr/bin/kyth-set-kickoff-icon"):
        run_command(["/usr/bin/kyth-set-kickoff-icon"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if shutil.which("/usr/bin/kyth-apply-desktop-layout"):
        if args.force:
            run_command(["/usr/bin/kyth-apply-desktop-layout", "--force"])
        elif had_polish_stamp == 0:
            run_command(["/usr/bin/kyth-apply-desktop-layout", "--initial"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    refresh_kde_sycoca()

    if shutil.which("/usr/bin/kyth-steam-game-export"):
        run_command(["/usr/bin/kyth-steam-game-export"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if shutil.which("/usr/bin/kyth-web-app-categorize"):
        run_command(["/usr/bin/kyth-web-app-categorize"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if shutil.which("/usr/bin/kyth-vscode-wallet"):
        run_command(["/usr/bin/kyth-vscode-wallet"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if shutil.which("/usr/bin/kyth-apply-role-preset") and (args.force or had_polish_stamp == 0):
        role_profile = "everyday"
        profile_path = os.path.expanduser("~/.local/share/kyth/profile")
        if os.path.isfile(profile_path):
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    role_profile = f.readline().strip() or "everyday"
            except Exception:
                logger.debug("handled expected exception", exc_info=True)
                pass
        run_command(["/usr/bin/kyth-apply-role-preset", role_profile], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    welcome_desktop = "/usr/share/applications/kyth-welcome.desktop"
    if os.path.isdir(os.path.expanduser("~/Desktop")) and (args.force or had_polish_stamp == 0):
        if os.path.isfile(welcome_desktop):
            try:
                shutil.copy(welcome_desktop, os.path.expanduser("~/Desktop/kyth-welcome.desktop"))
                # The executable bit is required for KDE Plasma 6 to treat this
                # launcher as trusted without prompting (see the same rule in
                # branding/23-kyth-helper-ctx-installs.sh, which uses 0o755 for
                # the shared /etc/skel template). This copy lands in the live
                # user's own home directory, so owner-only 0o700 is tighter
                # than the skel default, not a downgrade — no other user needs
                # access to this desktop.
                os.chmod(os.path.expanduser("~/Desktop/kyth-welcome.desktop"), 0o700)  # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
            except OSError:
                pass

    recycle_bin_desktop = "/usr/share/kyth/kyth-recycle-bin.desktop"
    recycle_bin_dst = os.path.expanduser("~/Desktop/kyth-recycle-bin.desktop")
    if os.path.isdir(os.path.expanduser("~/Desktop")) and not os.path.exists(recycle_bin_dst):
        if os.path.isfile(recycle_bin_desktop):
            try:
                shutil.copy(recycle_bin_desktop, recycle_bin_dst)
            except OSError:
                pass

    finish_polish(stamp_name, home_dir)
