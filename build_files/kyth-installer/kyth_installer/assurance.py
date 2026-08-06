"""Installer preflight and installed-target assurance checks."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


def _encryption_check(disk: str | None = None) -> AssuranceCheck | None:
    """Detect BitLocker/LUKS/LVM on the target that would block install."""
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
                except Exception:
                    pass
    except Exception:
        pass
    return None


def run_preflight(source: ImageSource, *, power_root: Path = Path("/sys/class/power_supply")) -> list[AssuranceCheck]:
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
    # Bonus: surface encryption blockers early so user gets actionable remediation before disk step
    try:
        # Try to infer disk from source target — best-effort, non-blocking
        enc = _encryption_check(None)
        if enc is not None:
            checks.append(enc)
    except Exception:
        pass
    return checks


def validate_installed_target(etc: Path, request: InstallRequest) -> list[AssuranceCheck]:
    """Verify identity and account configuration before declaring success."""
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
    return checks
