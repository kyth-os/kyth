"""Shared utilities for desktop shortcuts, menus, and flatpak exports."""
from __future__ import annotations
import logging
import subprocess

import os
import re
import shutil

from ..commands import run as run_command
from pathlib import Path

from ..atomic_io import atomic_write_text as _atomic_write_text

logger = logging.getLogger(__name__)


def safe_id(name: str) -> str:
    """Sanitize application name to be safe for filenames."""
    s = name.lower()
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    s = s.strip("-")
    return s


def copy_steam_icon(icon_name: str, src_icons_root: Path, dst_icons_root: Path) -> bool:
    """Copy matching game icon from Steam flatpak directory to host hicolor icon directory."""
    if not icon_name or not src_icons_root.is_dir():
        return False

    copied = False
    # Walk all files under src_icons_root looking for pattern "*/apps/{icon_name}.*"
    for path in src_icons_root.glob("**/apps/*"):
        if path.is_file() and path.stem == icon_name:
            try:
                # Resolve relative path to src_icons_root
                rel_path = path.relative_to(src_icons_root)
                dest_path = dst_icons_root / rel_path
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest_path)
                copied = True
            except (OSError, ValueError, AttributeError, TypeError):
                logger.debug("handled expected exception", exc_info=True)
                pass
    return copied


def refresh_desktop_database(desktop_dir: Path | str) -> None:
    """Refresh the freedesktop MIME/desktop-file database for a directory of .desktop files."""
    if shutil.which("update-desktop-database"):
        try:
            run_command(["update-desktop-database", str(desktop_dir)], capture_output=True, check=False)
        except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
            logger.debug("handled expected exception", exc_info=True)
            pass


def refresh_icon_cache(icons_dir: Path | str) -> None:
    """Refresh the GTK icon cache for a hicolor icon theme directory."""
    if shutil.which("gtk-update-icon-cache"):
        try:
            run_command(["gtk-update-icon-cache", "-q", "-t", str(icons_dir)], capture_output=True, check=False)
        except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
            logger.debug("handled expected exception", exc_info=True)
            pass


def refresh_kde_sycoca() -> None:
    """Rebuild KDE Plasma's application/service cache (kbuildsycoca6)."""
    if shutil.which("kbuildsycoca6"):
        try:
            run_command(["kbuildsycoca6", "--noincremental"], capture_output=True, check=False)
        except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
            logger.debug("handled expected exception", exc_info=True)
            pass


def rewrite_steam_exec(exec_line: str) -> str | None:
    """Rewrite steam Exec= commands to launch correctly via Flatpak Steam."""
    target = exec_line.split("=", 1)[1].strip()

    # Match steam://rungameid/[0-9]+
    m = re.search(r"steam://rungameid/([0-9]+)", target)
    if m:
        return f"Exec=flatpak run com.valvesoftware.Steam steam://rungameid/{m.group(1)}"

    # Match -applaunch [0-9]+
    m = re.search(r"-applaunch\s+([0-9]+)", target)
    if m:
        return f"Exec=flatpak run com.valvesoftware.Steam steam://rungameid/{m.group(1)}"

    return None


def export_steam_games() -> tuple[int, int]:
    """Export Flatpak Steam game shortcuts to the host system."""
    home = Path.home()
    data_home = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
    steam_data = home / ".var/app/com.valvesoftware.Steam/.local/share"
    src_apps = steam_data / "applications"
    src_icons = steam_data / "icons/hicolor"
    dst_apps = data_home / "applications"
    dst_icons = data_home / "icons/hicolor"

    if not src_apps.is_dir():
        return 0, 0

    dst_apps.mkdir(parents=True, exist_ok=True)

    exported = 0
    skipped = 0

    for src_file in src_apps.glob("*.desktop"):
        try:
            name = None
            icon = None
            exec_line = None

            with open(src_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("Name="):
                        name = line.split("=", 1)[1].strip()
                    elif line.startswith("Icon="):
                        icon = line.split("=", 1)[1].strip()
                    elif line.startswith("Exec="):
                        exec_line = line.strip()

            if not name or not exec_line:
                skipped += 1
                continue

            # Extract app ID
            m_id = re.search(r"rungameid/([0-9]+)", exec_line)
            if not m_id:
                m_id = re.search(r"-applaunch\s+([0-9]+)", exec_line)

            if not m_id:
                skipped += 1
                continue

            appid = m_id.group(1)
            dst_file = dst_apps / f"kyth-steam-{appid}.desktop"

            # Parse and rewrite content
            new_lines = []
            saw_exec = False
            saw_categories = False

            with open(src_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line_strip = line.strip()
                    if line_strip.startswith("Exec="):
                        rewritten = rewrite_steam_exec(line_strip)
                        if rewritten:
                            new_lines.append(rewritten + "\n")
                            saw_exec = True
                        else:
                            new_lines.append(line)
                    elif line_strip.startswith("Categories="):
                        new_lines.append("Categories=Game;\n")
                        saw_categories = True
                    elif line_strip.startswith("NoDisplay=") or line_strip.startswith("Hidden="):
                        # skip hidden flags
                        continue
                    else:
                        new_lines.append(line)

            if not saw_exec:
                skipped += 1
                continue

            if not saw_categories:
                new_lines.append("Categories=Game;\n")

            new_lines.append("X-KythExportedSteamGame=true\n")
            new_lines.append("X-Flatpak=com.valvesoftware.Steam\n")

            # Write out
            _atomic_write_text(dst_file, "".join(new_lines), encoding="utf-8")

            # Copy icon
            if icon:
                copy_steam_icon(icon, src_icons, dst_icons)

            exported += 1
            print(f"Exported {name}")
        except (OSError, ValueError, UnicodeError, AttributeError, KeyError):
            logger.debug("handled expected exception", exc_info=True)
            skipped += 1

    # Update database and caches
    refresh_desktop_database(dst_apps)
    if dst_icons.is_dir():
        refresh_icon_cache(dst_icons)

    return exported, skipped


def categorize_web_apps() -> bool:
    """Scan and categorize web apps under ~/.local/share/applications."""
    home = Path.home()
    app_dir = home / ".local/share/applications"
    if not app_dir.is_dir():
        return False

    changed = False
    globs = [
        "chrome-*.desktop",
        "chromium-*.desktop",
        "brave-*.desktop",
        "msedge-*.desktop",
        "com.google.Chrome.flextop.*.desktop",
        "org.chromium.Chromium.flextop.*.desktop",
        "com.brave.Browser.flextop.*.desktop",
        "com.microsoft.Edge.flextop.*.desktop",
    ]

    for pattern in globs:
        for desktop_file in app_dir.glob(pattern):
            try:
                content = desktop_file.read_text(encoding="utf-8", errors="replace")

                # Match --app or --app-id
                if not re.search(r"--app(-id)?=", content):
                    continue

                # If Categories= is already present, skip
                if re.search(r"^Categories=", content, re.MULTILINE):
                    continue

                # Insert Categories=X-KythWebApp; right after [Desktop Entry]
                lines = content.splitlines()
                updated_lines = []
                inserted = False
                for line in lines:
                    updated_lines.append(line)
                    if line.strip() == "[Desktop Entry]" and not inserted:
                        updated_lines.append("Categories=X-KythWebApp;")
                        inserted = True

                _atomic_write_text(desktop_file, "\n".join(updated_lines) + "\n", encoding="utf-8")
                changed = True
            except (OSError, ValueError, UnicodeError, AttributeError, re.error):
                logger.debug("handled expected exception", exc_info=True)
                pass

    if changed:
        refresh_kde_sycoca()

    return changed


def fixup_kali_desktop_launchers() -> bool:
    """Fix up .desktop launchers exported from Kali distrobox container."""
    app_dir = Path.home() / ".local" / "share" / "applications"
    if not app_dir.is_dir():
        return False

    changed = False
    for desktop_file in app_dir.glob("*.desktop"):
        if not desktop_file.is_file():
            continue
        try:
            content = desktop_file.read_text(encoding="utf-8", errors="replace")
            if "--name kali" not in content and "-n kali" not in content:
                continue

            lines = content.splitlines()
            new_lines = []
            file_changed = False

            for line in lines:
                if line.startswith("Categories="):
                    new_lines.append("Categories=X-KythSecurity;")
                    file_changed = True
                    continue
                if re.match(r"^NoDisplay\s*=\s*true", line, re.IGNORECASE):
                    file_changed = True
                    continue
                if line.startswith("OnlyShowIn=") or line.startswith("NotShowIn="):
                    file_changed = True
                    continue
                if re.search(r"\b(pkexec|kdesu|gksu|gksudo)\b", line):
                    line = re.sub(r"\b(pkexec|kdesu|gksu|gksudo)\s+", "sudo -E ", line)
                    file_changed = True

                new_lines.append(line)

            if not any(l.startswith("Categories=") for l in new_lines):
                new_lines.append("Categories=X-KythSecurity;")
                file_changed = True

            if file_changed:
                _atomic_write_text(desktop_file, "\n".join(new_lines) + "\n", encoding="utf-8")
                changed = True
        except (OSError, ValueError, UnicodeError, AttributeError, re.error):
            logger.debug("handled expected exception", exc_info=True)
            pass

    # Zenmap specific fixups
    for desktop_file in app_dir.glob("*zenmap*.desktop"):
        if not desktop_file.is_file():
            continue
        try:
            content = desktop_file.read_text(encoding="utf-8", errors="replace")
            if "--name kali" not in content and "-n kali" not in content:
                continue

            if re.search(r"^Exec=.*$", content, re.MULTILINE):
                content = re.sub(
                    r"^Exec=.*$",
                    "Exec=kyth-distrobox-root-launch --root kali /usr/bin/zenmap",
                    content,
                    flags=re.MULTILINE,
                )
            if re.search(r"^TryExec=.*$", content, re.MULTILINE):
                content = re.sub(
                    r"^TryExec=.*$",
                    "TryExec=kyth-distrobox-root-launch",
                    content,
                    flags=re.MULTILINE,
                )
            _atomic_write_text(desktop_file, content, encoding="utf-8")
            changed = True
        except (OSError, ValueError, UnicodeError, AttributeError, re.error):
            logger.debug("handled expected exception", exc_info=True)
            pass

    if changed:
        refresh_desktop_database(app_dir)
        refresh_kde_sycoca()

    return changed
