"""Declarative home — role presets as idempotent TOML.

Mirrors ``hardware_policy apply``: ``~/.config/kyth/preset.toml`` is the
single source of truth (``profile = "everyday"|"gaming"|"dev"|"creator"``,
plus flatpaks/distroboxes/vscode extensions). ``kyth-apply-role-preset``
reads it and installs only what is missing — second run is a no-op.
Progressive vs Mint's dotfile drift and Bazzite's one-image.
"""
from __future__ import annotations
import logging

import argparse
import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kyth_shared.commands import run

logger = logging.getLogger(__name__)

PRESETS: dict[str, dict[str, list[str]]] = {
    "everyday": {
        "flatpaks": ["com.brave.Browser", "com.valvesoftware.Steam"],
        "distroboxes": [],
        "vscode_extensions": [],
    },
    "gaming": {
        "flatpaks": ["com.valvesoftware.Steam", "net.lutris.Lutris", "com.heroicgameslauncher.hgl", "com.github.Matoking.protontricks"],
        "distroboxes": [],
        "vscode_extensions": [],
    },
    "dev": {
        "flatpaks": ["com.visualstudio.code", "com.github.flathub.flatpak-external-data-checker"],
        "distroboxes": ["kyth-ai-dev"],
        "vscode_extensions": ["ms-python.python", "rust-lang.rust-analyzer"],
    },
    "creator": {
        "flatpaks": ["com.obsproject.Studio", "org.kde.kdenlive"],
        "distroboxes": [],
        "vscode_extensions": [],
    },
}

DEFAULT_PRESET_PATH = Path.home() / ".config" / "kyth" / "preset.toml"


@dataclass(frozen=True, slots=True)
class Preset:
    profile: str
    flatpaks: tuple[str, ...]
    distroboxes: tuple[str, ...]
    vscode_extensions: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Preset":
        profile = str(data.get("profile", "everyday"))
        if profile not in PRESETS:
            profile = "everyday"
        # Allow TOML to override per-profile lists, else use preset defaults
        flatpaks = tuple(data.get("flatpaks", PRESETS[profile]["flatpaks"]))
        distroboxes = tuple(data.get("distroboxes", PRESETS[profile]["distroboxes"]))
        vscode_extensions = tuple(data.get("vscode_extensions", PRESETS[profile]["vscode_extensions"]))
        return cls(profile, flatpaks, distroboxes, vscode_extensions)

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "flatpaks": list(self.flatpaks),
            "distroboxes": list(self.distroboxes),
            "vscode_extensions": list(self.vscode_extensions),
        }


def preset_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "kyth" / "preset.toml"
    return DEFAULT_PRESET_PATH


def load_preset(path: Path | None = None) -> Preset:
    p = preset_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        # Default to everyday if no file
        return Preset("everyday", tuple(PRESETS["everyday"]["flatpaks"]), (), ())
    return Preset.from_dict(data)


def save_preset(preset: Preset, path: Path | None = None) -> Path:
    p = preset_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    flatpaks_s = ", ".join(f'"{x}"' for x in preset.flatpaks)
    distroboxes_s = ", ".join(f'"{x}"' for x in preset.distroboxes)
    vscode_s = ", ".join(f'"{x}"' for x in preset.vscode_extensions)
    lines = [
        f'profile = "{preset.profile}"',
        f"flatpaks = [{flatpaks_s}]",
        f"distroboxes = [{distroboxes_s}]",
        f"vscode_extensions = [{vscode_s}]",
        "",
    ]
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def _installed_flatpaks() -> set[str]:
    try:
        res = run(["flatpak", "list", "--app", "--columns=application"], capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return {ln.strip() for ln in res.stdout.splitlines() if ln.strip()}
    except Exception:
        logger.debug("handled expected exception", exc_info=True)
        pass
    return set()


def _installed_distroboxes() -> set[str]:
    try:
        res = run(["distrobox", "list", "--no-color"], capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return {parts[2] for line in res.stdout.splitlines() if len(parts := line.split()) >= 3}
    except Exception:
        logger.debug("handled expected exception", exc_info=True)
        pass
    return set()


def _installed_vscode_extensions() -> set[str]:
    for binary in ("code", "codium", "code-insiders"):
        try:
            res = run([binary, "--list-extensions"], capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return {ln.strip().lower() for ln in res.stdout.splitlines() if ln.strip()}
        except Exception:
            continue
    return set()


def apply_preset(
    profile: str | None = None,
    path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Idempotently apply preset — install only missing items.

    If ``profile`` is given, it overwrites the TOML's profile before
    applying (and persists it). Returns ``{installed: [...], skipped: [...], dry_run: bool}``.
    """
    preset = load_preset(path)
    if profile is not None:
        if profile not in PRESETS:
            raise ValueError(f"Unknown preset {profile!r} (everyday/gaming/dev/creator)")
        # Merge profile defaults into preset if profile changed
        preset = Preset(
            profile=profile,
            flatpaks=tuple(PRESETS[profile]["flatpaks"]),
            distroboxes=tuple(PRESETS[profile]["distroboxes"]),
            vscode_extensions=tuple(PRESETS[profile]["vscode_extensions"]),
        )
        if not dry_run:
            save_preset(preset, path)

    installed: list[str] = []
    skipped: list[str] = []

    have_flatpaks = _installed_flatpaks()
    for app in preset.flatpaks:
        if app in have_flatpaks:
            skipped.append(app)
        else:
            installed.append(app)
            if not dry_run:
                try:
                    run(["flatpak", "install", "-y", "flathub", app], capture_output=True, timeout=300)
                except Exception:
                    logger.debug("handled expected exception", exc_info=True)
                    pass

    have_boxes = _installed_distroboxes()
    for box in preset.distroboxes:
        if box in have_boxes:
            skipped.append(box)
        else:
            installed.append(box)
            if not dry_run:
                try:
                    run(["distrobox", "create", "--yes", "--name", box, "--image", "registry.fedoraproject.org/fedora-toolbox:44"], capture_output=True, timeout=300)
                except Exception:
                    logger.debug("handled expected exception", exc_info=True)
                    pass

    have_exts = _installed_vscode_extensions()
    for ext in preset.vscode_extensions:
        low = ext.lower()
        if low in have_exts:
            skipped.append(ext)
        else:
            installed.append(ext)
            if not dry_run:
                for binary in ("code", "codium"):
                    try:
                        run([binary, "--install-extension", ext], capture_output=True, timeout=60)
                        break
                    except Exception:
                        continue

    return {"profile": preset.profile, "installed": installed, "skipped": skipped, "dry_run": dry_run}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kyth-apply-role-preset", description="Apply KythOS role preset idempotently (preset.toml).")
    p.add_argument("profile", nargs="?", choices=sorted(PRESETS), help="Profile to apply and persist")
    p.add_argument("--path", type=Path, default=None, help="Custom preset.toml path")
    p.add_argument("--dry-run", action="store_true", help="Show what would be installed without changing system")
    p.add_argument("--list", action="store_true", help="List available presets")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        print("Available presets: " + ", ".join(sorted(PRESETS)))
        return 0
    try:
        result = apply_preset(profile=args.profile, path=args.path, dry_run=args.dry_run)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(f"Would install: {result['installed'] or 'nothing (already satisfied)'}")
        print(f"Skipped (already present): {result['skipped']}")
    else:
        if result["installed"]:
            print(f"Installed: {', '.join(result['installed'])}")
        else:
            print("Already satisfied — no changes.")
    print(f"Profile: {result['profile']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
