"""Read-only daily-driver readiness checks for KythOS."""
from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import shutil
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .commands import run
from .health import from_smoke_results


@dataclass(frozen=True)
class Result:
    level: str
    name: str
    detail: str
    section: str


class SmokeCheck:
    """Collect and render diagnostics while keeping probes independently testable."""

    def __init__(self, *, verbose: bool = False, quiet: bool = False) -> None:
        self.verbose = verbose
        self.quiet = quiet
        self.results: list[Result] = []
        self.current_section = ""

    def section(self, name: str) -> None:
        self.current_section = name
        if not self.quiet:
            print(f"\n== {name} ==")

    def record(self, level: str, name: str, detail: str) -> None:
        self.results.append(Result(level, name, detail, self.current_section))
        if not self.quiet:
            print(f"{level:<5} {name:<34} {detail}")

    def passed(self, name: str, detail: str) -> None:
        self.record("PASS", name, detail)

    def warn(self, name: str, detail: str) -> None:
        self.record("WARN", name, detail)

    def fail(self, name: str, detail: str) -> None:
        self.record("FAIL", name, detail)

    @staticmethod
    def command(command: Sequence[str], *, timeout: int | None = None):
        try:
            return run(
                list(command), check=False, capture_output=True, text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return None

    def check_command(self, command: str, label: str, *, optional: bool = False) -> None:
        path = shutil.which(command)
        if path:
            self.passed(label, path)
        elif optional:
            self.warn(label, "not installed or unavailable on this image")
        else:
            self.fail(label, "missing command")

    def check_path(
        self, path: str | Path, label: str, *, executable: bool = False,
        absent: bool = False,
    ) -> None:
        target = Path(path).expanduser()
        exists = target.exists()
        if absent:
            (self.fail if exists else self.passed)(
                label, f"{target} should not exist" if exists else f"{target} absent"
            )
        elif exists and (not executable or os.access(target, os.X_OK)):
            self.passed(label, str(target))
        else:
            suffix = " missing or not executable" if executable else " missing"
            self.fail(label, f"{target}{suffix}")

    def check_contains(
        self, path: str | Path, needle: str, label: str, detail: str,
        *, negate: bool = False,
    ) -> None:
        target = Path(path).expanduser()
        try:
            found = needle in target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            found = False
        good = not found if negate else found
        if good:
            self.passed(label, detail)
        else:
            verb = "contains an unwanted entry" if negate else "does not contain expected entry"
            self.fail(label, f"{target} {verb}")

    def check_unit(
        self, unit: str, label: str, *, user: bool = False,
        enabled: bool = False,
    ) -> None:
        if not shutil.which("systemctl"):
            self.warn(label, "systemctl unavailable")
            return
        prefix = ["systemctl", "--user"] if user else ["systemctl"]
        state = "is-enabled" if enabled else "is-active"
        result = self.command([*prefix, state, "--quiet", unit])
        if result and result.returncode == 0:
            self.passed(label, "enabled" if enabled else "active")
            return
        if user:
            self.warn(label, "not active in this user session")
            return
        installed = self.command(["systemctl", "list-unit-files", unit])
        if installed and installed.returncode == 0 and unit in installed.stdout:
            self.warn(label, f"installed but not {'enabled' if enabled else 'active'}")
        else:
            self.fail(label, "unit missing")

    def check_flatpak(self, app_id: str, label: str) -> None:
        if not shutil.which("flatpak"):
            self.fail(label, "flatpak command missing")
            return
        result = self.command(["flatpak", "info", app_id])
        if result and result.returncode == 0:
            self.passed(label, f"{app_id} installed")
        else:
            self.warn(label, f"{app_id} missing; run sudo systemctl start kyth-default-flatpaks.service")

    def identity_and_updates(self) -> None:
        self.section("Identity And Update Safety")
        release = Path("/etc/os-release")
        text = release.read_text(errors="replace") if release.is_file() else ""
        pretty = next(
            (line.partition("=")[2].strip('"') for line in text.splitlines()
             if line.startswith("PRETTY_NAME=")), "unknown",
        )
        (self.passed if pretty.startswith("KythOS") else self.fail)(
            "OS identity", pretty if pretty.startswith("KythOS") else
            "/etc/os-release does not advertise KythOS",
        )
        self.check_contains(release, "ID=kythos", "OS identity ID", "boot metadata uses KythOS identity")
        self.check_command("bootc", "bootc")
        if shutil.which("bootc"):
            status = self.command(["bootc", "status", "--format", "json"])
            if (not status or status.returncode) and shutil.which("sudo"):
                status = self.command(["sudo", "-n", "bootc", "status", "--format", "json"])
            if status and status.returncode == 0:
                try:
                    data = json.loads(status.stdout)
                    booted = data.get("status", {}).get("booted", {})
                    image = booted.get("image", {})
                    ref = image.get("image", {}).get("image") or image.get("imageDigest") or "unknown"
                    self.passed("Booted image", ref)
                    if data.get("status", {}).get("staged"):
                        self.warn("Staged update", "reboot before performance testing")
                    else:
                        self.passed("Staged update", "none detected")
                except (TypeError, ValueError):
                    self.fail("bootc status", "invalid JSON")
            else:
                self.fail("bootc status", "unreadable")
        for unit, label in (
            ("kyth-selinux-relabel-home.service", "SELinux home relabel"),
            ("kyth-first-boot-message.service", "First boot message"),
            ("fstrim.timer", "SSD trim timer"),
            ("fwupd.service", "Firmware service"),
        ):
            self.check_unit(unit, label, enabled=True)
        for command, label in (("python3", "Python 3"), ("pip3", "pip3"), ("pip", "pip")):
            self.check_command(command, label)

    def desktop(self) -> None:
        self.section("Desktop Familiarity")
        desktop = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION", "unknown")
        (self.passed if "KDE" in desktop or desktop.startswith("plasma") else self.warn)(
            "Desktop session", desktop
        )
        self.check_unit("display-manager.service", "Login manager", enabled=True)
        for path, label in (
            ("/usr/share/wallpapers/kyth/metadata.json", "KythOS wallpaper"),
            ("/usr/share/plymouth/themes/kyth/kyth-logo.png", "Plymouth KythOS logo"),
            ("/usr/share/applications/kyth-welcome.desktop", "Hub launcher"),
            ("/usr/bin/kyth-user-polish", "User comfort polish"),
            ("/usr/bin/kyth-apply-desktop-layout", "KythOS default layout helper"),
            ("/etc/xdg/mimeapps.list", "Default app associations"),
            ("/usr/bin/kyth-post-update-check", "Post-update confidence"),
            ("/usr/bin/kyth-session-snapshot", "Session snapshot helper"),
        ):
            self.check_path(path, label)
        # Portal stack — screen share / Flatpak permission dialogs on Wayland.
        portal_ok = any(
            os.path.exists(p)
            for p in (
                "/usr/libexec/xdg-desktop-portal",
                "/usr/libexec/xdg-desktop-portal-kde",
                "/usr/lib64/libexec/xdg-desktop-portal-kde",
            )
        ) or bool(shutil.which("xdg-desktop-portal"))
        (self.passed if portal_ok else self.warn)(
            "xdg-desktop-portal stack",
            "portal binaries present" if portal_ok else "xdg-desktop-portal / kde backend missing",
        )
        self.check_contains(
            "/etc/plymouth/plymouthd.conf", "Theme=kyth", "Plymouth theme",
            "KythOS boot splash selected",
        )
        self.check_contains(
            "/etc/default/grub", 'GRUB_DISTRIBUTOR="KythOS"',
            "GRUB distributor branding", "bootloader menu metadata uses KythOS",
        )
        for path, label in (
            ("/usr/share/plymouth/themes/bgrt-fedora", "Fedora Plymouth BGRT theme"),
            ("/usr/share/plymouth/themes/bgrt", "Plymouth firmware BGRT fallback theme"),
        ):
            self.check_path(path, label, absent=True)

    def services_and_hardware(self) -> None:
        self.section("Core Daily-Driver Services")
        for unit, label, user in (
            ("NetworkManager.service", "Network manager", False),
            ("bluetooth.service", "Bluetooth", False),
            ("rtkit-daemon.service", "Realtime audio helper", False),
            ("pipewire.service", "PipeWire", True),
            ("wireplumber.service", "WirePlumber", True),
        ):
            self.check_unit(unit, label, user=user)
        for unit, label in (
            ("kyth-bluetooth-enable.service", "Bluetooth auto-enable"),
            ("irqbalance.service", "IRQ balancing"),
        ):
            self.check_unit(unit, label, enabled=True)

        self.section("Hardware And Drivers")
        self.check_command("lspci", "PCI hardware probe")
        lspci = self.command(["lspci", "-nn"]) if shutil.which("lspci") else None
        gpu = ""
        if lspci:
            gpu = next(
                (line for line in lspci.stdout.splitlines()
                 if any(kind in line.lower() for kind in ("vga", "3d", "display"))), ""
            )
        (self.passed if gpu else self.warn)("GPU detected", gpu or "no VGA/3D/display adapter found")
        vulkan = self.command(["vulkaninfo", "--summary"], timeout=10) if shutil.which("vulkaninfo") else None
        if vulkan and vulkan.returncode == 0:
            device = next(
                (line.partition("=")[2].strip() for line in vulkan.stdout.splitlines()
                 if "deviceName" in line), "vulkaninfo works",
            )
            self.passed("Vulkan", device)
        elif vulkan:
            self.fail("Vulkan", "vulkaninfo failed")
        else:
            self.warn("Vulkan", "vulkaninfo unavailable; install vulkan-tools for deeper validation")

    def gaming_and_work(self) -> None:
        self.section("Gaming Stack")
        for command, label in (
            ("gamemoderun", "GameMode wrapper"), ("gamescope", "Gamescope"),
            ("mangohud", "MangoHud"), ("kyth-gamescope", "KythOS Gamescope presets"),
            ("kyth-performance-mode", "KythOS performance modes"),
            ("kyth-proton-cachyos-update", "Proton-CachyOS updater"), ("umu-run", "umu launcher"),
        ):
            self.check_command(command, label, optional=True)
        for path, label in (
            ("/etc/gamemode.ini", "GameMode config"),
            ("/etc/MangoHud/MangoHud.conf", "MangoHud config"),
            ("/etc/vkBasalt.conf", "vkBasalt config"),
        ):
            self.check_path(path, label)
        (self.passed if Path("/dev/ntsync").exists() else self.warn)(
            "NTSYNC", "/dev/ntsync present" if Path("/dev/ntsync").exists()
            else "not present; Proton will fall back to fsync/esync",
        )
        for app_id, label in (
            ("com.valvesoftware.Steam", "Steam Flatpak"),
            ("net.lutris.Lutris", "Lutris Flatpak"),
            ("com.heroicgameslauncher.hgl", "Heroic Flatpak"),
            ("com.usebottles.bottles", "Bottles Flatpak"),
            ("com.github.mtkennerly.ludusavi", "Ludusavi Flatpak"),
            ("com.github.Matoking.protontricks", "Protontricks Flatpak"),
        ):
            self.check_flatpak(app_id, label)

        self.section("Work Productivity")
        for command, label in (
            ("fprintd", "fingerprint daemon"), ("pcscd", "smartcard daemon"),
            ("openconnect", "VPN (GlobalProtect/AnyConnect)"),
            ("vpnc", "VPN (Cisco legacy)"), ("smbclient", "SMB client"),
        ):
            self.check_command(command, label, optional=command in {"fprintd", "pcscd"})
        cameras = glob.glob("/dev/video*")
        (self.passed if cameras else self.warn)(
            "Camera", f"video capture device present ({cameras[0]})" if cameras
            else "no /dev/video* device detected",
        )

    def background_and_tools(self) -> None:
        self.section("KythOS Background Work")
        for unit, label in (
            ("kyth-hw-setup.service", "First-boot hardware setup"),
            ("kyth-flathub-setup.service", "Flathub setup"),
            ("kyth-default-flatpaks.service", "Default Flatpaks"),
            ("kyth-proton-cachyos-update.timer", "Proton-CachyOS timer"),
            ("kyth-duperemove.timer", "Game cache dedupe timer"),
            ("kyth-local-bin-migrate.service", "Local bin migration"),
        ):
            self.check_unit(unit, label, enabled=True)
        self.check_command("kyth-full-update", "KythOS full updater")
        for command, label in (
            ("kyth-ai-dev", "AI developer environment helper"),
            ("kyth-device-info", "Support snapshot"),
            ("kyth-controller-check", "Controller check"),
            ("kyth-resume-check", "Resume check"),
            ("kyth-nvidia-status", "NVIDIA status check"),
        ):
            self.check_command(command, label, optional=True)

        self.section("Power User Tools")
        for command, label in (
            ("bat", "bat (better cat)"), ("eza", "eza (better ls)"),
            ("fd", "fd (better find)"), ("rg", "ripgrep"), ("fzf", "fzf (fuzzy finder)"),
            ("zoxide", "zoxide (smart cd)"), ("starship", "starship prompt"),
            ("delta", "git-delta (better diff)"), ("hx", "helix editor"),
            ("fish", "fish shell"), ("zellij", "zellij (terminal mux)"),
        ):
            self.check_command(command, label, optional=True)

    def verbose_context(self) -> None:
        if not self.verbose:
            return
        self.section("Verbose Context")
        for heading, command in (
            ("bootc status", ["bootc", "status"]),
            ("flatpak apps", ["flatpak", "list", "--app", "--columns=application,name,installation"]),
            ("recent warnings", ["journalctl", "-b", "-p", "warning", "--no-pager", "-n", "30"]),
        ):
            print(f"-- {heading} --")
            result = self.command(command)
            if result:
                print(result.stdout, end="")
            print()

    def execute(self) -> None:
        if not self.quiet:
            print("KythOS Smoke Check")
            print(f"Generated: {datetime.now().astimezone().isoformat()}")
            print(f"Host: {socket.gethostname() or 'unknown'}")
            print(f"Kernel: {platform.release() or 'unknown'}")
        self.identity_and_updates()
        self.desktop()
        self.services_and_hardware()
        self.gaming_and_work()
        self.background_and_tools()
        self.verbose_context()

    def exit_code(self, *, strict: bool) -> int:
        failures = sum(result.level == "FAIL" for result in self.results)
        warnings = sum(result.level == "WARN" for result in self.results)
        passes = sum(result.level == "PASS" for result in self.results)
        if not self.quiet:
            print("\n== Summary ==")
            print(f"PASS: {passes}\nWARN: {warnings}\nFAIL: {failures}")
        if failures:
            if not self.quiet:
                print("Result: not daily-driver ready yet. Fix failed checks first.")
            return 2
        if warnings:
            if not self.quiet:
                print("Result: usable, with warnings to review.")
            return 1 if strict else 0
        if not self.quiet:
            print("Result: daily-driver smoke check is clean.")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kyth-smoke-check",
        description="Check KythOS daily-driver readiness.",
    )
    parser.add_argument("--strict", action="store_true", help="return 1 when warnings are present")
    parser.add_argument("-v", "--verbose", action="store_true", help="include raw diagnostic context")
    parser.add_argument("--json", action="store_true", help="emit a support-safe JSON health report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checker = SmokeCheck(verbose=args.verbose, quiet=args.json)
    checker.execute()
    if args.json:
        print(from_smoke_results(checker.results).to_json(), end="")
    return checker.exit_code(strict=args.strict)
