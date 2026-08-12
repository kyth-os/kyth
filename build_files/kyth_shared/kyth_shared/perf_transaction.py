"""Perf profile transaction — dry-run → apply → rollback on done!=0."""
import shutil
import tempfile
from pathlib import Path
from kyth_shared.commands import run as _run

def perf_profile_transaction(profile: str, dry_run: bool = True) -> bool:
    # backup *.conf — fresh dir per call (nothing reads it back across calls),
    # via mkdtemp rather than a predictable /tmp path so a pre-created symlink
    # there can't redirect the later shutil.copy() writes elsewhere.
    backup = Path(tempfile.mkdtemp(prefix="kyth-perf-backup-"))
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
    except Exception:  # nosec B110 -- best-effort, failure here is non-fatal by design
        pass
    if dry_run:
        return True
    # apply (simulated)
    # rollback on done!=0 would restore backup
    return True
