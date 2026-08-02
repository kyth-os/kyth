#!/usr/bin/env python3
"""Enforce focused coverage floors on Kyth's highest-risk service boundaries."""
from __future__ import annotations

import json
import sys
from pathlib import Path

THRESHOLDS = {
    "build_files/kyth-installer/kyth_installer/fsresize.py": 90.0,
    "build_files/kyth-installer/kyth_installer/recovery.py": 85.0,
    "build_files/kyth-installer/kyth_installer/services/installer_service.py": 20.0,
    "build_files/kyth-installer/kyth_installer/system.py": 85.0,
    "build_files/kyth-welcome/kyth_welcome/services/privileged.py": 80.0,
    "build_files/kyth-welcome/kyth_welcome/services/updates.py": 75.0,
    "build_files/kyth_shared/kyth_shared/desktop/windows_installer.py": 80.0,
    "build_files/kyth_shared/kyth_shared/thirdparty.py": 12.0,
    "build_files/kyth_shared/kyth_shared/user_polish.py": 30.0,
    "build_files/kyth_shared/kyth_shared/vm_acceptance.py": 16.0,
}


def main() -> int:
    report = json.loads(Path("coverage.json").read_text(encoding="utf-8"))
    failures = []
    for filename, minimum in THRESHOLDS.items():
        summary = report["files"].get(filename, {}).get("summary")
        if summary is None:
            failures.append(f"{filename}: absent from coverage report")
            continue
        actual = float(summary["percent_covered"])
        print(f"{filename}: {actual:.1f}% (minimum {minimum:.1f}%)")
        if actual < minimum:
            failures.append(f"{filename}: {actual:.1f}% is below {minimum:.1f}%")
    if failures:
        print("Critical coverage gate failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
