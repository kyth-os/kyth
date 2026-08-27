#!/usr/bin/env python3
"""Bridge between the Tauri (Rust) shell and the existing Python backend.

This is the "option A" boundary from the react+rust rewrite plan: Rust owns
the window/IPC/shell layer, kyth_shared stays Python for now (it's ~200
modules of host-tuning logic — porting it is a separate, later decision,
not part of the shell swap). One small, single-purpose script per the
kyth_shared convention (see CLAUDE.md), invoked as a subprocess by
main.rs's `probe_backend` command — argv[1] is a disk-backed probe section
key (see kyth_shared.system.probe.DISK_TTL for the valid set, e.g.
"bootc-status-data"), stdout is one JSON object.

Deliberately read-only: this calls read_section(), which only reads
whatever kyth-probe.service (or a prior Hub run) already wrote to the disk
cache — it does not trigger a fresh probe (that's collect_snapshot(),
which shells out to bootc/flatpak/lspci and can take real time). A
dashboard tile blocking a Tauri command handler on that would be a bad
first impression; the on-disk cache is what production Hub pages already
read from for the same reason (see services/probe.py's docstring).
"""
from __future__ import annotations

import json
import sys

from kyth_shared.system.probe import read_section


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"error": "usage: probe_bridge.py <section-key>"}))
        return 1

    key = sys.argv[1]
    try:
        data = read_section(key)
    except (OSError, ValueError, RuntimeError) as exc:  # noqa: BLE001 -- narrow: bridge is best-effort like probe.py itself
        print(json.dumps({"key": key, "data": None, "error": str(exc)}))
        return 0

    # data is None when no fresh-enough cache entry exists yet (e.g.
    # kyth-probe.service hasn't run on this machine) — that's a valid,
    # honest result, not an error.
    print(json.dumps({"key": key, "data": data, "error": None}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
