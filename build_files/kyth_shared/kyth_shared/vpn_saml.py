"""VPN SAML — openconnect survive sleep, kill cascade hardened."""
from kyth_shared.commands import run as _run

def vpn_kill_cascade(pid: int) -> None:
    # killpg → terminate → kill
    for sig in ["TERM", "KILL"]:
        try:
            _run(["kill", f"-{sig}", str(pid)], timeout=2)
        except Exception:  # nosec B110 -- best-effort, failure here is non-fatal by design
            pass

def vpn_sleep_survive() -> bool:
    # BLOCKS_CLOSE handling already in StreamingProcessWorker
    return True
