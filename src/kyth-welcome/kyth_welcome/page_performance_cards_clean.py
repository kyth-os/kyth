"""Clean Perf card for PerformancePage — read-only tunable status list.

Was a wall of 24 cryptically-abbreviated buttons ("UKSmd", "PipeWG",
"OOM-G"...) that each clobbered one shared status label when clicked, so
only the most recently clicked tunable's state was ever visible at a time,
and nothing was legible without already knowing the abbreviations. This
renders every tunable's live status up front, in plain English, as one
scannable list (one background fetch on page load instead of 24 clicks).

Changing a profile still goes through the Master switch, `ujust` recipes,
or `kyth-tunable <name> status` in a terminal (Advanced card, below) —
wiring each tunable's own privileged write path into the Hub is the next
phase of the Hub rewrite, not this one.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .page_performance import PerformancePage

# Every X_status() reader in kyth_shared settled on the same convention:
# the do-nothing/default value is one of these three strings (or False);
# anything else means the tunable has actually been switched on.
_INACTIVE = {"balanced", "off", "auto"}


def _flag(value: str) -> bool:
    return value not in _INACTIVE


def _status_kargs() -> tuple[str, bool]:
    from kyth_shared.kargs_preset import load_kargs

    value = str(load_kargs().get("profile", "balanced"))
    return value, _flag(value)


def _status_io() -> tuple[str, bool]:
    from kyth_shared.io_tune import io_status

    value = io_status()
    return value, _flag(value)


def _status_net() -> tuple[str, bool]:
    from kyth_shared.net_latency import net_latency_status

    on = bool(net_latency_status())
    return ("on" if on else "off"), on


def _status_uksmd() -> tuple[str, bool]:
    from kyth_shared.uksmd_preset import load_uksmd

    on = bool(load_uksmd().get("enabled"))
    return ("on" if on else "off"), on


def _status_journal() -> tuple[str, bool]:
    from kyth_shared.journal_tune import journal_status

    on = bool(journal_status())
    return ("slimmed" if on else "stock"), on


def _status_thp() -> tuple[str, bool]:
    from kyth_shared.thp_tune import thp_status

    value = thp_status()
    return value, _flag(value)


def _status_mimalloc() -> tuple[str, bool]:
    from kyth_shared.mimalloc_preset import mimalloc_status

    value = mimalloc_status()
    return value, value != "off"


def _status_irq() -> tuple[str, bool]:
    from kyth_shared.irq_tune import irq_status

    value = irq_status()
    return value, _flag(value)


def _status_btrfs() -> tuple[str, bool]:
    from kyth_shared.btrfs_perf import btrfs_perf_status

    value = btrfs_perf_status()
    return value, _flag(value)


def _status_trim() -> tuple[str, bool]:
    from kyth_shared.trim_preset import trim_status

    value = trim_status()
    return value, _flag(value)


def _status_ananicy() -> tuple[str, bool]:
    from kyth_shared.ananicy_preset import ananicy_status

    value = ananicy_status()
    return value, _flag(value)


def _status_zswap() -> tuple[str, bool]:
    from kyth_shared.zswap_preset import zswap_status

    value = zswap_status()
    return value, _flag(value)


def _status_gpu() -> tuple[str, bool]:
    from kyth_shared.gpu_power import gpu_power_status

    value = gpu_power_status()
    return value, _flag(value)


def _status_sched() -> tuple[str, bool]:
    from kyth_shared.sched_latency import sched_latency_status

    value = sched_latency_status()
    return value, _flag(value)


def _status_readahead() -> tuple[str, bool]:
    from kyth_shared.readahead_preset import load_readahead

    cfg = load_readahead()
    on = bool(cfg.get("enabled"))
    return (f"{cfg.get('size_mb', 512)}MB" if on else "off"), on


def _status_master() -> tuple[str, bool]:
    from kyth_shared.gaming_master import load_master

    value = str(load_master().get("profile", "balanced"))
    return value, _flag(value)


def _status_wine() -> tuple[str, bool]:
    from kyth_shared.wine_sync import wine_sync_status

    value = wine_sync_status()
    return value, _flag(value)


def _status_kwin() -> tuple[str, bool]:
    from kyth_shared.kwin_latency import kwin_latency_status

    value = kwin_latency_status()
    return value, _flag(value)


def _status_pipewire() -> tuple[str, bool]:
    from kyth_shared.pipewire_gaming import pipewire_gaming_status

    value = pipewire_gaming_status()
    return value, _flag(value)


def _status_btrfsauto() -> tuple[str, bool]:
    from kyth_shared.btrfs_autotune import load_btrfs_autotune

    on = bool(load_btrfs_autotune().get("enabled"))
    return ("on" if on else "off"), on


def _status_boot() -> tuple[str, bool]:
    from kyth_shared.boot_loader import loader_status

    value = loader_status()
    return value, _flag(value)


def _status_oomg() -> tuple[str, bool]:
    from kyth_shared.oom_gaming import oom_gaming_status

    value = oom_gaming_status()
    return value, _flag(value)


def _status_shader() -> tuple[str, bool]:
    from kyth_shared.shader_tmpfs import shader_tmpfs_status

    value = shader_tmpfs_status()
    return value, _flag(value)


def _status_cfs() -> tuple[str, bool]:
    from kyth_shared.gaming_cfs import gaming_cfs_status

    value = gaming_cfs_status()
    return value, _flag(value)


# key, title, one-line description (lifted from each module's own
# docstring, not invented), status fetcher — every fetcher above is a
# cheap local file read, safe to run in a batch off the GUI thread.
TUNABLES: tuple[tuple[str, str, str, Callable[[], tuple[str, bool]]], ...] = (
    ("kargs", "Kernel args profile", "mitigations=off and other boot args — gaming profile only.", _status_kargs),
    ("io", "I/O scheduler", "NVMe scheduler=none plus read-ahead tuning via a udev rule.", _status_io),
    ("net", "Network latency", "BBR+FQ, TCP fastopen, and rmem sysctls for online play.", _status_net),
    ("uksmd", "UKSM daemon", "Dedups identical memory pages — worth 15-30% RAM under heavy gaming loads.", _status_uksmd),
    ("journal", "Journal size", "Slims systemd-journald's disk cap and retention window.", _status_journal),
    ("thp", "Transparent huge pages", "madvise + khugepaged tuning — cuts stutter in UE/Star Citizen.", _status_thp),
    ("mimalloc", "Mimalloc allocator", "Per-game LD_PRELOAD wrapper — never a global system preload.", _status_mimalloc),
    ("irq", "IRQ affinity", "Pins GPU/NVMe/NIC interrupts off the gaming CCD/isolated cores.", _status_irq),
    ("btrfs", "Btrfs mount options", "compress-force=zstd:1,noatime via a systemd drop-in.", _status_btrfs),
    ("trim", "SSD trim", "Weekly fstrim.timer instead of continuous discard (avoids QLC stalls).", _status_trim),
    ("ananicy", "Ananicy nice", "Renices the gaming cgroup — nice -12, realtime I/O class.", _status_ananicy),
    ("zswap", "Zswap", "zstd-compressed swap cache — complements zram under 16 GB.", _status_zswap),
    ("gpu", "GPU power profile", "DPM + power profile: high in gaming, auto otherwise.", _status_gpu),
    ("sched", "Scheduler latency sysctls", "Kernel scheduler latency knobs tuned for gaming.", _status_sched),
    ("readahead", "Game-dir readahead", "Ephemeral WILLNEED prefetch on game directories — no daemon.", _status_readahead),
    ("master", "Master gaming profile", "One switch that composes every tunable on this list for a gaming rig.", _status_master),
    ("wine", "Wine sync primitive", "Picks ntsync/fsync/esync automatically from what the kernel supports.", _status_wine),
    ("kwin", "KWin low latency", "Unblocks MaxFPS and enables tearing in the gaming profile.", _status_kwin),
    ("pipewire", "PipeWire quantum", "128/48000 for low latency in gaming, 1024/48000 studio otherwise.", _status_pipewire),
    ("btrfsauto", "Btrfs autotune", "Weekly timer that rebalances Btrfs only if it's actually needed.", _status_btrfsauto),
    ("boot", "Boot loader timeout", "greenboot-aware — 0s fast path vs. the 2s balanced default.", _status_boot),
    ("oomg", "OOM gaming slice", "gaming.slice gets 75% OOM headroom vs. desktop's 50%.", _status_oomg),
    ("shader", "Shader cache tmpfs", "Mesa's shader cache lives on tmpfs, persisted back on shutdown.", _status_shader),
    ("cfs", "CFS gaming burst", "gaming.slice CPU quota 400%, weight 800, for burst scheduling.", _status_cfs),
)


def gather_clean_status() -> dict[str, tuple[str, bool]]:
    """Run every fetcher above. Meant for a background DataWorker — never
    called from the GUI thread."""
    result: dict[str, tuple[str, bool]] = {}
    for key, _title, _description, fetch in TUNABLES:
        try:
            result[key] = fetch()
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError, TypeError):  # noqa: BLE001 -- narrow: best-effort status read
            result[key] = ("unknown", False)
    return result


def make_clean_card(page: "PerformancePage"):
    from .qt import QHBoxLayout, QLabel, QPushButton, QVBoxLayout
    from .widgets import PillBadge, _make_card, _make_setting_row

    card, layout = _make_card()
    title = QLabel("Clean Perf — zero cost when off")
    title.setObjectName("card-title")
    layout.addWidget(title)
    desc = QLabel(
        "24 offline tunables in /etc/kyth, each revertible. Master composes "
        "all of them for a gaming rig in one switch; the rest are read-only "
        "here for now — change them with the Master switch, ujust recipes, "
        "or kyth-tunable in a terminal."
    )
    desc.setObjectName("card-copy")
    desc.setWordWrap(True)
    layout.addWidget(desc)

    rows = QVBoxLayout()
    rows.setSpacing(0)
    page._clean_badges = {}
    for key, row_title, description, _fetch in TUNABLES:
        badge = PillBadge("checking…", "dim")
        page._clean_badges[key] = badge
        rows.addWidget(_make_setting_row(row_title, description, badge))
    layout.addLayout(rows)

    audit_row = QHBoxLayout()
    audit_row.setSpacing(8)
    page._audit_label = QLabel("")
    page._audit_label.setObjectName("prop-val-dim")
    page._audit_label.setWordWrap(True)
    audit_row.addWidget(page._audit_label, 1)
    audit_btn = QPushButton("Run full audit")
    audit_btn.setToolTip("Runs kyth_shared.perf_audit.collect_audit() — every tunable plus systemd-analyze")
    audit_btn.clicked.connect(page._run_audit)
    audit_row.addWidget(audit_btn)
    layout.addLayout(audit_row)
    return card
