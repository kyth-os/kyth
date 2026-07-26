"""Guest-side state machine and shared policy for KythOS VM acceptance."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from kyth_shared.commands import run, run_text

FW_CFG_ROOT = Path("/sys/firmware/qemu_fw_cfg/by_name/opt/com.kyth")
ENABLE_FILE = FW_CFG_ROOT / "acceptance/raw"
UPDATE_FILE = FW_CFG_ROOT / "update-ref/raw"
STATE_DIR = Path("/var/lib/kyth/vm-acceptance")
STATE_FILE = STATE_DIR / "state"
SERIAL_DEVICE = Path("/dev/ttyS0")
LOG_FILE = Path("/var/log/kyth-vm-acceptance.log")
TARGET_BY_ID = Path("/dev/disk/by-id/virtio-KYTH_ACCEPT")
UPDATE_REF_PATTERN = re.compile(r"^[A-Za-z0-9._/@:+-]+$")


def _read_fw_cfg(path: Path) -> str:
    try:
        return path.read_bytes().replace(b"\0", b"").decode().strip()
    except OSError:
        return ""


def enabled() -> bool:
    return _read_fw_cfg(ENABLE_FILE) == "1"


def read_update_ref() -> str:
    return _read_fw_cfg(UPDATE_FILE)


def valid_update_ref(value: str) -> bool:
    return not value or UPDATE_REF_PATTERN.fullmatch(value) is not None


def emit(phase: str, detail: str = "") -> None:
    line = f"KYTH_ACCEPTANCE:{phase}:{detail.replace(chr(10), ' ')}"
    print(line, flush=True)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
    except OSError:
        pass
    try:
        SERIAL_DEVICE.write_text(line + "\n", encoding="utf-8")
    except OSError:
        pass


def power(action: str) -> None:
    run(["systemctl", action, "--no-block"])


def fail(message: str) -> None:
    emit("FAILED", message)
    power("poweroff")
    raise SystemExit(1)


def wait_for_desktop(mode: str, *, attempts: int = 90, delay: float = 2) -> bool:
    for _ in range(attempts):
        command = (
            ["pgrep", "-x", "plasmashell"]
            if mode == "live"
            else ["systemctl", "is-active", "--quiet", "display-manager.service"]
        )
        result = run_text(command, timeout=5)
        if result is not None and result.returncode == 0:
            return True
        time.sleep(delay)
    return False


def booted_digest() -> str:
    result = run_text(["bootc", "status", "--format", "json"], timeout=30)
    if result is None or result.returncode:
        return ""
    try:
        booted = json.loads(result.stdout).get("status", {}).get("booted", {})
        image = booted.get("image", {})
        return image.get("imageDigest") or image.get("image", {}).get("imageDigest") or ""
    except (AttributeError, json.JSONDecodeError):
        return ""


def deployment_count() -> int:
    result = run_text(["ostree", "admin", "status", "--json"], timeout=30)
    if result is None or result.returncode:
        return 0
    try:
        data = json.loads(result.stdout)
        deployments = data.get("deployments", data if isinstance(data, list) else [])
        return len(deployments)
    except (AttributeError, json.JSONDecodeError, TypeError):
        return 0


def run_smoke_check(phase: str) -> None:
    try:
        with LOG_FILE.open("a", encoding="utf-8") as log:
            result = run(
                ["/usr/bin/kyth-smoke-check", "--verbose"],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
    except OSError:
        fail(f"{phase} smoke check could not run")
    try:
        SERIAL_DEVICE.write_bytes(LOG_FILE.read_bytes())
    except OSError:
        pass
    if result.returncode >= 2:
        fail(f"{phase} smoke check reported failed invariants (exit {result.returncode})")
    emit(f"{phase}_SMOKE_OK", f"warnings-allowed={result.returncode}")


def _installer_target_ref() -> str:
    default = "ghcr.io/mrtrick37/kyth:testing"
    env_file = Path("/etc/kyth-installer.env")
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("KYTH_TARGET_IMAGE="):
                return line.partition("=")[2].strip().strip("'\"") or default
    except OSError:
        pass
    return default


def install_from_live_iso() -> None:
    if not wait_for_desktop("live"):
        fail("live Plasma desktop did not become ready")
    emit("LIVE_READY", "plasmashell-active")
    run_smoke_check("LIVE")
    for _ in range(60):
        if TARGET_BY_ID.is_block_device():
            break
        time.sleep(1)
    try:
        target = TARGET_BY_ID.resolve(strict=True)
    except OSError:
        fail("dedicated acceptance disk not found")
    if not target.is_block_device():
        fail("acceptance disk symlink did not resolve to a block device")
    source_ref = "oci:/usr/share/kyth/image:latest"
    target_ref = _installer_target_ref()
    if not Path("/usr/share/kyth/image").is_dir():
        fail("bundled OCI image is missing from live media")
    emit("INSTALL_STARTED", str(target))
    try:
        with LOG_FILE.open("a", encoding="utf-8") as log:
            result = run(
                [
                    "bootc", "install", "to-disk", "--source-imgref", source_ref,
                    "--target-imgref", target_ref, "--filesystem", "btrfs",
                    "--wipe", "--skip-fetch-check", str(target),
                ],
                stdout=log, stderr=subprocess.STDOUT,
            )
    except OSError:
        fail("bootc install to-disk failed")
    if result.returncode:
        fail("bootc install to-disk failed")
    update_ref = read_update_ref()
    if not valid_update_ref(update_ref):
        fail("update image reference contains unsupported characters")
    emit("INSTALL_COMPLETE", target_ref)
    power("reboot")


def _state_value() -> str:
    try:
        return STATE_FILE.read_text(encoding="utf-8").strip() or "fresh"
    except OSError:
        return "fresh"


def _initial_digest() -> str:
    try:
        return (STATE_DIR / "initial-digest").read_text(encoding="utf-8").strip()
    except OSError:
        fail("initial deployment digest is missing")
    return ""


def _logged(command: list[str], error: str) -> None:
    with LOG_FILE.open("a", encoding="utf-8") as log:
        result = run(command, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        fail(error)


def run_installed_lifecycle() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = _state_value()
    update_ref = read_update_ref()
    if not valid_update_ref(update_ref):
        fail("update image reference contains unsupported characters")
    if not wait_for_desktop("installed"):
        fail("installed display manager did not become ready")
    if state == "fresh":
        emit("INSTALLED_READY", "display-manager-active")
        run_smoke_check("INSTALLED")
        initial = booted_digest()
        if not initial:
            fail("could not read initial booted digest")
        (STATE_DIR / "initial-digest").write_text(initial + "\n", encoding="utf-8")
        if not update_ref:
            emit("COMPLETE", "install-only")
            power("poweroff")
            return
        STATE_FILE.write_text("update-staged\n", encoding="utf-8")
        emit("UPDATE_STARTED", update_ref)
        _logged(["bootc", "switch", update_ref], "bootc switch failed")
        emit("UPDATE_STAGED", update_ref)
        power("reboot")
    elif state == "update-staged":
        initial, current = _initial_digest(), booted_digest()
        if not current or current == initial:
            fail("updated deployment did not boot a different digest")
        if deployment_count() < 2:
            fail("updated system does not expose a rollback deployment")
        emit("UPDATE_BOOTED", current)
        run_smoke_check("UPDATE")
        STATE_FILE.write_text("rollback-staged\n", encoding="utf-8")
        _logged(["bootc", "rollback"], "bootc rollback failed")
        emit("ROLLBACK_STAGED", initial)
        power("reboot")
    elif state == "rollback-staged":
        initial, current = _initial_digest(), booted_digest()
        if not current or current != initial:
            fail("rollback did not restore the initial deployment digest")
        emit("ROLLBACK_BOOTED", current)
        run_smoke_check("ROLLBACK")
        emit("COMPLETE", "update-and-rollback")
        STATE_FILE.unlink(missing_ok=True)
        power("poweroff")
    else:
        fail(f"unknown acceptance state: {state}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("enabled", "run"))
    args = parser.parse_args(argv)
    if args.command == "enabled":
        return 0 if enabled() else 1
    if not enabled():
        return 0
    try:
        if Path("/etc/kyth-installer.env").is_file():
            install_from_live_iso()
        else:
            run_installed_lifecycle()
    except (OSError, RuntimeError, ValueError) as exc:
        fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
