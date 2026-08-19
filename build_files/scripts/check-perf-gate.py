#!/usr/bin/env python3
"""Give kyth_shared.perf_gate's check a real measurement.

perf_gate.check_perf_gate() reads a JSONL ledger of historical p95 samples
and compares a supplied current_ms against the most recent one — real,
tested logic. But every caller in this repo passed current_ms=None (a
guaranteed pass, no comparison ever happens), and nothing anywhere writes
to its default ledger (/var/cache/kyth/perf-ledger.jsonl, real-machine
runtime state that doesn't exist on a fresh CI checkout regardless). The
gate has never been able to catch a regression.

This measures kyth_shared.system.probe.collect_probe_results() — pure
stdlib, no PySide6, so it runs in the same bare environment validate.sh
already has — and checks it against a ledger tracked in the repo instead
of host state, so CI has real history to compare against.

The ledger is only ever written by --record, run deliberately by a
maintainer, never automatically by a plain check. CI has no step that
commits anything back, so an auto-write during a CI run would just be
silently discarded on every single run — never accumulating real history,
and worse, inviting exactly the flakiness a perf gate should prevent (a
single noisy sample quietly becoming tomorrow's baseline). Recording a new
baseline is a conscious decision, same as raising an optimization budget.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Caller sets PYTHONPATH=build_files/kyth_shared (matches every other
# validate.sh step that imports kyth_shared), not managed here.
from kyth_shared.perf_gate import check_perf_gate

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "build_files/config/perf-ledger.jsonl"
MAX_LEDGER_ENTRIES = 50
SAMPLES = 7

_PROBE_CODE = (
    "import time; from kyth_shared.system.probe import collect_probe_results; "
    "s=time.perf_counter(); collect_probe_results(); "
    "print((time.perf_counter()-s)*1000)"
)


def _measure_once() -> float:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "build_files/kyth_shared")
    result = subprocess.run(
        [sys.executable, "-c", _PROBE_CODE],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60, check=True,
    )
    return float(result.stdout.strip())


def _measure_current_ms() -> float:
    # Median of 7 samples, not 3: one process launch is noisy enough (cold
    # caches, scheduler jitter) that a 3-sample median with a 5%-threshold
    # measured luck more than code. 10% threshold below matches.
    samples = sorted(_measure_once() for _ in range(SAMPLES))
    return samples[len(samples) // 2]


def _record(current_ms: float) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(line)
    entry = json.dumps({
        "p95": round(current_ms, 2),
        "commit": os.environ.get("GITHUB_SHA", "local"),
        "recorded_at": int(time.time()),
    })
    entries.append(entry)
    entries = entries[-MAX_LEDGER_ENTRIES:]
    LEDGER.write_text("\n".join(entries) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--record", action="store_true",
        help="Measure and append a new baseline to the ledger, regardless of pass/fail. "
             "Commit the resulting build_files/config/perf-ledger.jsonl change.",
    )
    args = parser.parse_args(argv)

    current_ms = _measure_current_ms()

    if args.record:
        _record(current_ms)
        print(f"perf gate: recorded new baseline {current_ms:.1f}ms -> {LEDGER}")
        return 0

    result = check_perf_gate(current_ms=current_ms, ledger=LEDGER)

    if not result.get("enabled", True):
        print(f"perf gate disabled: current={current_ms:.1f}ms")
        return 0

    last = result.get("last")
    if last is None:
        print(
            f"perf gate: no ledger baseline yet (current={current_ms:.1f}ms) — "
            "run `python3 build_files/scripts/check-perf-gate.py --record` to establish one"
        )
        return 0

    delta = result.get("delta")
    print(
        f"perf gate: current={current_ms:.1f}ms last={last:.1f}ms "
        f"delta={delta}% threshold={result.get('threshold')}%"
    )
    if not result.get("pass"):
        print(
            f"::error::probe collection regressed {delta}% vs last recorded "
            f"{last:.1f}ms (threshold {result.get('threshold')}%). If intentional, "
            "re-baseline with --record.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
