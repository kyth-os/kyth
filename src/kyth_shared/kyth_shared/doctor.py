"""kyth-doctor — health score like cachy-doctor, reuses probe + hardware_policy.

Scores: kernel (fedora vs cachy), v3 (CACHYOS_ARCH), zram, btrfs, scx.
Suggests just fixes; no daemon, same probe code.
"""
from __future__ import annotations

from pathlib import Path

from kyth_shared.system.probe import read_section
from kyth_shared.system.hardware_view import get_hardware_view


def _score() -> tuple[int, list[str], list[str]]:
    suggestions: list[str] = []
    checks: list[str] = []
    score = 0

    # kernel
    has_cachy = any("cachy" in p.name for p in Path("/usr/lib/modules").glob("*"))
    if has_cachy:
        checks.append("kernel: cachy (opt-in)")
        score += 20
    else:
        checks.append("kernel: fedora (default)")
        score += 20
        suggestions.append("For v3: just build-base cachy")

    # v3
    _ = Path("/usr/lib/os-release").read_text(errors="ignore") if Path("/usr/lib/os-release").exists() else ""
    # Use probe hardware-summary if available
    hw = read_section("hardware-summary")
    if hw and isinstance(hw, dict) and hw.get("capabilities"):
        checks.append(f"v3: {hw.get('capabilities')[:2]}")
        score += 20
    else:
        try:
            view = get_hardware_view()
            checks.append(f"v3: {view.evaluation.capabilities[:2]}")
            score += 20
        except Exception:
            checks.append("v3: unknown")
            suggestions.append("Run kyth-probe --system")

    # zram
    if Path("/usr/lib/systemd/zram-generator.conf").exists() or Path("/etc/systemd/zram-generator.conf").exists():
        checks.append("zram: yes")
        score += 20
    else:
        checks.append("zram: no")
        suggestions.append("Enable zram: systemctl enable systemd-zram-setup@zram0")

    # btrfs
    try:
        fstype = Path("/proc/mounts").read_text()
        if "btrfs" in fstype:
            checks.append("btrfs: yes")
            score += 20
        else:
            checks.append("btrfs: no")
    except Exception:
        checks.append("btrfs: unknown")

    # scx
    scx_active = Path("/sys/kernel/sched_ext/state").exists()
    checks.append(f"scx: {'active' if scx_active else 'inactive (opt-in)'}")
    score += 20
    if not scx_active:
        suggestions.append("Try scx: kyth-scx set lavd")

    return min(score, 100), checks, suggestions


def main() -> int:
    score, checks, suggestions = _score()
    print(f"KythOS health: {score}/100")
    for c in checks:
        print(f" - {c}")
    if suggestions:
        print("\nSuggestions (just):")
        for s in suggestions:
            print(f"  * {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
