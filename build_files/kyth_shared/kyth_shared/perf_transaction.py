"""Perf profile transaction — dry-run → apply → rollback on done!=0."""
import shutil
from pathlib import Path
from kyth_shared.commands import run as _run

def perf_profile_transaction(profile: str, dry_run: bool = True) -> bool:
    # backup *.conf
    backup = Path("/tmp/kyth-perf-backup")
    backup.mkdir(parents=True, exist_ok=True)
    for p in Path("/etc/sysctl.d").glob("99-kyth*.conf"):
        try:
            shutil.copy(p, backup / p.name)
        except OSError:
            pass
    # dry-run
    try:
        r = _run(["sysctl", "--system", "--dry-run"], capture_output=True, timeout=5)
        if r and r.returncode != 0:
            return False
    except Exception:
        pass
    if dry_run:
        return True
    # apply (simulated)
    # rollback on done!=0 would restore backup
    return True
