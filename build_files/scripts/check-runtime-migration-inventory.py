#!/usr/bin/env python3
"""Generate and validate Kyth's runtime migration inventory.

The inventory is intentionally source-derived.  It records aliases and nested
unit files separately because the installed executable is not always the
source file that appears in build_files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "build_files/config/runtime-migration-inventory.json"
SCHEMA_VERSION = 1
STATUSES = {"done-native", "queued", "explicitly-not-ported"}
RISK = {"read-only", "user-session-writer", "privileged-writer", "daemon", "destructive", "build-time"}
UNIT_SUFFIXES = {".service", ".timer", ".path"}

NATIVE_BINARIES = {
    "kyth-probe", "kyth-guardian", "kyth-update-watcher", "kyth-network-share",
    "kyth-telem", "kyth-privileged", "kyth-post-update-check",
    "kyth-firstboot-app-status", "kyth-steam-game-export", "kyth-hub-desktop-entries",
    "kyth-safe-upgrade", "kyth-bootc-guard", "kyth-finalize-staged", "kyth-btrfs-maint",
    "kyth-ai-perfd", "kyth-perf-gate-rs",
}
NATIVE_BINARIES = NATIVE_BINARIES | {"kyth-doctor", "kyth-health-check", "kyth-smoke-check", "kyth-resume-check", "kyth-nvidia-status", "kyth-controller-check", "kyth-creator-check", "kyth-exe-compat", "kyth-snapshot-timeline", "kyth-print-check"}
PACKAGED_NATIVE_LAUNCHERS = NATIVE_BINARIES
NOT_PORTED = {"kyth-default-flatpaks", "kyth-flathub-setup", "kyth-local-bin-migrate", "rclone@", "scx_loader"}
READ_ONLY_NAMES = {
    "kyth-doctor", "kyth-health-check", "kyth-smoke-check", "kyth-resume-check",
    "kyth-nvidia-status", "kyth-controller-check", "kyth-creator-check",
    "kyth-exe-compat", "kyth-snapshot-timeline", "kyth-print-check",
    "kyth-windows-verify", "kyth-vm-acceptance-guest",
}
WRITER_NAMES = {
    "kyth-apply-desktop-layout", "kyth-apply-role-preset", "kyth-configure-session",
    "kyth-greeter-compositor", "kyth-performance-mode", "kyth-set-kickoff-icon",
    "kyth-set-resolution", "kyth-config-apply", "kyth-exe-handler", "kyth-report-issue",
    "kyth-session-snapshot", "kyth-setup-transfer", "kyth-setup-devcontainer",
    "kyth-ntfs-repair", "kyth-kali-desktop-fixup", "kyth-refresh-boot-splash-initramfs",
    "kyth-refresh-taskbar-pins", "kyth-vscode-wallet", "kyth-web-app-categorize",
}
DAEMON_NAMES = {
    "kyth-batteryd", "kyth-backup", "kyth-save-sync", "kyth-cloud-mount", "kyth-duperemove",
    "kyth-storage-sense", "kyth-dynamic-lock", "kyth-game-boost", "kyth-game-launch",
    "kyth-sched", "kyth-sched-arbiter", "kyth-proton-cachyos-update", "kyth-rclone-update",
    "kyth-user-polish", "kyth-installerd",
}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def launcher_kind(path: Path) -> str:
    if path.is_symlink():
        return "alias"
    try:
        first = path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except (OSError, IndexError):
        return "data"
    if "python" in first:
        return "python"
    if "bash" in first or "/bin/sh" in first:
        return "shell"
    return "data"


def name_for(path: Path) -> str:
    return path.name.removesuffix(".service").removesuffix(".timer").removesuffix(".path")


def risk_for(name: str, kind: str, path: Path) -> str:
    if "/scripts/" in f"/{rel(path)}" or path.parts[:2] == ("build_files", "scripts"):
        return "build-time"
    if name in READ_ONLY_NAMES or name in NATIVE_BINARIES and name not in {"kyth-network-share"}:
        return "read-only"
    if name in WRITER_NAMES:
        return "user-session-writer"
    if name in DAEMON_NAMES:
        return "destructive" if name in {"kyth-installerd"} else "daemon"
    if "privileged" in name or name in {"kyth-ntfs-repair", "kyth-refresh-boot-splash-initramfs"}:
        return "privileged-writer"
    if kind in {"python", "shell", "alias"}:
        return "user-session-writer"
    return "build-time"


def entry(path: Path, *, surface: str, implementation: str | None = None, name: str | None = None) -> dict:
    item_name = name or name_for(path)
    kind = implementation or launcher_kind(path)
    if item_name in NOT_PORTED:
        status = "explicitly-not-ported"
        reason = "documented third-party or declarative build/runtime exception"
    elif (
        implementation == "rust"
        or (surface == "systemd-unit" and item_name in NATIVE_BINARIES)
        or (surface == "launcher" and item_name in PACKAGED_NATIVE_LAUNCHERS)
    ):
        status = "done-native"
        reason = "native Rust crate or installed unit is already declared/packaged"
    else:
        status = "queued"
        reason = None
    owner = f"fixture::{rel(path)}" if status == "queued" else f"native::{item_name}"
    return {
        "path": rel(path),
        "surface": surface,
        "name": item_name,
        "resolved_target": rel(path.resolve()) if path.exists() else None,
        "current_implementation": kind,
        "installed_implementation": "rust" if status == "done-native" else kind,
        "status": status,
        "risk_tier": risk_for(item_name, kind, path),
        "priority": 0 if status != "queued" else 1,
        "owner": owner,
        "parity_tests": ["tests/"],
        "cutover": f"replace installed {item_name} entry point after parity gates",
        "rollback": f"restore previous installed {item_name} entry point",
        "retirement": "retain source fixture until exact-image acceptance and rollback qualification",
        **({"reason": reason} if reason else {}),
    }


def discover() -> list[dict]:
    items: list[dict] = []
    for path in sorted(ROOT.glob("build_files/kyth-*")):
        if path.suffix not in UNIT_SUFFIXES:
            items.append(entry(path, surface="launcher"))
    for path in sorted((ROOT / "build_files").rglob("*")):
        if path.is_file() and path.suffix in UNIT_SUFFIXES:
            unit = entry(path, surface="systemd-unit")
            text = path.read_text(encoding="utf-8", errors="replace")
            execs = re.findall(r"^Exec(?:Start|Condition|Stop)=([^\n]+)", text, re.MULTILINE)
            unit["exec_start"] = execs
            if any("kyth-privileged" in command or "kyth-installerd" in command for command in execs):
                unit["risk_tier"] = "privileged-writer" if "installerd" not in path.name else "destructive"
            items.append(unit)
    for root, surface in ((ROOT / "src/kyth_shared", "python-runtime"), (ROOT / "src/kyth-welcome", "python-runtime"), (ROOT / "src/kyth-installer", "installer-runtime")):
        for path in sorted(root.rglob("*.py")):
            items.append(entry(path, surface=surface, implementation="python", name=path.stem))
    for path in sorted((ROOT / "build_files/just/kyth").glob("*.just")):
        items.append(entry(path, surface="ujust-recipe", implementation="recipe", name=path.stem))
    for manifest in (ROOT / "src/kyth-shared-rs/Cargo.toml", ROOT / "src/kyth-hub-web/src-tauri/Cargo.toml", ROOT / "src/kyth-installer-web/src-tauri/Cargo.toml"):
        if manifest.exists():
            items.append(entry(manifest, surface="rust-crate", implementation="rust", name=manifest.parent.name))
    return sorted(items, key=lambda item: item["path"])


def validate(document: dict, *, expected_paths: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported schema_version")
    entries = document.get("entries")
    if not isinstance(entries, list) or not entries:
        return ["entries must be a non-empty list"]
    seen: set[str] = set()
    required = {"path", "surface", "resolved_target", "current_implementation", "installed_implementation", "status", "risk_tier", "priority", "owner", "parity_tests", "cutover", "rollback", "retirement"}
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            errors.append(f"entry {index} is not an object")
            continue
        missing = required - item.keys()
        if missing:
            errors.append(f"entry {index} missing {', '.join(sorted(missing))}")
        path = item.get("path")
        if not isinstance(path, str) or not path or path in seen:
            errors.append(f"entry {index} has missing or duplicate path: {path!r}")
        else:
            seen.add(path)
            source = ROOT / path
            if not source.exists() and not source.is_symlink():
                errors.append(f"entry {path} does not exist")
            if source.is_symlink() and not source.exists():
                errors.append(f"entry {path} is a broken symlink")
        if item.get("status") not in STATUSES:
            errors.append(f"entry {path} has invalid status")
        if item.get("risk_tier") not in RISK:
            errors.append(f"entry {path} has invalid risk_tier")
        if not isinstance(item.get("priority"), int) or item["priority"] < 0:
            errors.append(f"entry {path} has invalid priority")
        for field in ("owner", "cutover", "rollback", "retirement"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"entry {path} has empty {field}")
        if not isinstance(item.get("parity_tests"), list) or not item["parity_tests"]:
            errors.append(f"entry {path} has no parity_tests")
        if item.get("status") == "explicitly-not-ported" and not item.get("reason"):
            errors.append(f"entry {path} needs a reason")
    if expected_paths is not None:
        missing = expected_paths - seen
        extra = seen - expected_paths
        errors.extend(f"missing discovered path {path}" for path in sorted(missing))
        errors.extend(f"stale inventory path {path}" for path in sorted(extra))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true", help="regenerate the inventory from the checkout")
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    args = parser.parse_args(argv)
    path = args.inventory if args.inventory.is_absolute() else ROOT / args.inventory
    if args.generate:
        document = {"schema_version": SCHEMA_VERSION, "generated_from": "checkout discovery", "entries": discover()}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"runtime inventory: cannot read {path}: {exc}", file=sys.stderr)
        return 1
    errors = validate(document, expected_paths={item["path"] for item in discover()})
    if errors:
        for error in errors:
            print(f"runtime inventory: {error}", file=sys.stderr)
        return 1
    print(f"runtime inventory: valid ({len(document['entries'])} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
