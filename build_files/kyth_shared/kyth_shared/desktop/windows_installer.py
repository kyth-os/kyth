"""Safe, testable Windows-installer workflow backed by Bottles."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..commands import APPLICATION_RUNNER, CommandRunner

BOTTLES_ID = "com.usebottles.bottles"
FLATHUB_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"


class InstallerKind(StrEnum):
    EXE = "exe"
    MSI = "msi"


class Compatibility(StrEnum):
    LIKELY = "likely"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


class WorkflowFailureKind(StrEnum):
    INVALID_FILE = "invalid-file"
    FILE_CHANGED = "file-changed"
    BOTTLES_INSTALL = "bottles-install"
    BOTTLE_CREATE = "bottle-create"
    FILE_STAGE = "file-stage"
    LAUNCH = "launch"


class WorkflowFailure(RuntimeError):
    def __init__(self, kind: WorkflowFailureKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    size: int
    modified_ns: int


@dataclass(frozen=True)
class InstallerRequest:
    source: Path
    kind: InstallerKind
    architecture: str
    identity: FileIdentity
    sha256: str


@dataclass(frozen=True)
class CompatibilityAssessment:
    level: Compatibility
    summary: str
    detail: str


@dataclass(frozen=True)
class BottlePlan:
    name: str
    environment: str
    architecture: str


@dataclass(frozen=True)
class StagedInstaller:
    host_path: Path
    sandbox_path: Path


@dataclass(frozen=True)
class LaunchResult:
    bottle: BottlePlan
    staged: StagedInstaller


ProgressCallback = Callable[[str], None]

_PE_MACHINES = {
    0x014C: "win32",
    0x8664: "win64",
    0xAA64: "arm64",
}
_UNSUPPORTED_PATTERNS = re.compile(
    r"(?:^|[-_. ])(?:anti[-_. ]?cheat|battleye|easyanti(?:cheat)?|driver|firmware|"
    r"bios|chipset|microsoft[-_. ]?store|windows[-_. ]?update)(?:$|[-_. ])",
    re.IGNORECASE,
)
_GAMING_PATTERNS = re.compile(
    r"(?:game|gaming|steam|battle[-_. ]?net|blizzard|gog|epic|launcher|ubisoft|uplay)",
    re.IGNORECASE,
)


def _identity(path: Path) -> FileIdentity:
    info = path.stat()
    return FileIdentity(info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inspect_pe(source: Any) -> str:
    header = source.read(64)
    if len(header) < 64 or header[:2] != b"MZ":
        raise WorkflowFailure(
            WorkflowFailureKind.INVALID_FILE,
            "The file does not contain a valid Windows executable header.",
        )
    pe_offset = int.from_bytes(header[0x3C:0x40], "little")
    if pe_offset < 64 or pe_offset > 64 * 1024 * 1024:
        raise WorkflowFailure(
            WorkflowFailureKind.INVALID_FILE,
            "The Windows executable header points outside a safe inspection range.",
        )
    source.seek(pe_offset)
    pe_header = source.read(6)
    if len(pe_header) != 6 or pe_header[:4] != b"PE\0\0":
        raise WorkflowFailure(
            WorkflowFailureKind.INVALID_FILE,
            "The file has a DOS header but no valid PE executable header.",
        )
    return _PE_MACHINES.get(int.from_bytes(pe_header[4:6], "little"), "unknown")


def inspect_installer(filepath: str | os.PathLike[str]) -> InstallerRequest:
    """Validate an installer by content and capture an immutable launch identity."""
    path = Path(filepath).expanduser()
    try:
        if path.is_symlink() or not path.is_file():
            raise WorkflowFailure(
                WorkflowFailureKind.INVALID_FILE,
                "Choose a regular, non-symbolic-link installer file.",
            )
        resolved = path.resolve(strict=True)
        mode = resolved.stat().st_mode
        if not stat.S_ISREG(mode):
            raise WorkflowFailure(
                WorkflowFailureKind.INVALID_FILE,
                "Choose a regular installer file.",
            )
        suffix = resolved.suffix.lower()
        with resolved.open("rb") as source:
            if suffix == ".exe":
                kind = InstallerKind.EXE
                architecture = _inspect_pe(source)
            elif suffix == ".msi":
                if source.read(8) != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                    raise WorkflowFailure(
                        WorkflowFailureKind.INVALID_FILE,
                        "The file does not contain a valid MSI compound-document header.",
                    )
                kind = InstallerKind.MSI
                architecture = "win64"
            else:
                raise WorkflowFailure(
                    WorkflowFailureKind.INVALID_FILE,
                    "Kyth currently supports Windows .exe and .msi installers only.",
                )
        return InstallerRequest(
            source=resolved,
            kind=kind,
            architecture=architecture,
            identity=_identity(resolved),
            sha256=_sha256(resolved),
        )
    except WorkflowFailure:
        raise
    except OSError as exc:
        raise WorkflowFailure(
            WorkflowFailureKind.INVALID_FILE,
            f"The installer could not be read: {exc}",
        ) from exc


def assess_compatibility(request: InstallerRequest) -> CompatibilityAssessment:
    """Return an honest, conservative compatibility assessment."""
    if request.architecture == "arm64":
        return CompatibilityAssessment(
            Compatibility.UNSUPPORTED,
            "ARM Windows installer",
            "This installer targets Windows on ARM, which this Kyth compatibility path does not support.",
        )
    if _UNSUPPORTED_PATTERNS.search(request.source.stem):
        return CompatibilityAssessment(
            Compatibility.UNSUPPORTED,
            "System-level Windows component",
            "Drivers, firmware tools, kernel anti-cheat, and Windows system components generally cannot run through Wine.",
        )
    if request.architecture in {"win32", "win64"}:
        return CompatibilityAssessment(
            Compatibility.LIKELY,
            "Standard Windows installer",
            "Many conventional desktop installers work, but compatibility is not guaranteed.",
        )
    return CompatibilityAssessment(
        Compatibility.UNKNOWN,
        "Unknown Windows architecture",
        "Kyth can try this installer, but its architecture could not be identified reliably.",
    )


def plan_bottle(request: InstallerRequest) -> BottlePlan:
    stem = re.sub(r"[^a-z0-9]+", "-", request.source.stem.lower()).strip("-")
    for token in ("setup", "installer", "install", "update", "updater"):
        stem = re.sub(rf"(?:^|-){token}(?:-|$)", "-", stem).strip("-")
    stem = stem[:36] or "windows-app"
    suffix = request.sha256[:8]
    architecture = request.architecture if request.architecture in {"win32", "win64"} else "win64"
    environment = "gaming" if _GAMING_PATTERNS.search(request.source.stem) else "application"
    return BottlePlan(f"Kyth-{stem}-{suffix}", environment, architecture)


def flatpak_install_commands() -> tuple[list[str], list[str]]:
    return (
        ["flatpak", "remote-add", "--if-not-exists", "--user", "flathub", FLATHUB_URL],
        ["flatpak", "install", "-y", "--noninteractive", "--user", "flathub", BOTTLES_ID],
    )


def bottles_cli(*args: str) -> list[str]:
    return ["flatpak", "run", "--command=bottles-cli", BOTTLES_ID, *args]


def bottle_names(payload: str) -> set[str]:
    """Parse Bottles JSON across the list shapes used by supported releases."""
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return {line.strip() for line in payload.splitlines() if line.strip()}
    if isinstance(data, dict):
        data = data.get("bottles", data)
        if isinstance(data, dict):
            return {str(name) for name in data}
    if not isinstance(data, list):
        return set()
    names: set[str] = set()
    for item in data:
        if isinstance(item, str):
            names.add(item)
        elif isinstance(item, dict):
            name = item.get("Name") or item.get("name")
            if name:
                names.add(str(name))
    return names


def stage_installer(request: InstallerRequest, home: Path | None = None) -> StagedInstaller:
    """Copy the installer into Bottles' private Flatpak storage."""
    if _identity(request.source) != request.identity:
        raise WorkflowFailure(
            WorkflowFailureKind.FILE_CHANGED,
            "The installer changed after it was inspected. Reopen it to continue safely.",
        )
    user_home = (home or Path.home()).resolve()
    relative = Path("kyth-installers") / request.sha256[:16]
    host_dir = user_home / ".var" / "app" / BOTTLES_ID / "cache" / relative
    safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", request.source.name)
    host_path = host_dir / safe_name
    try:
        host_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not host_path.exists() or _sha256(host_path) != request.sha256:
            temporary = host_path.with_suffix(host_path.suffix + ".part")
            with request.source.open("rb") as source, temporary.open("wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
            os.chmod(temporary, 0o600)
            if _sha256(temporary) != request.sha256:
                temporary.unlink(missing_ok=True)
                raise WorkflowFailure(
                    WorkflowFailureKind.FILE_CHANGED,
                    "The installer changed while it was being prepared. Reopen it to continue safely.",
                )
            temporary.replace(host_path)
        # Flatpak exposes its per-app cache at this same absolute host path.
        # Passing ~/.cache here would address the host's cache, which Bottles
        # cannot access without weakening its sandbox.
        return StagedInstaller(host_path, host_path)
    except WorkflowFailure:
        raise
    except OSError as exc:
        raise WorkflowFailure(
            WorkflowFailureKind.FILE_STAGE,
            f"Could not prepare the installer inside the Bottles sandbox: {exc}",
        ) from exc


class WindowsInstallerWorkflow:
    """Prepare Bottles and launch one validated installer without a shell."""

    def __init__(self, runner: CommandRunner | None = None, *, home: Path | None = None) -> None:
        self.runner = runner or APPLICATION_RUNNER
        self.home = home

    def _run(
        self,
        command: list[str],
        failure: WorkflowFailureKind,
        message: str,
        *,
        timeout: float = 120,
    ) -> str:
        try:
            result = self.runner.run(
                command, capture_output=True, text=True, timeout=timeout
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise WorkflowFailure(failure, f"{message}: {exc}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown error").strip()
            raise WorkflowFailure(failure, f"{message}: {detail}")
        return result.stdout or ""

    def bottles_installed(self) -> bool:
        try:
            result = self.runner.run(
                ["flatpak", "info", BOTTLES_ID], capture_output=True, text=True
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0

    def ensure_bottles(self, progress: ProgressCallback) -> None:
        if self.bottles_installed():
            return
        progress("Preparing Flathub…")
        remote, install = flatpak_install_commands()
        self._run(remote, WorkflowFailureKind.BOTTLES_INSTALL, "Could not configure Flathub")
        progress("Installing Bottles…")
        self._run(
            install,
            WorkflowFailureKind.BOTTLES_INSTALL,
            "Could not install Bottles",
            timeout=3600,
        )

    def ensure_bottle(self, plan: BottlePlan, progress: ProgressCallback) -> None:
        progress("Checking isolated environments…")
        output = self._run(
            bottles_cli("--json", "list", "bottles"),
            WorkflowFailureKind.BOTTLE_CREATE,
            "Could not list Bottles environments",
        )
        if plan.name in bottle_names(output):
            return
        progress("Creating an isolated Windows environment…")
        self._run(
            bottles_cli(
                "new",
                "--bottle-name",
                plan.name,
                "--environment",
                plan.environment,
                "--arch",
                plan.architecture,
            ),
            WorkflowFailureKind.BOTTLE_CREATE,
            "Could not create the Windows environment",
            timeout=1800,
        )

    def execute(
        self,
        request: InstallerRequest,
        progress: ProgressCallback | None = None,
    ) -> LaunchResult:
        report = progress or (lambda _message: None)
        self.ensure_bottles(report)
        plan = plan_bottle(request)
        self.ensure_bottle(plan, report)
        report("Copying the installer into the sandbox…")
        staged = stage_installer(request, self.home)
        report("Opening the Windows installer…")
        try:
            self.runner.spawn(
                bottles_cli("run", "-b", plan.name, "-e", os.fspath(staged.sandbox_path)),
                start_new_session=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise WorkflowFailure(
                WorkflowFailureKind.LAUNCH,
                f"Bottles could not launch the installer: {exc}",
            ) from exc
        return LaunchResult(plan, staged)
