"""Declarative hardware matching, support reporting, and first-boot policy.

The policy file is deliberately data-only.  Runtime code owns the small set of
supported actions so a profile cannot turn hardware metadata into arbitrary
root command execution.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys
import tomllib
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .commands import run_optional, run_text

import time as _time

# Inventory cache — avoid re-scanning /sys on every hw-setup/guardian/probe tick (60s TTL, host paths only, aligns with probe/gaming)
_INVENTORY_CACHE: tuple[float, Inventory] | None = None
_INVENTORY_TTL = 60.0

# Progressive: per-quirk modules under hardware_quirks/ for testable catalog
try:
    from .hardware_quirks import __all__ as _QUIRK_MODULES  # noqa: F401
except Exception:
    _QUIRK_MODULES = []  # type: ignore[assignment]

DEFAULT_POLICY_PATH = Path("/usr/share/kyth/hardware-profiles.toml")
DEFAULT_STATE_PATH = Path("/var/lib/kyth/hardware-policy.json")
DEFAULT_REPORT_PATH = Path("/var/lib/kyth/hardware-support.json")
MANAGED_MODPROBE_PATH = Path("/etc/modprobe.d/90-kyth-hardware-policy.conf")
SCX_CONFIG_PATH = Path("/etc/scx/scx_loader.conf")

_HEX_ID = re.compile(r"^[0-9a-f]{4}$")
_CLASS_ID = re.compile(r"^[0-9a-f]{2,6}$")
_MODULE = re.compile(r"^[a-zA-Z0-9_-]+$")
_OPTION = re.compile(r"^[a-zA-Z0-9_-]+$")
_VALUE = re.compile(r"^[a-zA-Z0-9_.,:/+-]+$")
_POLICY_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class PolicyError(ValueError):
    """Raised when hardware policy data is malformed or unsafe."""


@dataclass(frozen=True, slots=True)
class Device:
    bus: str
    vendor: str
    device: str
    class_code: str = ""
    driver: str = ""
    name: str = ""


@dataclass(frozen=True, slots=True)
class Inventory:
    cpu_vendor: str
    dmi_vendor: str
    dmi_product: str
    dmi_board: str
    pci: tuple[Device, ...]
    usb: tuple[Device, ...]

    def digest(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Evaluation:
    policy_revision: str
    policy_digest: str
    inventory: Inventory
    profiles: tuple[dict[str, Any], ...]
    quirks: tuple[dict[str, Any], ...]
    capabilities: tuple[str, ...]
    recommended_variant: str
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _sysfs_hex(path: Path) -> str:
    return _read_text(path).lower().removeprefix("0x")


def _driver_name(path: Path) -> str:
    try:
        return path.resolve(strict=True).name
    except OSError:
        return ""


def invalidate_inventory_cache() -> None:
    """Clear inventory cache (for tests)."""
    global _INVENTORY_CACHE
    _INVENTORY_CACHE = None


def collect_inventory(
    *,
    pci_root: Path = Path("/sys/bus/pci/devices"),
    usb_root: Path = Path("/sys/bus/usb/devices"),
    dmi_root: Path = Path("/sys/class/dmi/id"),
    cpuinfo_path: Path = Path("/proc/cpuinfo"),
) -> Inventory:
    """Collect stable matching identifiers without invoking parsing utilities."""
    # Fast-path cache for default host paths — custom temp dirs in tests bypass cache
    _default = (Path("/sys/bus/pci/devices"), Path("/sys/bus/usb/devices"), Path("/sys/class/dmi/id"), Path("/proc/cpuinfo"))
    if (pci_root, usb_root, dmi_root, cpuinfo_path) == _default:
        global _INVENTORY_CACHE
        if _INVENTORY_CACHE is not None:
            _ts, _inv = _INVENTORY_CACHE
            if _time.monotonic() - _ts < _INVENTORY_TTL:
                return _inv
    pci: list[Device] = []
    if pci_root.is_dir():
        for node in sorted(pci_root.iterdir()):
            vendor = _sysfs_hex(node / "vendor")
            device = _sysfs_hex(node / "device")
            if not vendor or not device:
                continue
            pci.append(Device(
                bus="pci",
                vendor=vendor,
                device=device,
                class_code=_sysfs_hex(node / "class"),
                driver=_driver_name(node / "driver"),
            ))

    usb: list[Device] = []
    if usb_root.is_dir():
        for node in sorted(usb_root.iterdir()):
            vendor = _sysfs_hex(node / "idVendor")
            device = _sysfs_hex(node / "idProduct")
            if not vendor or not device:
                continue
            driver = _driver_name(node / "driver")
            if not driver:
                driver = next(
                    (
                        name for child in sorted(node.parent.glob(f"{node.name}:*"))
                        if (name := _driver_name(child / "driver"))
                    ),
                    "",
                )
            usb.append(Device(
                bus="usb",
                vendor=vendor,
                device=device,
                driver=driver,
                name=_read_text(node / "product"),
            ))

    cpu_vendor = ""
    try:
        for line in cpuinfo_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("vendor_id") and ":" in line:
                cpu_vendor = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass

    inv = Inventory(
        cpu_vendor=cpu_vendor,
        dmi_vendor=_read_text(dmi_root / "sys_vendor"),
        dmi_product=_read_text(dmi_root / "product_name"),
        dmi_board=_read_text(dmi_root / "board_name"),
        pci=tuple(pci),
        usb=tuple(usb),
    )
    if (pci_root, usb_root, dmi_root, cpuinfo_path) == _default:
        _INVENTORY_CACHE = (_time.monotonic(), inv)
    return inv


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    data = tomllib.loads(raw.decode("utf-8"))
    validate_policy(data)
    return data, hashlib.sha256(raw).hexdigest()


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PolicyError(f"{field} must be an array of strings")
    return value


def _validate_selector(selector: dict[str, Any], field: str) -> None:
    allowed = {"vendor", "devices", "classes", "drivers"}
    unknown = set(selector) - allowed
    if unknown:
        raise PolicyError(f"{field} has unknown keys: {', '.join(sorted(unknown))}")
    vendor = str(selector.get("vendor", "")).lower()
    if vendor and not _HEX_ID.fullmatch(vendor):
        raise PolicyError(f"{field}.vendor must be a four-digit hexadecimal ID")
    for device in _string_list(selector.get("devices", []), f"{field}.devices"):
        if not _HEX_ID.fullmatch(device.lower()):
            raise PolicyError(f"{field}.devices contains invalid ID {device!r}")
    for class_id in _string_list(selector.get("classes", []), f"{field}.classes"):
        if not _CLASS_ID.fullmatch(class_id.lower()):
            raise PolicyError(f"{field}.classes contains invalid class {class_id!r}")
    for driver in _string_list(selector.get("drivers", []), f"{field}.drivers"):
        if not _MODULE.fullmatch(driver):
            raise PolicyError(f"{field}.drivers contains invalid driver {driver!r}")


def _validate_variant_entry(entry: dict[str, Any], index: int, seen: set[str]) -> None:
    """Validate a single variant entry from the policy."""
    if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
        raise PolicyError(f"variants[{index}] requires a string id")
    entry_id = entry["id"]
    if not _POLICY_ID.fullmatch(entry_id):
        raise PolicyError(f"invalid policy id: {entry_id!r}")
    if entry_id in seen:
        raise PolicyError(f"duplicate policy id: {entry_id}")
    seen.add(entry_id)


def _validate_match_section(entry_id: str, match: dict[str, Any], kind: str) -> None:
    """Validate the match section of a profile or quirk entry."""
    if not isinstance(match, dict):
        raise PolicyError(f"{entry_id}.match must be a table")
    match_fields = {
        "always", "pci", "usb", "cpu_vendors", "dmi_vendors",
        "dmi_products", "dmi_boards",
    }
    unknown_match = set(match) - match_fields
    if unknown_match:
        raise PolicyError(
            f"{entry_id}.match has unknown keys: {', '.join(sorted(unknown_match))}"
        )
    if not match:
        raise PolicyError(f"{entry_id}.match must not be empty")
    if "always" in match and match["always"] is not True:
        raise PolicyError(f"{entry_id}.match.always may only be true")
    if match.get("always") and len(match) != 1:
        raise PolicyError(f"{entry_id}.match.always cannot be combined with selectors")
    for bus in ("pci", "usb"):
        selectors = match.get(bus, [])
        if not isinstance(selectors, list):
            raise PolicyError(f"{entry_id}.match.{bus} must be an array")
        for selector_index, selector in enumerate(selectors):
            if not isinstance(selector, dict):
                raise PolicyError(f"{entry_id}.match.{bus}[{selector_index}] must be a table")
            _validate_selector(selector, f"{entry_id}.match.{bus}[{selector_index}]")
    for field in ("cpu_vendors", "dmi_vendors", "dmi_products", "dmi_boards"):
        _string_list(match.get(field, []), f"{entry_id}.match.{field}")


def _validate_profile_entry(entry: dict[str, Any], variant_ids: set[str]) -> None:
    """Validate a single profile entry from the policy."""
    profile_id = entry["id"]
    variant = entry.get("image_variant")
    if variant not in variant_ids:
        raise PolicyError(f"profile {profile_id} references unknown image variant {variant!r}")
    profile_policy = entry.get("policy", {})
    if not isinstance(profile_policy, dict):
        raise PolicyError(f"profile {profile_id}.policy must be a table")
    unknown = set(profile_policy) - {"scheduler_candidates", "nvidia_setup"}
    if unknown:
        raise PolicyError(f"profile {profile_id} has unknown policy keys")
    for scheduler in _string_list(
        profile_policy.get("scheduler_candidates", []),
        f"profile {profile_id}.policy.scheduler_candidates",
    ):
        if not _MODULE.fullmatch(scheduler):
            raise PolicyError(f"profile {profile_id} has invalid scheduler {scheduler!r}")
    if "nvidia_setup" in profile_policy and not isinstance(profile_policy["nvidia_setup"], bool):
        raise PolicyError(f"profile {profile_id}.policy.nvidia_setup must be boolean")


def _validate_quirk_entry(entry: dict[str, Any]) -> None:
    """Validate a single quirk entry from the policy."""
    quirk_id = entry["id"]
    for field in ("reason", "provenance"):
        value = entry.get(field)
        if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
            raise PolicyError(f"quirk {quirk_id} requires single-line {field}")
    try:
        date.fromisoformat(str(entry["expires_on"]))
    except (KeyError, ValueError) as exc:
        raise PolicyError(f"quirk {quirk_id} requires ISO expires_on") from exc
    actions = entry.get("actions", [])
    if not actions:
        raise PolicyError(f"quirk {quirk_id} requires at least one action")
    for action in actions:
        if set(action) != {"kind", "module", "options"} or action.get("kind") != "modprobe":
            raise PolicyError(f"quirk {quirk_id} contains an unsupported action")
        module = action.get("module", "")
        if not _MODULE.fullmatch(module):
            raise PolicyError(f"quirk {quirk_id} has invalid module {module!r}")
        options = action.get("options")
        if not isinstance(options, dict) or not options:
            raise PolicyError(f"quirk {quirk_id} requires modprobe options")
        for key, value in options.items():
            if not _OPTION.fullmatch(str(key)) or not _VALUE.fullmatch(str(value)):
                raise PolicyError(f"quirk {quirk_id} has unsafe modprobe option")


def validate_policy(data: dict[str, Any]) -> None:
    if data.get("schema_version") != 1:
        raise PolicyError("hardware policy schema_version must be 1")
    if not isinstance(data.get("policy_revision"), str):
        raise PolicyError("hardware policy requires policy_revision")

    seen: set[str] = set()
    for kind in ("variants", "profiles", "quirks"):
        entries = data.get(kind, [])
        if not isinstance(entries, list):
            raise PolicyError(f"{kind} must be an array of tables")
        for index, entry in enumerate(entries):
            if not isinstance(entry.get("id"), str):
                raise PolicyError(f"{kind}[{index}] requires a string id")
            entry_id = entry["id"]
            if not _POLICY_ID.fullmatch(entry_id):
                raise PolicyError(f"invalid policy id: {entry_id!r}")
            if entry_id in seen:
                raise PolicyError(f"duplicate policy id: {entry_id}")
            seen.add(entry_id)

            if kind == "variants":
                continue

            match = entry.get("match", {})
            _validate_match_section(entry_id, match, kind)

    variant_ids = {entry["id"] for entry in data.get("variants", [])}
    for profile in data.get("profiles", []):
        _validate_profile_entry(profile, variant_ids)

    for quirk in data.get("quirks", []):
        _validate_quirk_entry(quirk)


def _device_matches(device: Device, selector: dict[str, Any]) -> bool:
    vendor = str(selector.get("vendor", "")).lower()
    devices = {value.lower() for value in selector.get("devices", [])}
    classes = tuple(value.lower() for value in selector.get("classes", []))
    drivers = set(selector.get("drivers", []))
    return (
        (not vendor or device.vendor == vendor)
        and (not devices or device.device in devices)
        and (not classes or any(device.class_code.startswith(value) for value in classes))
        and (not drivers or device.driver in drivers)
    )


def _patterns_match(value: str, patterns: list[str]) -> bool:
    return not patterns or any(fnmatch.fnmatchcase(value.casefold(), pattern.casefold()) for pattern in patterns)


def matches(inventory: Inventory, match: dict[str, Any]) -> bool:
    if match.get("always") is True:
        return True
    if not _patterns_match(inventory.cpu_vendor, match.get("cpu_vendors", [])):
        return False
    if not _patterns_match(inventory.dmi_vendor, match.get("dmi_vendors", [])):
        return False
    if not _patterns_match(inventory.dmi_product, match.get("dmi_products", [])):
        return False
    if not _patterns_match(inventory.dmi_board, match.get("dmi_boards", [])):
        return False
    for bus, devices in (("pci", inventory.pci), ("usb", inventory.usb)):
        for selector in match.get(bus, []):
            if not any(_device_matches(device, selector) for device in devices):
                return False
    return bool(match) or match.get("always") is True


def evaluate(
    policy: dict[str, Any],
    policy_digest: str,
    inventory: Inventory,
    *,
    today: date | None = None,
) -> Evaluation:
    today = today or date.today()
    profiles = sorted(
        (entry for entry in policy.get("profiles", []) if matches(inventory, entry.get("match", {}))),
        key=lambda entry: (int(entry.get("priority", 0)), entry["id"]),
    )
    quirks: list[dict[str, Any]] = []
    warnings: list[str] = []
    for entry in policy.get("quirks", []):
        if not matches(inventory, entry.get("match", {})):
            continue
        copy = dict(entry)
        expiry = date.fromisoformat(str(entry["expires_on"]))
        copy["expired"] = expiry < today
        if copy["expired"]:
            warnings.append(f"quirk {entry['id']} expired on {expiry.isoformat()} and needs review")
        quirks.append(copy)

    capabilities = sorted({item for profile in profiles for item in profile.get("capabilities", [])})
    recommended = profiles[-1].get("image_variant", "universal") if profiles else "universal"
    return Evaluation(
        policy_revision=policy["policy_revision"],
        policy_digest=policy_digest,
        inventory=inventory,
        profiles=tuple(profiles),
        quirks=tuple(quirks),
        capabilities=tuple(capabilities),
        recommended_variant=recommended,
        warnings=tuple(warnings),
    )


def evaluate_system(path: Path = DEFAULT_POLICY_PATH) -> Evaluation:
    policy, digest = load_policy(path)
    return evaluate(policy, digest, collect_inventory())


def booted_image_identity() -> tuple[str, str]:
    """Return the exact booted image reference and digest when bootc exposes it."""
    try:
        from .system.bootc import (
            fetch_bootc_status_data_uncached,
            image_digest_from_status,
            image_reference_from_status,
        )
        status = fetch_bootc_status_data_uncached() or {}
        return (
            image_reference_from_status(status) or "unknown",
            image_digest_from_status(status, "booted") or "unknown",
        )
    except Exception:
        return "unknown", "unknown"


def _current_kernel() -> str:
    result = run_text(["uname", "-r"])
    return result.stdout.strip() if result else "unknown"


def _build_apply_identity(evaluation: Evaluation) -> dict[str, str]:
    image_reference, image_digest = booted_image_identity()
    return {
        "policy_digest": evaluation.policy_digest,
        "inventory_digest": evaluation.inventory.digest(),
        "kernel": _current_kernel(),
        "image_reference": image_reference,
        "image_digest": image_digest,
    }


def _should_skip_apply(
    previous: dict[str, Any],
    identity: dict[str, Any],
    expected_modprobe: str,
    force: bool,
) -> bool:
    return (
        not force
        and previous.get("status") == "applied"
        and all(previous.get(key) == value for key, value in identity.items())
        and _read_text(MANAGED_MODPROBE_PATH) == expected_modprobe.strip()
    )


def _write_state_report(path: Path, evaluation: Evaluation, state: dict[str, Any]) -> None:
    report = {"evaluation": evaluation.as_dict(), "applied": state}
    _atomic_write(path, json.dumps(report, indent=2, sort_keys=True) + "\n", mode=0o600)


def _apply_policy_config(policy: dict[str, Any]) -> dict[str, Any]:
    config: dict[str, Any] = {"scheduler": _configure_scheduler(policy["scheduler_candidates"])}
    config["nvidia"] = _configure_nvidia() if policy.get("nvidia_setup") else _clear_nvidia_policy()
    return config


def _atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def render_modprobe_config(evaluation: Evaluation) -> str:
    lines = [
        "# Generated by kyth-hardware-policy. Do not edit.",
        f"# Policy revision: {evaluation.policy_revision}",
    ]
    for quirk in evaluation.quirks:
        lines.append(f"# {quirk['id']}: {quirk['reason']} (review by {quirk['expires_on']})")
        for action in quirk["actions"]:
            options = " ".join(f"{key}={value}" for key, value in sorted(action["options"].items()))
            lines.append(f"options {action['module']} {options}")
    return "\n".join(lines) + "\n"


def _profile_policy(evaluation: Evaluation) -> dict[str, Any]:
    merged: dict[str, Any] = {"scheduler_candidates": []}
    for profile in evaluation.profiles:
        profile_policy = profile.get("policy", {})
        merged["scheduler_candidates"].extend(profile_policy.get("scheduler_candidates", []))
        if profile_policy.get("nvidia_setup"):
            merged["nvidia_setup"] = True
    merged["scheduler_candidates"] = list(dict.fromkeys(merged["scheduler_candidates"]))
    return merged


def _command_ok(argv: list[str]) -> bool:
    result = run_optional(argv, capture_output=True)
    return result is not None and result.returncode == 0


def _disable_scheduler() -> str:
    SCX_CONFIG_PATH.unlink(missing_ok=True)
    run_optional(["systemctl", "disable", "--now", "scx_loader.service"], capture_output=True)
    return "kernel-default"


def _configure_scheduler(candidates: list[str]) -> str:
    if not Path("/sys/kernel/sched_ext").is_dir() or not shutil.which("scx_loader"):
        return _disable_scheduler()
    selected = next((name for name in candidates if shutil.which(name)), "")
    if not selected:
        return _disable_scheduler()
    _atomic_write(SCX_CONFIG_PATH, f"SCX_SCHEDULER={selected}\n")
    run_optional(["systemctl", "enable", "scx_loader.service"], capture_output=True)
    run_optional(["systemctl", "restart", "scx_loader.service"], capture_output=True)
    return selected


def _configure_nvidia() -> str:
    if not _command_ok(["rpm", "-q", "akmod-nvidia"]):
        raise RuntimeError("NVIDIA GPU matched, but akmod-nvidia is missing from the image")
    kernel_result = run_text(["uname", "-r"])
    kernel = kernel_result.stdout.strip() if kernel_result else ""
    if not _command_ok(["modinfo", "nvidia"]):
        if not kernel:
            raise RuntimeError("unable to determine running kernel for NVIDIA module build")
        result = run_optional(["akmods", "--force", "--kernels", kernel])
        if result is None or result.returncode != 0:
            raise RuntimeError(f"NVIDIA module build failed for {kernel}")
    kernel_args = (
        "rd.driver.blacklist=nouveau,nova_core "
        "modprobe.blacklist=nouveau,nova_core nvidia-drm.modeset=1"
    )
    run_optional(["grubby", "--update-kernel=ALL", f"--args={kernel_args}"], capture_output=True)
    for unit in ("nvidia-suspend.service", "nvidia-resume.service", "nvidia-hibernate.service"):
        run_optional(["systemctl", "enable", unit], capture_output=True)
    return "proprietary-ready"


def _clear_nvidia_policy() -> str:
    kernel_args = (
        "rd.driver.blacklist=nouveau,nova_core "
        "modprobe.blacklist=nouveau,nova_core nvidia-drm.modeset=1"
    )
    run_optional(["grubby", "--update-kernel=ALL", f"--remove-args={kernel_args}"], capture_output=True)
    for unit in ("nvidia-suspend.service", "nvidia-resume.service", "nvidia-hibernate.service"):
        run_optional(["systemctl", "disable", unit], capture_output=True)
    return "not-required"


def read_applied_state(path: Path = DEFAULT_STATE_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def apply_system(
    *,
    policy_path: Path = DEFAULT_POLICY_PATH,
    state_path: Path = DEFAULT_STATE_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
    force: bool = False,
) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise PermissionError("hardware policy application must run as root")
    evaluation = evaluate_system(policy_path)
    kernel_result = run_text(["uname", "-r"])
    kernel = kernel_result.stdout.strip() if kernel_result else "unknown"
    image_reference, image_digest = booted_image_identity()
    identity = {
        "policy_digest": evaluation.policy_digest,
        "inventory_digest": evaluation.inventory.digest(),
        "kernel": kernel,
        "image_reference": image_reference,
        "image_digest": image_digest,
    }
    previous = read_applied_state(state_path)
    expected_modprobe = render_modprobe_config(evaluation)
    if _should_skip_apply(previous, identity, expected_modprobe, force):
        _write_state_report(report_path, evaluation, previous)
        return previous

    _atomic_write(MANAGED_MODPROBE_PATH, expected_modprobe)
    policy = _profile_policy(evaluation)
    state: dict[str, Any] = {
        "schema_version": 1,
        "status": "applying",
        **identity,
        "policy_revision": evaluation.policy_revision,
        "profiles": [profile["id"] for profile in evaluation.profiles],
        "quirks": [quirk["id"] for quirk in evaluation.quirks],
        "capabilities": list(evaluation.capabilities),
        "recommended_variant": evaluation.recommended_variant,
        "warnings": list(evaluation.warnings),
    }
    try:
        state.update(_apply_policy_config(policy))
        state["status"] = "applied"
        state["error"] = ""
    except RuntimeError as exc:
        state["status"] = "failed"
        state["error"] = str(exc)
        _atomic_write(state_path, json.dumps(state, indent=2, sort_keys=True) + "\n")
        _write_state_report(report_path, evaluation, state)
        raise
    _atomic_write(state_path, json.dumps(state, indent=2, sort_keys=True) + "\n")
    _write_state_report(report_path, evaluation, state)
    return state


def support_matrix(policy: dict[str, Any]) -> str:
    lines = [
        "# Hardware Support Matrix",
        "",
        "> Generated from `build_files/config/hardware-profiles.toml`; do not edit manually.",
        "",
        "## Image variants",
        "",
        "| Variant | Status | Intended hardware | Qualification |",
        "|---|---|---|---|",
    ]
    for variant in policy.get("variants", []):
        lines.append(
            f"| `{variant['id']}` | {variant['status']} | {variant['description']} | {variant['qualification']} |"
        )
    lines += [
        "",
        "## Device profiles",
        "",
        "| Profile | Tier | Recommended variant | Capabilities |",
        "|---|---|---|---|",
    ]
    for profile in sorted(policy.get("profiles", []), key=lambda item: (-int(item.get("priority", 0)), item["id"])):
        capabilities = ", ".join(f"`{item}`" for item in profile.get("capabilities", [])) or "—"
        lines.append(
            f"| `{profile['id']}` | {profile['tier']} | `{profile['image_variant']}` | {capabilities} |"
        )
    lines += [
        "",
        "## Managed quirks",
        "",
        "| Quirk | Review by | Reason | Provenance |",
        "|---|---|---|---|",
    ]
    for quirk in sorted(policy.get("quirks", []), key=lambda item: item["id"]):
        lines.append(
            f"| `{quirk['id']}` | {quirk['expires_on']} | {quirk['reason']} | {quirk['provenance']} |"
        )
    return "\n".join(lines) + "\n"


def _status_payload(policy_path: Path, state_path: Path) -> dict[str, Any]:
    evaluation = evaluate_system(policy_path)
    return {"evaluation": evaluation.as_dict(), "applied": read_applied_state(state_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate and apply KythOS hardware policy")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inventory")
    subparsers.add_parser("evaluate")
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--force", action="store_true")
    subparsers.add_parser("status")
    matrix_parser = subparsers.add_parser("matrix")
    matrix_parser.add_argument("--output", type=Path)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--fail-expired", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.command == "inventory":
            print(json.dumps(asdict(collect_inventory()), indent=2, sort_keys=True))
        elif args.command == "evaluate":
            print(json.dumps(evaluate_system(args.policy).as_dict(), indent=2, sort_keys=True))
        elif args.command == "apply":
            state = apply_system(policy_path=args.policy, state_path=args.state, force=args.force)
            print(json.dumps(state, indent=2, sort_keys=True))
        elif args.command == "status":
            print(json.dumps(_status_payload(args.policy, args.state), indent=2, sort_keys=True))
        elif args.command == "matrix":
            policy, _ = load_policy(args.policy)
            rendered = support_matrix(policy)
            if args.output:
                _atomic_write(args.output, rendered)
            else:
                print(rendered, end="")
        elif args.command == "validate":
            policy, digest = load_policy(args.policy)
            expired = [
                quirk["id"] for quirk in policy.get("quirks", [])
                if date.fromisoformat(str(quirk["expires_on"])) < date.today()
            ]
            print(f"hardware policy {policy['policy_revision']} ({digest[:12]}): valid")
            if expired:
                print(f"expired quirks: {', '.join(expired)}", file=sys.stderr)
                return 1 if args.fail_expired else 0
    except (OSError, PermissionError, PolicyError, RuntimeError, tomllib.TOMLDecodeError) as exc:
        print(f"kyth-hardware-policy: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
