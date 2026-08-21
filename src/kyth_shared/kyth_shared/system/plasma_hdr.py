"""Plasma HDR / VRR presets with transactional kwinrc rollback.

Plasma 6 stores global VRR under ``[Wayland] VrrPolicy`` (0=Never, 1=Automatic,
2=Always). Per-output HDR/WCG is applied via ``kscreen-doctor`` when a live
session is available. Writes go through ``kwriteconfig6`` (with fallbacks) after
backing up ``kwinrc``; on failure the backup is restored.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path

from kyth_shared.commands import run as _run
from kyth_shared.guardian_actions import parse_kscreen_outputs

logger = logging.getLogger(__name__)

_OUTPUT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# Global kwinrc keys only — HDR itself is per-output (see _apply_output_hdr).
_PRESETS: dict[str, dict[str, dict[str, str]]] = {
    "hdr": {
        "Wayland": {"VrrPolicy": "1"},
        "Compositing": {"AllowTearing": "false", "LatencyPolicy": "Low"},
    },
    "hdr10plus": {
        "Wayland": {"VrrPolicy": "1"},
        "Compositing": {"AllowTearing": "false", "LatencyPolicy": "Low"},
    },
    "sdr": {
        "Wayland": {"VrrPolicy": "1"},
        "Compositing": {"AllowTearing": "false", "LatencyPolicy": "Low"},
    },
    "vrr": {"Wayland": {"VrrPolicy": "1"}},
    "vrr_off": {"Wayland": {"VrrPolicy": "0"}},
    "vrr_always": {"Wayland": {"VrrPolicy": "2"}},
}

_HDR_ENABLE = frozenset({"hdr", "hdr10plus"})
_HDR_DISABLE = frozenset({"sdr"})


def _kwinrc_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(xdg) / "kwinrc"


def _kwriteconfig_bin() -> str | None:
    return shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5") or shutil.which("kwriteconfig")


def _qdbus_bin() -> str | None:
    for name in ("qdbus6", "qdbus-qt6", "qdbus"):
        found = shutil.which(name)
        if found:
            return found
    return None


def available_presets() -> list[str]:
    return sorted(_PRESETS.keys())


def _write_kwin_keys(preset: dict[str, dict[str, str]]) -> list[str]:
    bin_name = _kwriteconfig_bin()
    if not bin_name:
        raise RuntimeError("kwriteconfig6/5 not found")
    applied: list[str] = []
    for section, keys in preset.items():
        for key, value in keys.items():
            args = [bin_name, "--file", "kwinrc", "--group", section, "--key", key, value]
            res = _run(args, capture_output=True, timeout=5, check=False)
            if res.returncode != 0:
                err = (res.stderr or res.stdout or "").strip()[:200]
                raise RuntimeError(f"kwriteconfig failed for [{section}]{key}: {err or res.returncode}")
            applied.append(f"{section}.{key}={value}")
    return applied


def _reconfigure_kwin() -> None:
    qdbus = _qdbus_bin()
    if not qdbus:
        return
    try:
        _run(
            [qdbus, "org.kde.KWin", "/KWin", "reconfigure"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, ValueError, RuntimeError):
        logger.debug("kwin reconfigure skipped", exc_info=True)


def _session_is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def _apply_output_hdr(enable: bool) -> list[str]:
    """Best-effort per-output HDR/WCG via kscreen-doctor (Wayland only)."""
    if not shutil.which("kscreen-doctor"):
        return ["kscreen-doctor unavailable"]
    if not _session_is_wayland():
        return ["hdr skipped: not a Wayland session"]
    listed = _run(["kscreen-doctor", "-o"], capture_output=True, timeout=8, check=False)
    if listed.returncode != 0:
        return ["kscreen-doctor -o failed"]
    notes: list[str] = []
    action = "enable" if enable else "disable"
    for output in parse_kscreen_outputs(listed.stdout or ""):
        name = str(output.get("name") or "")
        if not _OUTPUT_NAME_RE.fullmatch(name):
            continue
        if not output.get("connected"):
            continue
        # Enable WCG with HDR so colors match System Settings; disable both for SDR.
        cmd = [
            "kscreen-doctor",
            f"output.{name}.hdr.{action}",
            f"output.{name}.wcg.{action}",
        ]
        try:
            res = _run(cmd, capture_output=True, timeout=12, check=False)
            if res.returncode == 0:
                notes.append(f"{name}.hdr.{action}")
            else:
                notes.append(f"{name}.hdr.{action} failed")
        except (OSError, ValueError, RuntimeError) as exc:
            notes.append(f"{name}.hdr.{action}: {exc}")
    return notes or ["no connected outputs"]


def apply_preset(name: str, dry_run: bool = False) -> tuple[bool, str]:
    """Apply KWin/kscreen preset transactionally. Returns (ok, msg)."""
    if name not in _PRESETS:
        return False, f"unknown preset: {name}"
    if dry_run:
        return True, f"dry-run ok: {name}"

    kwinrc = _kwinrc_path()
    backup: str | None = None
    try:
        if kwinrc.exists():
            backup = kwinrc.read_text(encoding="utf-8")
        applied = _write_kwin_keys(_PRESETS[name])
        hdr_notes: list[str] = []
        if name in _HDR_ENABLE:
            hdr_notes = _apply_output_hdr(True)
        elif name in _HDR_DISABLE:
            hdr_notes = _apply_output_hdr(False)
        _reconfigure_kwin()
        parts = [f"applied {name}"] + applied + hdr_notes
        return True, "; ".join(parts)
    except (OSError, ValueError, RuntimeError) as exc:
        if backup is not None:
            try:
                kwinrc.write_text(backup, encoding="utf-8")
            except OSError:
                logger.warning("failed to restore kwinrc after preset error", exc_info=True)
        elif kwinrc.exists():
            try:
                kwinrc.unlink()
            except OSError:
                logger.debug("could not remove partial kwinrc", exc_info=True)
        return False, str(exc)


def preset_status(name: str) -> str:
    if name not in _PRESETS:
        return f"unknown preset: {name}"
    kwinrc = _kwinrc_path()
    if not kwinrc.exists():
        return "kwinrc not found"
    try:
        txt = kwinrc.read_text(encoding="utf-8")
    except OSError as exc:
        return str(exc)

    # Section-aware match: key must appear under the expected [section] header.
    current_section = ""
    wanted = {
        (section, key, value)
        for section, keys in _PRESETS[name].items()
        for key, value in keys.items()
    }
    found: set[tuple[str, str, str]] = set()
    for raw in txt.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1]
            continue
        if "=" not in line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        candidate = (current_section, key, value)
        if candidate in wanted:
            found.add(candidate)
    missing = wanted - found
    if missing:
        section, key, value = sorted(missing)[0]
        return f"[{section}]{key}={value} not active"
    return "active"
