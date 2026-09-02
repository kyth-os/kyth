#!/usr/bin/env python3
"""Generate KRunner application entries from the React Hub route manifest.

This is packaging-only code. The manifest is imported by the React frontend
and is deliberately independent of the retired Python/Qt Hub package.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "page"


def _entry(section: dict[str, str]) -> str:
    key = section["key"]
    title = section["title"]
    description = section["description"]
    keywords = ";".join(dict.fromkeys((title, key)))
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "NoDisplay=true\n"
        f"Name=Kyth Hub: {title}\n"
        f"Comment={description}\n"
        f"Keywords={keywords};\n"
        f'Exec=/usr/bin/kyth-welcome-launch --page "{key}"\n'
        "Icon=kyth\n"
        "Terminal=false\n"
        "Categories=Settings;\n"
        "X-KDE-StartupNotify=false\n"
    )


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} MANIFEST DEST_DIR", file=sys.stderr)
        return 2

    manifest_path = Path(sys.argv[1])
    destination_dir = Path(sys.argv[2])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    destination_dir.mkdir(parents=True, exist_ok=True)

    for destination in manifest["destinations"]:
        for section in destination["sections"]:
            path = destination_dir / f"kyth-hub-{_slugify(section['key'])}.desktop"
            path.write_text(_entry(section), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
