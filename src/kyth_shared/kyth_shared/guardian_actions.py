"""Bounded multi-step executors for Guardian recipes that are more than one argv.

Each helper takes the same ``run(argv, timeout)`` callable Guardian uses, so
tests can inject mocks without going through a shell. Commands stay argv lists
with validated identifiers — no ``bash -c`` and no ``|| true`` success.
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable

Run = Callable[..., Any]

_OUTPUT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_SINK_NAME_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
_NM_NAME_RE = re.compile(r"^[A-Za-z0-9 _.-]+$")
_DUMMY_SINKS = frozenset({"auto_null", "@DEFAULT_SINK@", "auto_null.monitor"})


def parse_kscreen_outputs(text: str) -> list[dict[str, Any]]:
    """Parse ``kscreen-doctor -o`` into name/connected/enabled records."""
    outputs: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Output:"):
            if current is not None:
                outputs.append(current)
            parts = line.split()
            name = parts[2] if len(parts) > 2 else parts[-1] if len(parts) > 1 else ""
            current = {"name": name, "connected": False, "enabled": False}
            continue
        if current is None:
            continue
        lowered = line.lower()
        if lowered == "connected":
            current["connected"] = True
        elif lowered == "disconnected":
            current["connected"] = False
        elif lowered == "enabled":
            current["enabled"] = True
        elif lowered == "disabled":
            current["enabled"] = False
    if current is not None:
        outputs.append(current)
    return outputs


def apply_display_reconfigure(run: Run) -> tuple[bool, str]:
    """Reload KScreen, then enable any connected-but-disabled outputs."""
    notes: list[str] = []
    restart = run(("systemctl", "--user", "restart", "plasma-kscreen.service"), 10)
    if restart is not None and restart.returncode == 0:
        notes.append("plasma-kscreen restarted")
    listed = run(("kscreen-doctor", "-o"), 8)
    if listed is None:
        return bool(notes), "; ".join(notes) or "kscreen-doctor unavailable"
    if listed.returncode != 0:
        err = ((listed.stderr or listed.stdout or "").strip()[:200])
        if notes:
            return True, "; ".join(notes) + (f"; kscreen-doctor: {err}" if err else "")
        return False, err or "kscreen-doctor failed"
    enabled_any = False
    for output in parse_kscreen_outputs(listed.stdout or ""):
        name = str(output.get("name") or "")
        if not _OUTPUT_NAME_RE.fullmatch(name):
            continue
        if output.get("connected") and not output.get("enabled"):
            applied = run(("kscreen-doctor", f"output.{name}.enable"), 8)
            if applied is not None and applied.returncode == 0:
                notes.append(f"enabled {name}")
                enabled_any = True
            else:
                notes.append(f"enable {name} failed")
    if notes or enabled_any:
        return True, "; ".join(notes)
    # Query succeeded and every connected output is already enabled.
    return True, "display outputs already enabled"


def restore_audio_sink(run: Run) -> tuple[bool, str]:
    """Set the default sink to the first real device; never report success on dummy."""
    real = _real_sinks(run)
    if real:
        applied = run(("pactl", "set-default-sink", real[0]), 6)
        if applied is not None and applied.returncode == 0:
            return True, f"default sink set to {real[0]}"
    pulse = run(("systemctl", "--user", "restart", "pipewire-pulse.service"), 10)
    if pulse is None or pulse.returncode != 0:
        return False, "no usable audio sink"
    real = _real_sinks(run)
    if not real:
        return False, "no usable audio sink after pipewire-pulse restart"
    applied = run(("pactl", "set-default-sink", real[0]), 6)
    if applied is None or applied.returncode != 0:
        return False, "failed to set default audio sink"
    return True, f"default sink set to {real[0]}"


def _real_sinks(run: Run) -> list[str]:
    listed = run(("pactl", "list", "short", "sinks"), 6)
    if listed is None or listed.returncode != 0:
        return []
    names: list[str] = []
    for line in (listed.stdout or "").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[1]
        if name in _DUMMY_SINKS or "auto_null" in name:
            continue
        if _SINK_NAME_RE.fullmatch(name):
            names.append(name)
    return names


def reset_power_profile(run: Run) -> tuple[bool, str]:
    for profile in ("balanced", "performance"):
        result = run(("powerprofilesctl", "set", profile), 6)
        if result is not None and result.returncode == 0:
            return True, f"power profile set to {profile}"
    return False, "powerprofilesctl could not set a profile"


def flush_dns(run: Run) -> tuple[bool, str]:
    resolved = run(("resolvectl", "flush-caches"), 6)
    if resolved is not None and resolved.returncode == 0:
        return True, "flushed systemd-resolved caches"
    legacy = run(("systemd-resolve", "--flush-caches"), 6)
    if legacy is not None and legacy.returncode == 0:
        return True, "flushed systemd-resolve caches"
    return False, "DNS cache flush unavailable"


def recapture_network(run: Run) -> tuple[bool, str]:
    """Re-toggle NetworkManager to clear captive-portal / local-only state."""
    off = run(("nmcli", "networking", "off"), 8)
    if off is None or off.returncode != 0:
        return False, "nmcli networking off failed"
    time.sleep(2)
    on = run(("nmcli", "networking", "on"), 8)
    if on is None or on.returncode != 0:
        return False, "failed to re-enable networking"
    active = run(("nmcli", "-t", "-f", "NAME", "connection", "show", "--active"), 5)
    name = ""
    if active is not None and active.returncode == 0:
        name = (active.stdout or "").splitlines()[0].strip() if (active.stdout or "").strip() else ""
    if name and _NM_NAME_RE.fullmatch(name):
        run(("nmcli", "connection", "up", name), 15)
    return True, "networking re-toggled"


def restore_autoconnect_vpn(run: Run) -> tuple[bool, str]:
    """Bring up at most one always-on VPN profile. Idle VPN profiles are ignored."""
    listed = run(("nmcli", "-t", "-f", "NAME,TYPE,AUTOCONNECT", "connection", "show"), 6)
    active = run(("nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active"), 5)
    active_vpn: set[str] = set()
    if active is not None and active.returncode == 0:
        for line in (active.stdout or "").splitlines():
            parts = line.split(":")
            if len(parts) >= 2 and parts[-1] == "vpn":
                active_vpn.add(":".join(parts[:-1]))
    if listed is None or listed.returncode != 0:
        return False, "nmcli connection list failed"
    for line in (listed.stdout or "").splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        autoconnect = parts[-1].lower()
        conn_type = parts[-2]
        name = ":".join(parts[:-2])
        if conn_type != "vpn" or autoconnect != "yes":
            continue
        if name in active_vpn:
            continue
        if not _NM_NAME_RE.fullmatch(name):
            continue
        brought = run(("nmcli", "connection", "up", name), 15)
        if brought is not None and brought.returncode == 0:
            return True, f"brought up VPN {name}"
        return False, f"failed to bring up VPN {name}"
    return False, "no always-on VPN needed reconnecting"


def restart_joycond(run: Run) -> tuple[bool, str]:
    """Restart the system joycond unit via sudo -A (graphical askpass when present)."""
    result = run(("sudo", "-A", "systemctl", "restart", "joycond.service"), 20)
    if result is None:
        return False, "joycond restart failed to start"
    if result.returncode != 0:
        return False, ((result.stderr or result.stdout or "").strip()[:200] or "joycond restart failed")
    return True, "joycond restarted"


ACTION_EXECUTORS: dict[str, Callable[[Run], tuple[bool, str]]] = {
    "display.reconfigure": apply_display_reconfigure,
    "audio.sink-fallback": restore_audio_sink,
    "power.profile-fix": reset_power_profile,
    "network.dns-flush": flush_dns,
    "network.captive-fix": recapture_network,
    "network.vpn-fix": restore_autoconnect_vpn,
    "controller.repair": restart_joycond,
}
