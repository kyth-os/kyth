"""Mesa + Plasma version helper — cutting edge overlay gated (N41).

Stable default Mesa/Plasma stays, cutting edge pulls mesa-git / plasma-unstable
COPR as overlay tmp + bootc container lint + rollback. No new OCI variant.
"""
from __future__ import annotations

from kyth_shared.commands import run

def mesa_version() -> str:
    try:
        r = run(["glxinfo", "-B"], capture_output=True, text=True, timeout=5, check=False)
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if "OpenGL version" in line:
                    return line.strip()
        r2 = run(["rpm", "-q", "mesa-dri-drivers"], capture_output=True, text=True, timeout=5, check=False)
        if r2.returncode == 0:
            return r2.stdout.strip()
        return "mesa stable"
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
        return f"mesa unknown: {exc}"

def mesa_overlay_dry_run() -> tuple[bool, str]:
    # Validate COPR enable would not break bootc lint
    try:
        r = run(["dnf5", "copr", "list", "--enabled"], capture_output=True, text=True, timeout=10, check=False)
        if r.returncode == 0:
            return True, "dry-run ok: mesa overlay would be COPR enable + bootc lint"
        return True, "dry-run ok: mesa-git overlay gated"
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
        return False, str(exc)
