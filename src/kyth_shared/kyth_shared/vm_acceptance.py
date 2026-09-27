"""Guest-side state machine and shared policy for KythOS VM acceptance."""
from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import signal
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

from kyth_shared.commands import run, run_text

FW_CFG_ROOT = Path("/sys/firmware/qemu_fw_cfg/by_name/opt/com.kyth")
ENABLE_FILE = FW_CFG_ROOT / "acceptance/raw"
UPDATE_FILE = FW_CFG_ROOT / "update-ref/raw"
STATE_DIR = Path("/var/lib/kyth/vm-acceptance")
STATE_FILE = STATE_DIR / "state"
SERIAL_DEVICE = Path("/dev/ttyS0")
LOG_FILE = Path("/var/log/kyth-vm-acceptance.log")
TARGET_BY_ID = Path("/dev/disk/by-id/virtio-KYTH_ACCEPT")
INSTALLER_ENV_FILE = Path("/etc/kyth-installer.env")
HUB_BINARY = Path("/usr/bin/kyth-hub-shell")
HUB_ROUTE_MANIFEST = Path("/usr/share/kyth/hubRoutes.json")
HUB_ACCEPTANCE_TIMEOUT = 45
UPDATE_REF_PATTERN = re.compile(r"^[A-Za-z0-9._/@:+-]+$")


from .atomic_io import atomic_write_text as _atomic_write


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
        # A bare top-level list is handled before calling .get(): list has no
        # .get, so checking isinstance() only inside the default-value
        # argument would never run — .get itself raises AttributeError first.
        deployments = data if isinstance(data, list) else data.get("deployments", [])
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
    default = "ghcr.io/kyth-os/kyth:testing"
    try:
        for line in INSTALLER_ENV_FILE.read_text(encoding="utf-8").splitlines():
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
                stdout=log, stderr=subprocess.STDOUT, timeout=1800,
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


def _active_graphical_session() -> tuple[str, dict[str, str]] | None:
    """Return the active desktop user and the minimal environment it needs."""
    active = run_text(["loginctl", "show-seat", "seat0", "-p", "ActiveSession", "--value"], timeout=5)
    session = active.stdout.strip() if active and active.returncode == 0 else ""
    if not session:
        return None
    owner = run_text(["loginctl", "show-session", session, "-p", "Name", "--value"], timeout=5)
    username = owner.stdout.strip() if owner and owner.returncode == 0 else ""
    if not username:
        return None
    try:
        account = pwd.getpwnam(username)
    except KeyError:
        return None
    runtime = Path(f"/run/user/{account.pw_uid}")
    wayland = next(iter(sorted(runtime.glob("wayland-*"))), None)
    x11 = next(iter(sorted(Path("/tmp/.X11-unix").glob("X*"))), None)
    environment = {
        "HOME": account.pw_dir,
        "LOGNAME": username,
        "USER": username,
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "XDG_RUNTIME_DIR": str(runtime),
        "XDG_CURRENT_DESKTOP": "KDE",
        "XDG_SESSION_TYPE": "wayland" if wayland else "x11" if x11 else "",
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime}/bus",
    }
    if wayland:
        environment["WAYLAND_DISPLAY"] = wayland.name
    if x11:
        environment["DISPLAY"] = f":{x11.name.removeprefix('X')}"
    xauthority = Path(account.pw_dir) / ".Xauthority"
    if xauthority.is_file():
        environment["XAUTHORITY"] = str(xauthority)
    return username, environment


def _hub_pages() -> tuple[tuple[str, str], ...]:
    try:
        manifest = json.loads(HUB_ROUTE_MANIFEST.read_text(encoding="utf-8"))
        pages: list[tuple[str, str]] = [("Welcome", "/")]
        for destination in manifest["destinations"]:
            route = str(destination["route"])
            key = str(destination["key"])
            pages.append((key, route))
            pages.extend(
                (str(section["key"]), f"{route}?section={quote(str(section['key']), safe='')}" )
                for section in destination["sections"]
            )
        if len({key for key, _ in pages}) != len(pages):
            raise ValueError("Hub route manifest contains duplicate page keys")
        return tuple(pages)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        fail(f"Hub route manifest could not be read: {exc}")
    return ()


def _hub_start(username: str, environment: dict[str, str], page: str, evidence: Path, *, degraded: bool = False) -> subprocess.Popen[bytes]:
    values = dict(environment)
    values["KYTH_HUB_ACCEPTANCE_FILE"] = str(evidence)
    if degraded:
        values["KYTH_HUB_ACCEPTANCE_DEGRADED"] = "1"
    command = [
        "runuser", "-u", username, "--", "env",
        *(f"{key}={value}" for key, value in values.items() if value),
        str(HUB_BINARY), "--page", page,
    ]
    stream = evidence.with_suffix(".process.log").open("ab")
    try:
        return subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    finally:
        stream.close()


def _hub_stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=8)


def _hub_event(evidence: Path, event: str) -> dict[str, object] | None:
    prefix = f"KYTH_HUB_ACCEPTANCE:{event}:"
    try:
        lines = evidence.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if line.startswith(prefix):
            try:
                value = json.loads(line.removeprefix(prefix))
            except json.JSONDecodeError:
                return None
            return value if isinstance(value, dict) else None
    return None


def _wait_hub_event(evidence: Path, event: str, *, timeout: int = HUB_ACCEPTANCE_TIMEOUT) -> dict[str, object] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = _hub_event(evidence, event)
        if value is not None:
            return value
        time.sleep(0.5)
    return None


def _hub_launch_check(username: str, environment: dict[str, str], page: str, expected_route: str, evidence: Path) -> bool:
    evidence.unlink(missing_ok=True)
    try:
        process = _hub_start(username, environment, page, evidence)
    except OSError:
        return False
    try:
        event = _wait_hub_event(evidence, "deep-link")
        return bool(
            event
            and event.get("page") == page
            and event.get("route") == expected_route
            and event.get("source") == "initial"
        )
    finally:
        _hub_stop(process)


def _ensure_acceptance_graphical_session() -> tuple[str, dict[str, str]] | None:
    """Create a disposable desktop account when the installed image has none.

    The live image's ``liveuser`` is created by livesys at runtime and is not
    part of the installed bootc image. The normal installed system therefore
    correctly stops at the login manager until a user is created, but that
    leaves the firmware-gated VM acceptance service without a graphical
    session in which to exercise the installed Hub. Create an acceptance-only
    account and restart the login manager; this path is reachable only when
    QEMU exposes the acceptance fw_cfg flag.
    """
    session = _active_graphical_session()
    if session and (session[1].get("WAYLAND_DISPLAY") or session[1].get("DISPLAY")):
        return session

    username = "kyth-acceptance"
    account = run_text(["id", "-u", username], timeout=5)
    if account is None or account.returncode:
        created = run(["useradd", "--create-home", "--shell", "/bin/bash", username], timeout=30)
        if created.returncode:
            return None
    try:
        config = Path("/etc/plasmalogin.conf.d/90-kyth-vm-acceptance.conf")
        config.write_text(
            "[Autologin]\nUser=kyth-acceptance\nSession=plasma.desktop\nRelogin=true\n",
            encoding="utf-8",
        )
    except OSError:
        return None
    restarted = run(["systemctl", "restart", "display-manager.service", "--no-block"], timeout=30)
    if restarted.returncode:
        return None
    for _ in range(60):
        session = _active_graphical_session()
        if session and (session[1].get("WAYLAND_DISPLAY") or session[1].get("DISPLAY")):
            return session
        time.sleep(1)
    return None


def run_hub_acceptance() -> None:
    """Exercise the installed Rust/Tauri shell from the installed desktop."""
    if not HUB_BINARY.is_file() or not os.access(HUB_BINARY, os.X_OK):
        fail(f"installed Rust/Tauri Hub binary is missing or not executable: {HUB_BINARY}")
    session = _ensure_acceptance_graphical_session()
    if session is None:
        fail("active graphical session for installed Hub acceptance was not found")
    username, environment = session
    evidence = Path(f"/tmp/kyth-hub-acceptance-{os.getuid()}.log")
    emit("HUB_BINARY_OK", str(HUB_BINARY))

    pages = _hub_pages()
    for page, route in pages:
        if not _hub_launch_check(username, environment, page, route, evidence):
            fail(f"Hub --page deep link failed for {page!r}")
    emit(
        "HUB_DEEP_LINKS_OK",
        "; ".join(f"{page}={route}" for page, route in pages),
    )

    evidence.unlink(missing_ok=True)
    first = _hub_start(username, environment, "Welcome", evidence)
    try:
        if _wait_hub_event(evidence, "deep-link") is None:
            fail("Hub first launch did not resolve Welcome")
        evidence.unlink(missing_ok=True)
        second = _hub_start(username, environment, "Updates", evidence)
        try:
            forwarded = _wait_hub_event(evidence, "deep-link")
            if not forwarded or forwarded.get("page") != "Updates" or forwarded.get("source") != "single-instance":
                fail("Hub second launch did not forward the Updates page")
        finally:
            _hub_stop(second)
    finally:
        _hub_stop(first)
    emit("HUB_SECOND_LAUNCH_OK", "Updates forwarded to the existing Hub process")

    evidence.unlink(missing_ok=True)
    degraded = _hub_start(username, environment, "Welcome", evidence, degraded=True)
    try:
        dashboard = _wait_hub_event(evidence, "dashboard")
        if not dashboard or dashboard.get("state") != "degraded" or dashboard.get("label") != "Status unavailable":
            fail("Hub dashboard did not report its unavailable-data state honestly")
    finally:
        _hub_stop(degraded)
    emit("HUB_DASHBOARD_DEGRADED_OK", "Status unavailable")

    evidence.unlink(missing_ok=True)
    updates = _hub_start(username, environment, "Updates", evidence)
    try:
        update_probe = _wait_hub_event(evidence, "updates-probe")
        privilege_probe = _wait_hub_event(evidence, "privileged-failure")
        if not update_probe or update_probe.get("state") not in {"ok", "degraded"}:
            fail("Hub Updates page did not report a usable or degraded probe result")
        if not privilege_probe or privilege_probe.get("state") != "expected":
            fail("Hub privileged-action failure was not surfaced as an expected failure")
    finally:
        _hub_stop(updates)
    emit("HUB_UPDATES_OK", str(update_probe.get("state", "unknown")))
    emit("HUB_PRIVILEGED_FAILURE_OK", "allowlist rejection surfaced")


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
        run_hub_acceptance()
        initial = booted_digest()
        if not initial:
            fail("could not read initial booted digest")
        _atomic_write(STATE_DIR / "initial-digest", initial + "\n")
        if not update_ref:
            emit("COMPLETE", "install-only")
            power("poweroff")
            return
        _atomic_write(STATE_FILE, "update-staged\n")
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
        _atomic_write(STATE_FILE, "rollback-staged\n")
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
        if INSTALLER_ENV_FILE.is_file():
            install_from_live_iso()
        else:
            run_installed_lifecycle()
    except (OSError, RuntimeError, ValueError) as exc:
        fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
