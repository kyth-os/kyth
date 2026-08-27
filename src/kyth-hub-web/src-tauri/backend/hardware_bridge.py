#!/usr/bin/env python3
"""Bridge for the Tauri shell's `hardware_snapshot` command.

Runs a single `lspci -nn` call (via kyth_shared.system.gpu.lspci_gpu_lines)
to get a raw GPU description line — the same "one lspci call, no fancier
parsing" convention the Qt Hub's page_feedback.py / page_compatibility.py /
services/plasma.py already use, not a new probing pattern. One subprocess
call: comparable cost to guardian_bridge.py's pgrep/systemctl checks, well
short of a live probe sweep.

Returns {"gpu_line": null} on dev machines without a GPU lspci can see
(e.g. this repo's own dev container, which has no `lspci` binary at all)
— that's the expected, honest result there, not an error.
"""
from __future__ import annotations

import json

from kyth_shared.system.gpu import lspci_gpu_lines


def main() -> int:
    lines = lspci_gpu_lines()
    payload = {"gpu_line": lines[0] if lines else None}
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
