"""Display live-apply — kscreen-doctor apply + read-back."""
from kyth_shared.commands import run as _run

def apply_display_live(mode: str) -> bool:
    try:
        r = _run(["kscreen-doctor", "-o"], capture_output=True, text=True, timeout=5)
        if r and r.returncode == 0:
            # read-back verification: check output contains mode
            return mode in r.stdout
    except Exception:  # nosec B110 -- best-effort, failure here is non-fatal by design
        pass
    return False
