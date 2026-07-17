"""bootc status, image reference, branch, and deployment helpers.

Pure stdlib — safe to import from CLI tools (update-watcher) without Qt.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from typing import Any

from .process import (
    _BOOTC_CACHE_TTL,
    _command_stdout,
    _probe_cached,
    _run_command,
)

REGISTRY = "ghcr.io/mrtrick37/kyth"


def nested_get(data: object, path: tuple[str, ...]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


# Underscore alias used across System Hub
_nested_get = nested_get


def walk_strings(data: object):
    if isinstance(data, str):
        yield data
        return
    if isinstance(data, dict):
        for value in data.values():
            yield from walk_strings(value)
        return
    if isinstance(data, list):
        for value in data:
            yield from walk_strings(value)


_walk_strings = walk_strings


def _fetch_bootc_status_text() -> str:
    for cmd in (["sudo", "-n", "bootc", "status"], ["bootc", "status"]):
        result = _run_command(cmd, timeout=10)
        if result is None or result.returncode != 0 or not result.stdout.strip():
            continue
        return result.stdout.strip()
    return ""


def _bootc_status_text() -> str:
    return _probe_cached("bootc-status-text", _BOOTC_CACHE_TTL, _fetch_bootc_status_text)


def _fetch_bootc_status_data() -> dict | None:
    for cmd in (["sudo", "-n", "bootc", "status", "--json"], ["bootc", "status", "--json"]):
        result = _run_command(cmd, timeout=10)
        if result is None or result.returncode != 0 or not result.stdout.strip():
            continue
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            continue
    return None


def _bootc_status_data() -> dict | None:
    return _probe_cached("bootc-status-data", _BOOTC_CACHE_TTL, _fetch_bootc_status_data)


def fetch_bootc_status_data_uncached() -> dict | None:
    """Root/CLI path: always re-query bootc (no probe cache)."""
    return _fetch_bootc_status_data()


def _active_bootc_operation() -> str | None:
    result = _run_command(["ps", "-eo", "pid=,args="], timeout=5)
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return None
    for line in result.stdout.splitlines():
        text = line.strip()
        if not text or " bootc " not in f" {text} ":
            continue
        if any(op in text for op in (" bootc upgrade", " bootc switch", " bootc rollback", " bootc reset")):
            return text
    return None


def _default_phase(mode: str) -> str:
    return {
        "update": "Pulling OS image from container registry…",
        "topgrade": "Running full system update…",
        "rollback": "Staging rollback deployment…",
    }.get(mode, "Operation in progress…")


def _bootc_proxy_running() -> bool:
    """True if skopeo image-proxy bootc spawns is still alive (download in progress)."""
    try:
        r = subprocess.run(
            ["pgrep", "-f", "skopeo.*image-proxy"],
            capture_output=True, timeout=2,
        )
        return r.returncode == 0
    except Exception:
        return False


def _parse_update_phase(line: str, mode: str) -> str | None:
    """Map a raw output line to a short human-readable phase label, or None to keep the last."""
    lo = line.lower()
    if "layers already present" in lo or "layers needed" in lo:
        return "Checking for new image layers…"
    if "resolved" in lo and ("image" in lo or REGISTRY in lo):
        return "Resolving OS image version…"
    if "fetching" in lo and ("manifest" in lo or "sha256" in lo):
        return "Fetching image manifest…"
    if any(k in lo for k in ("pulling", "copying", "fetching")) and any(
        k in lo for k in ("sha256", "blob", "layer", "ghcr.io", "registry")
    ):
        return "Downloading image layers…"
    if "unpacking" in lo or "extracting" in lo:
        return "Unpacking image layers…"
    if "checking out" in lo or "checkout" in lo or "importing" in lo:
        return "Importing image into system storage…"
    if "writing manifest" in lo or "manifest to image destination" in lo:
        return "Storing image manifest…"
    if "writing" in lo or "composing" in lo or "committing" in lo:
        return "Writing new OS image to disk…"
    if "rpmdb" in lo:
        return "Updating package database in the new image…"
    if "initramfs" in lo or "kernel" in lo:
        return "Preparing boot files for the new image…"
    if "deploying" in lo:
        return "Deploying new OS image…"
    if "staging" in lo or "staged" in lo or "transaction complete" in lo:
        return "Staging new image for next reboot…"
    if "no update available" in lo or "already booted" in lo:
        return "Already on the latest image — nothing to download."
    if "queued" in lo and "boot" in lo:
        return "Staged — new image ready for next reboot."
    if mode == "topgrade" and line.startswith("――"):
        m = re.match(r"――\s*[\d:]+\s*-\s*(.+?)\s*――", line)
        if m:
            section = m.group(1).strip()
            if section:
                return f"Updating {section}…"
    return None


def _bootc_cancel_block_reason(mode: str, phase: str) -> str:
    if mode == "rollback":
        return "Rollback is already staging the previous deployment. Let it finish, then reboot or update again."
    if phase in {
        "Unpacking image layers…",
        "Download complete — processing image layers…",
        "Processing image layers…",
        "Importing image into system storage…",
        "Storing image manifest…",
        "Writing new OS image to disk…",
        "Updating package database in the new image…",
        "Preparing boot files for the new image…",
        "Deploying new OS image…",
        "Staging new image for next reboot…",
        "Staged — new image ready for next reboot.",
    }:
        return "The operation is past the safe cancel point and is writing or staging the new image. Let it finish."
    if "writing image to disk" in phase.lower() or "committing image" in phase.lower():
        return "The operation is writing the new image. Let it finish."
    return ""


def image_reference_from_status(data: dict | None, *, status_text: str = "") -> str | None:
    """Resolve the booted image reference from bootc status JSON (and optional text)."""
    data = data or {}
    candidates = (
        ("status", "booted", "image", "reference"),
        ("status", "booted", "image", "image", "reference"),
        ("status", "booted", "image", "image", "image"),
        ("status", "booted", "image", "image"),
        ("status", "booted", "image"),
        ("spec", "image", "image"),
        ("spec", "image", "reference"),
    )
    for path in candidates:
        value = nested_get(data, path)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in walk_strings(data):
        stripped = value.strip()
        if REGISTRY in stripped:
            return stripped
    if status_text:
        pattern = re.compile(rf"({re.escape(REGISTRY)}(?::[A-Za-z0-9._-]+)?(?:@sha256:[a-fA-F0-9]+)?)")
        match = pattern.search(status_text)
        if match:
            return match.group(1)
    return None


def _bootc_image_reference() -> str | None:
    data = _bootc_status_data() or {}
    ref = image_reference_from_status(data)
    if ref:
        return ref
    text = _bootc_status_text()
    ref = image_reference_from_status(data, status_text=text)
    if ref:
        return ref
    # Fallback: rpm-ostree status (runs without root on ostree-managed systems)
    rpmostree = _run_command(["rpm-ostree", "status"], timeout=10)
    if rpmostree and rpmostree.returncode == 0:
        pattern = re.compile(rf"({re.escape(REGISTRY)}(?::[A-Za-z0-9._-]+)?(?:@sha256:[a-fA-F0-9]+)?)")
        match = pattern.search(rpmostree.stdout)
        if match:
            return match.group(1)
    return None


def _branch_from_ref(ref: str | None) -> str | None:
    if not ref:
        return None
    ref = ref.strip()
    if not ref:
        return None
    base = ref.split("@", 1)[0] if "@" in ref else ref
    if ":" in base:
        tag = base.rsplit(":", 1)[-1]
        if tag:
            return tag
    return None


def _branch_display_name(tag: str | None) -> str:
    if tag == "latest":
        return "Stable (latest)"
    if tag == "testing":
        return "Testing"
    if tag == "latest-cachy":
        return "Stable + CachyOS kernel"
    if tag == "testing-cachy":
        return "Testing + CachyOS kernel"
    return tag or "unknown"


def _current_branch() -> str | None:
    def fetch() -> str | None:
        return _branch_from_ref(_bootc_image_reference())

    return _probe_cached("bootc-branch", _BOOTC_CACHE_TTL, fetch)


def _current_kernel_flavor() -> str:
    def fetch() -> str:
        try:
            with open("/usr/share/kyth/kernel-flavor") as fh:
                flavor = fh.read().strip().lower()
                if flavor in {"fedora", "cachy"}:
                    return flavor
        except OSError:
            pass
        kernel = _command_stdout(["uname", "-r"]).lower()
        if "cachy" in kernel:
            return "cachy"
        return "fedora"

    return _probe_cached("kernel-flavor", 60.0, fetch)


def _image_tag_for_channel(channel: str, flavor: str | None = None) -> str:
    base = "testing" if channel == "testing" else "latest"
    flavor = flavor or _current_kernel_flavor()
    suffix = "-cachy" if flavor == "cachy" else ""
    return f"{base}{suffix}"


def _image_tag_for_kernel(flavor: str) -> str:
    channel = "testing" if (_current_branch() or "").startswith("testing") else "latest"
    if flavor == "cachy":
        return f"{channel}-cachy"
    return channel


def _has_staged_update() -> bool:
    data = _bootc_status_data() or {}
    return data.get("status", {}).get("staged") is not None


def _has_rollback_deployment() -> bool:
    data = _bootc_status_data() or {}
    return data.get("status", {}).get("rollback") is not None


def image_digest_from_status(status_data: dict | None, section: str) -> str | None:
    """Return full ``sha256:…`` digest for booted/staged/rollback, or None."""
    data = status_data or {}
    section_data = nested_get(data, ("status", section)) or {}
    for path in (
        ("image", "imageDigest"),
        ("image", "digest"),
        ("imageDigest",),
        ("digest",),
    ):
        value = nested_get(section_data, path)
        if isinstance(value, str) and value.startswith("sha256:"):
            return value
    return None


def _bootc_image_timestamp(section: str) -> str | None:
    """Human-readable build timestamp for 'booted', 'staged', or 'rollback'."""
    data = _bootc_status_data() or {}
    section_data = nested_get(data, ("status", section)) or {}
    for path in (("image", "timestamp"), ("timestamp",)):
        value = nested_get(section_data, path)
        if isinstance(value, str) and value.strip():
            try:
                dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00")).astimezone()
                return dt.strftime("%Y-%m-%d %H:%M %Z")
            except Exception:
                return value.strip()
    return None


def _bootc_image_digest(section: str) -> tuple[str, str] | None:
    """Return (short, full) sha256 digest for section. None if unavailable."""
    value = image_digest_from_status(_bootc_status_data(), section)
    if value is None:
        return None
    full = value[7:]  # strip "sha256:"
    return full[:12], full
