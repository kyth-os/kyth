#!/usr/bin/env python3
"""Select the prior published image release digest from GitHub's release list."""

import json
import sys

from kyth_changelog import previous_image_release_digest


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: resolve-previous-image-release.py CHANNEL_TAG CURRENT_VERSION", file=sys.stderr)
        return 2
    try:
        releases = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"invalid GitHub releases JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(releases, list):
        print("GitHub releases response must be an array", file=sys.stderr)
        return 1
    print(previous_image_release_digest(releases, sys.argv[1], sys.argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
