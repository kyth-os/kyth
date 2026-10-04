#!/usr/bin/env python3
"""Check monthly for compatible Tauri/GTK stack updates in both shells."""
from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHELLS = (
    ("Hub", "src/kyth-hub-web/src-tauri/Cargo.toml"),
    ("Installer", "src/kyth-installer-web/src-tauri/Cargo.toml"),
)
UPDATE_PACKAGES = (
    "tauri",
    "tauri-build",
    "tauri-plugin-single-instance",
    "tauri-runtime",
    "tauri-runtime-wry",
    "tauri-utils",
    "tao",
    "wry",
)
GTK_PACKAGES = {
    "atk",
    "cairo-rs",
    "gdk",
    "gdk-pixbuf",
    "gdkx11",
    "gio",
    "glib",
    "glib-sys",
    "gobject-sys",
    "gtk",
    "gtk-sys",
    "javascriptcore-rs",
    "muda",
    "pango",
    "soup3",
    "webkit2gtk",
}


def stack_versions(lockfile: Path) -> dict[str, list[str]]:
    packages = tomllib.loads(lockfile.read_text(encoding="utf-8"))["package"]
    versions: dict[str, list[str]] = {}
    for package in packages:
        name = package["name"]
        if name.startswith("tauri") or name in GTK_PACKAGES | {"tao", "wry"}:
            versions.setdefault(name, []).append(package["version"])
    return {name: sorted(items) for name, items in sorted(versions.items())}


def main() -> int:
    before: dict[str, dict[str, list[str]]] = {}
    for label, manifest in SHELLS:
        manifest_path = ROOT / manifest
        lockfile = manifest_path.with_name("Cargo.lock")
        before[label] = stack_versions(lockfile)
        command = ["cargo", "update", "--manifest-path", str(manifest_path)]
        for package in UPDATE_PACKAGES:
            command.extend(("-p", package))
        subprocess.run(command, cwd=ROOT, check=True)

    changes = []
    for label, manifest in SHELLS:
        lockfile = (ROOT / manifest).with_name("Cargo.lock")
        after = stack_versions(lockfile)
        if before[label] != after:
            changes.append((label, before[label], after))

    if changes:
        for label, old, new in changes:
            changed_names = sorted(
                name for name in old.keys() | new.keys() if old.get(name) != new.get(name)
            )
            print(f"{label} desktop dependency updates available:", file=sys.stderr)
            for name in changed_names:
                print(f"  {name}: {old.get(name, [])} -> {new.get(name, [])}", file=sys.stderr)
        print(
            "Update both Cargo.lock files together on testing and run both shell checks.",
            file=sys.stderr,
        )
        return 1

    print("No compatible Tauri/GTK-family updates are available in either shell.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
