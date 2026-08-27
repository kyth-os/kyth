#!/usr/bin/env python3
"""Bridge for the Tauri shell's `storage_snapshot` command.

Free space on the same filesystem Guardian's own storage check
(kyth_shared.guardian's _probe_storage — home, falling back to root if
home isn't a real mount of its own, e.g. a tiny composefs image) looks at
first. Pure `shutil.disk_usage` — a stdlib stat() call, no subprocess at
all, cheaper even than the lspci-backed hardware bridge.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path


def main() -> int:
    for check_path in (Path.home(), Path("/")):
        try:
            usage = shutil.disk_usage(check_path)
        except OSError:
            continue
        if usage.total < 2 * 1024**3:  # skip tiny partitions, mirrors guardian.py's own check
            continue
        print(json.dumps({"free_bytes": usage.free, "total_bytes": usage.total}))
        return 0
    print(json.dumps({"free_bytes": None, "total_bytes": None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
