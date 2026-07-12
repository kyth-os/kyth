"""System-mutation helpers for kyth-installer: privilege escalation, account
database repair, MOK/Secure Boot enrollment, timezone listing, and unmounting
a target disk before a wipe install.
"""

import glob
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def _as_root(cmd: list[str]) -> list[str]:
    return cmd if os.geteuid() == 0 else ["sudo", "-n", *cmd]


def list_timezones() -> list[str]:
    try:
        out = subprocess.check_output(
            ["timedatectl", "list-timezones"], text=True, timeout=5
        )
        zones = [l.strip() for l in out.splitlines() if l.strip()]
        if zones:
            return zones
    except Exception:
        pass
    # timedatectl unavailable or returned nothing — read zone.tab directly.
    for tab in ("/usr/share/zoneinfo/zone1970.tab", "/usr/share/zoneinfo/zone.tab"):
        try:
            zones = ["UTC"]
            with open(tab) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split()
                        if len(parts) >= 3:
                            zones.append(parts[2])
            if zones:
                return sorted(set(zones))
        except Exception:
            pass
    return ["UTC"]


def find_deploy_etc(root_mount: str) -> Optional[str]:
    candidates = glob.glob(f"{root_mount}/ostree/deploy/default/deploy/*/etc")
    if not candidates:
        return None
    return sorted(candidates)[-1]


SYSTEM_GROUP_FALLBACKS = {
    "sddm": "sddm:x:959:",
}

SYSTEM_PASSWD_FALLBACKS = {
    "sddm": "sddm:x:959:959:SDDM Greeter Account:/var/lib/sddm:/usr/sbin/nologin",
}


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(errors="ignore").splitlines()
    except FileNotFoundError:
        return []


def _write_lines(path: Path, lines: list[str], mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # passwd uses the literal "x" placeholder; shadow records contain hashes.
    # Open the file with restrictive permissions at creation time to prevent
    # race conditions and avoid creating world/group-readable files.
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, mode & 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write("\n".join(lines) + "\n")


def _append_missing_records(dest: Path, sources: list[Path], fallbacks: dict[str, str]) -> bool:
    lines = _read_lines(dest)
    names = {line.split(":", 1)[0] for line in lines if line and ":" in line}
    changed = False

    for source in sources:
        for line in _read_lines(source):
            if not line or ":" not in line:
                continue
            name = line.split(":", 1)[0]
            if name and name not in names:
                lines.append(line)
                names.add(name)
                changed = True

    for name, line in fallbacks.items():
        if name not in names:
            lines.append(line)
            names.add(name)
            changed = True

    if changed:
        _write_lines(dest, lines, 0o644)
    return changed


def ensure_system_accounts(deploy_root: str, log) -> None:
    root = Path(deploy_root)
    etc = root / "etc"

    group_changed = _append_missing_records(
        etc / "group",
        [root / "usr/lib/group"],
        SYSTEM_GROUP_FALLBACKS,
    )
    passwd_changed = _append_missing_records(
        etc / "passwd",
        [root / "usr/lib/passwd"],
        SYSTEM_PASSWD_FALLBACKS,
    )

    passwd_names = {
        line.split(":", 1)[0]
        for line in _read_lines(etc / "passwd")
        if line and ":" in line
    }
    shadow = etc / "shadow"
    shadow_lines = _read_lines(shadow)
    shadow_names = {
        line.split(":", 1)[0]
        for line in shadow_lines
        if line and ":" in line
    }
    shadow_changed = False
    for name in sorted(passwd_names - shadow_names):
        if name == "root" or not name:
            continue
        shadow_lines.append(f"{name}:!*:19700:0:99999:7:::")
        shadow_changed = True
    if shadow_changed:
        _write_lines(shadow, shadow_lines, 0o000)
    elif shadow.exists():
        os.chmod(shadow, 0o000)

    sddm_home = root / "var/lib/sddm"
    subprocess.run(_as_root(["mkdir", "-p", str(sddm_home)]), check=True)
    
    # Read the actual sddm UID/GID from target's etc/passwd to support dynamic allocation
    # and ensure numeric chown works even if the host environment has no sddm user/group.
    sddm_uid, sddm_gid = "959", "959"
    for line in _read_lines(etc / "passwd"):
        if line.startswith("sddm:"):
            parts = line.split(":")
            if len(parts) >= 4:
                sddm_uid, sddm_gid = parts[2], parts[3]
                break
    subprocess.run(_as_root(["chown", f"{sddm_uid}:{sddm_gid}", str(sddm_home)]), check=False)
    restorecon = shutil.which("restorecon")
    if restorecon:
        subprocess.run(
            _as_root([
                restorecon,
                str(etc / "passwd"),
                str(etc / "group"),
                str(etc / "shadow"),
                str(sddm_home),
            ]),
            check=False,
        )

    if group_changed or passwd_changed or shadow_changed:
        log("Repaired installed system account databases for SDDM/D-Bus")


def _lsblk_target_mounts(disk: str) -> list[tuple[str, str]]:
    """Return (device, mountpoint) pairs for mounted devices under disk."""
    out = subprocess.check_output(
        ["lsblk", "--json", "--paths", "--output", "NAME,TYPE,MOUNTPOINTS", disk],
        text=True, stderr=subprocess.DEVNULL,
    )
    mounts: list[tuple[str, str]] = []

    def walk(dev: dict) -> None:
        name = dev.get("name") or ""
        for mount in dev.get("mountpoints") or []:
            if mount:
                mounts.append((name, mount))
        for child in dev.get("children") or []:
            walk(child)

    for dev in json.loads(out).get("blockdevices", []):
        walk(dev)
    mounts.sort(key=lambda item: item[1].count("/"), reverse=True)
    return mounts


# Mountpoints that must never receive a lazy unmount — they are part of the
# running system and detaching them would destabilize the OS.
_CRITICAL_MOUNTS = frozenset({"/", "/boot", "/boot/efi", "/efi", "/home", "/var"})


def unmount_target_disk(disk: str, log) -> None:
    """Unmount any live-session mounts that would block wiping disk."""
    log(f"Unmounting any existing mounts on {disk} ...")
    for mount in ("/mnt", "/sysroot", "/target"):
        subprocess.run(_as_root(["umount", "-R", mount]), check=False)

    try:
        mounts = _lsblk_target_mounts(disk)
    except Exception as exc:
        log(f"Warning: could not inspect target mounts with lsblk: {exc}")
        mounts = []

    for dev, mount in mounts:
        log(f"Unmounting {dev} from {mount}")
        result = subprocess.run(
            _as_root(["umount", "-R", mount]),
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            log(f"Normal unmount failed for {mount}: {err}")
            if mount in _CRITICAL_MOUNTS:
                log(f"Skipping lazy unmount of running system mount: {mount}")
            else:
                subprocess.run(_as_root(["umount", "-l", mount]), check=False)

    try:
        remaining = _lsblk_target_mounts(disk)
    except Exception:
        remaining = []
    if remaining:
        details = ", ".join(f"{dev} at {mount}" for dev, mount in remaining)
        raise RuntimeError(
            f"Target disk {disk} still has mounted partitions: {details}. "
            "Close any file manager or terminal using those paths and retry."
        )


def _try_stage_mok_enrollment(log, kernel: str = "fedora", mok_password: str = "") -> str:
    """Stage Kyth Secure Boot MOK enrollment via mokutil.

    Returns one of: skipped, enrolled, pending, staged, failed.
    """
    force_stage = os.environ.get("KYTH_STAGE_MOK", "0").lower() in ("1", "true", "yes", "on")
    if kernel != "cachy" and not force_stage:
        log("Secure Boot: standard KythOS kernel selected — custom-kernel MOK enrollment not staged")
        return "skipped"

    cert_der = Path("/usr/share/kyth/secureboot/kyth-secureboot.der")
    if not cert_der.exists():
        log("Secure Boot: cert not found in live image — skipping enrollment staging")
        return "skipped"

    mokutil = shutil.which("mokutil")
    if not mokutil:
        log("Secure Boot: mokutil not found — skipping enrollment staging")
        return "skipped"

    try:
        result = subprocess.run(
            _as_root([mokutil, "--sb-state"]),
            capture_output=True, text=True, timeout=5,
        )
        if "SecureBoot enabled" not in result.stdout:
            log("Secure Boot: not currently enabled — enrollment staging skipped")
            log("Secure Boot: if you enable it later, run 'ujust enroll-secureboot'")
            return "skipped"
    except Exception as exc:
        log(f"Secure Boot: could not check state ({exc}) — skipping enrollment staging")
        return "skipped"

    try:
        enrolled = subprocess.run(
            _as_root([mokutil, "--list-enrolled"]),
            capture_output=True, text=True, timeout=5,
        )
        if "KythOS Secure Boot" in enrolled.stdout:
            log("Secure Boot: KythOS key already enrolled")
            return "enrolled"
    except Exception:
        pass

    try:
        pending = subprocess.run(
            _as_root([mokutil, "--list-new"]),
            capture_output=True, text=True, timeout=5,
        )
        if "KythOS Secure Boot" in pending.stdout:
            log("Secure Boot: enrollment already staged — confirm it on next boot")
            return "pending"
    except Exception:
        pass

    try:
        result = subprocess.run(
            _as_root([mokutil, "--import", str(cert_der), "--stdin-passwd"]),
            input=f"{mok_password}\n", text=True, capture_output=True, timeout=15,
        )
        if result.returncode == 0:
            log("Secure Boot: enrollment staged — confirm it on first boot before the KythOS performance kernel starts")
            return "staged"
        log(f"Secure Boot: mokutil import failed (exit {result.returncode}): {result.stderr.strip()}")
        return "failed"
    except Exception as exc:
        log(f"Secure Boot: enrollment staging failed: {exc}")
        return "failed"


def _hash_password(password: str) -> str:
    # openssl passwd -stdin emits nothing (exit 0) for empty input, which
    # would surface as a confusing "invalid SHA-512 crypt value" error.
    if not password:
        raise RuntimeError("Password cannot be empty. Return to the Configure step and re-enter it.")
    result = subprocess.run(
        ["openssl", "passwd", "-6", "-stdin"],
        input=password,
        text=True,
        capture_output=True,
        check=True,
        timeout=15,
    )
    password_hash = result.stdout.strip()
    if not password_hash.startswith("$6$"):
        raise RuntimeError("Password hashing returned an invalid SHA-512 crypt value")
    return password_hash
