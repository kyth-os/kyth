"""Installer preflight and installed-target assurance checks."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

_logger = logging.getLogger(__name__)

from .context import InstallRequest
from .imagesrc import ImageSource


@dataclass(frozen=True)
class AssuranceCheck:
    name: str
    status: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def _battery_check(power_root: Path = Path("/sys/class/power_supply")) -> AssuranceCheck:
    """Block destructive work when a laptop is critically low and unplugged."""
    if not power_root.is_dir():
        return AssuranceCheck("power", "pass", "No battery power constraint detected")
    batteries = []
    for entry in power_root.iterdir():
        try:
            if (entry / "type").read_text().strip() != "Battery":
                continue
            capacity = int((entry / "capacity").read_text().strip())
            status = (entry / "status").read_text().strip().lower()
            batteries.append((capacity, status))
        except (OSError, ValueError):
            continue
    if not batteries:
        return AssuranceCheck("power", "pass", "No battery power constraint detected")
    capacity, status = min(batteries)
    if capacity < 20 and status in {"discharging", "not charging"}:
        raise RuntimeError(
            f"Battery is at {capacity}% and is not charging. Connect power before installing."
        )
    return AssuranceCheck("power", "pass", f"Battery is {capacity}% ({status})")


def _encryption_check(disk: str | None = None, snapshot=None) -> AssuranceCheck | None:
    """Detect BitLocker/LUKS/LVM on the target that would block install.

    When snapshot is given, scan StorageSnapshot.fstype/parttype/children directly (R-07).
    """
    if snapshot is not None:
        try:
            # Snapshot has partitions as dicts with fstype/parttype
            for name, part in (snapshot.partitions_by_name.items() if hasattr(snapshot, "partitions_by_name") else []):
                fstype = (part.get("fstype") or part.get("FSTYPE") or "").lower()
                if fstype == "crypto_luks":
                    return AssuranceCheck("encryption", "warn", f"Partition {name} is LUKS-encrypted — unlock or disable before installing.")
                # children indicates LVM/LUKS wrapper
                if part.get("children"):
                    for child in part.get("children") or []:
                        ctype = (child.get("fstype") or "").lower()
                        if ctype == "crypto_luks":
                            return AssuranceCheck("encryption", "warn", f"Partition {name} is LUKS-encrypted — unlock or disable before installing.")
            # Also check disks for BitLocker via snapshot's in_use
            for part in snapshot.partitions_by_name.values() if hasattr(snapshot, "partitions_by_name") else []:
                if part.get("in_use") and (part.get("fstype") or "").lower() in ("ntfs", "ntfs3"):
                    return AssuranceCheck("encryption", "warn", f"Partition {part.get('name')} appears BitLocker-locked — suspend BitLocker in Windows before resizing.")
        except (OSError, ValueError, AttributeError, RuntimeError) as exc:
            _logger.debug("encryption snapshot probe failed: %s", exc, exc_info=True)
    if not disk:
        return None
    try:
        from .disk import list_partitions
        for part in list_partitions(disk):
            fstype = (part.get("fstype") or "").lower()
            in_use = bool(part.get("in_use") or part.get("children"))
            # LUKS is fstype crypto_LUKS, LVM is children with type lvm
            if fstype == "crypto_luks":
                return AssuranceCheck("encryption", "warn", f"Partition {part['name']} is LUKS-encrypted — unlock or disable before installing.")
            if in_use and fstype in ("ntfs", "ntfs3"):
                # in_use on NTFS often means BitLocker locked (no fstype but children)
                # Check via blkid for BitLocker
                try:
                    from .runner import run_command
                    from .system import _as_root
                    r = run_command(_as_root(["blkid", "-o", "value", "-s", "TYPE", part["name"]]), capture_output=True, text=True, timeout=5)
                    if "BitLocker" in (r.stdout or ""):
                        return AssuranceCheck("encryption", "warn", f"Partition {part['name']} appears BitLocker-locked — suspend BitLocker in Windows (manage-bde -off) before resizing.")
                except (OSError, ValueError, AttributeError, RuntimeError) as exc:
                    _logger.debug("blkid probe failed for %s: %s", part.get("name"), exc, exc_info=True)
    except (OSError, ValueError, AttributeError, RuntimeError) as exc:
        _logger.debug("encryption disk probe failed for %s: %s", disk, exc, exc_info=True)
    return None


def run_preflight(
    source: ImageSource, *, power_root: Path = Path("/sys/class/power_supply"), disk: str = "",
) -> list[AssuranceCheck]:
    checks = []
    if source.kind == "embedded":
        if not source.verified or not source.digest:
            raise RuntimeError("The embedded installation image could not be verified.")
        checks.append(
            AssuranceCheck("image", "pass", f"Embedded image verified: {source.digest}")
        )
    elif source.requires_network:
        checks.append(AssuranceCheck("image", "pass", "Registry source selected and reachable"))
    else:
        checks.append(AssuranceCheck("image", "pass", "Local installation source selected"))
    checks.append(_battery_check(power_root))
    # Surface encryption blockers early so the user gets actionable remediation
    # before the disk step, not only when the later resize-specific check in
    # plan.py blocks the actual operation. `disk` is best-effort — the caller
    # may not have a target selected yet (e.g. before a guided flow's first
    # disk pick), and _encryption_check() itself already no-ops cleanly on ""/None.
    try:
        enc = _encryption_check(disk or None)
        if enc is not None:
            checks.append(enc)
    except (OSError, ValueError, AttributeError, RuntimeError) as exc:
        _logger.debug("preflight encryption probe failed: %s", exc, exc_info=True)
    return checks


def _bootloader_installed(root: Path) -> str | None:
    """Return a short reason if the mounted install looks bootable, else None."""
    entries = root / "boot" / "loader" / "entries"
    try:
        if entries.is_dir() and any(entries.glob("*.conf")):
            return "boot loader entries are present"
    except OSError:
        pass
    efi = root / "boot" / "efi" / "EFI"
    try:
        if efi.is_dir() and any(efi.iterdir()):
            return "EFI boot files are present"
    except OSError:
        pass
    deploy = root / "ostree" / "deploy"
    try:
        if deploy.is_dir() and any(deploy.iterdir()):
            return "ostree deployment is present"
    except OSError:
        pass
    return None


def validate_installed_target(
    etc: Path, request: InstallRequest, *, root: Path | None = None,
) -> list[AssuranceCheck]:
    """Verify identity, account, and (when mounted) bootloader before success."""
    if not etc.is_dir():
        raise RuntimeError("Installed deployment has no writable /etc tree.")
    hostname_path = etc / "hostname"
    try:
        installed_hostname = hostname_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"Could not verify installed hostname: {exc}") from exc
    if installed_hostname != request.hostname:
        raise RuntimeError(
            f"Installed hostname verification failed: expected {request.hostname!r}."
        )
    checks = [AssuranceCheck("hostname", "pass", installed_hostname)]

    if request.username:
        try:
            passwd = (etc / "passwd").read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Could not verify installed account: {exc}") from exc
        if not any(line.split(":", 1)[0] == request.username for line in passwd.splitlines()):
            raise RuntimeError(f"Installed account {request.username!r} was not created.")
        checks.append(AssuranceCheck("account", "pass", request.username))

    fstab = etc / "fstab"
    if not fstab.is_file():
        raise RuntimeError("Installed deployment is missing /etc/fstab.")
    checks.append(AssuranceCheck("filesystem", "pass", "Installed fstab is present"))

    if root is not None:
        reason = _bootloader_installed(root)
        if not reason:
            raise RuntimeError(
                "Installed system has no bootloader (no loader entries, EFI files, "
                "or ostree deployment). The target would not boot."
            )
        checks.append(AssuranceCheck("bootloader", "pass", reason))
    return checks
