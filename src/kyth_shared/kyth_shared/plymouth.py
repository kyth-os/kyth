"""Shared Plymouth/initramfs policy, inspection, and refresh logic."""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

from kyth_shared.commands import run, run_optional, run_text

THEME = "kyth"
FALLBACK_THEMES = ("bgrt-fedora", "bgrt", "spinner")
PLYMOUTH_CONFIG = (
    "[Daemon]\nTheme=kyth\nShowDelay=0\nDeviceTimeout=8\n"
    "UseFirmwareBackground=false\n"
)
REQUIRED_ENTRIES = (
    "usr/share/plymouth/themes/kyth/kyth.plymouth",
    "usr/share/plymouth/themes/kyth/kyth.script",
    "usr/share/plymouth/themes/kyth/kyth-logo.png",
    "usr/share/plymouth/themes/default.plymouth",
)
FINGERPRINT_INPUTS = (
    "/usr/lib/dracut/modules.d/99kyth-plymouth/module-setup.sh",
    "/usr/libexec/kyth-plymouth-branding-guard",
    "/etc/dracut.conf.d/99-kyth.conf",
    "/etc/plymouth/plymouthd.conf",
    "/usr/share/plymouth/plymouthd.defaults",
    "/usr/share/kyth/branding/transparent-watermark.png",
    "/usr/share/pixmaps/system-logo-white.png",
    "/usr/share/plymouth/themes/kyth/kyth.plymouth",
    "/usr/share/plymouth/themes/kyth/kyth.script",
    "/usr/share/plymouth/themes/kyth/kyth-logo.png",
)
TRANSPARENT_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)


def fingerprint(paths: tuple[str, ...] = FINGERPRINT_INPUTS) -> str:
    digest = hashlib.sha256()
    for name in paths:
        path = Path(name)
        try:
            content = path.read_bytes()
            item = hashlib.sha256(content).hexdigest()
            digest.update(f"{item}  {name}\n".encode())
        except OSError:
            digest.update(f"MISSING  {name}\n".encode())
    return digest.hexdigest()


def collect_images(
    boot: Path = Path("/boot"), modules: Path = Path("/usr/lib/modules")
) -> list[Path]:
    candidates = [*boot.glob("ostree/*/initramfs-*.img"), *boot.glob("initramfs-*.img")]
    images: list[Path] = []
    for image in candidates:
        kernel = image.name.removeprefix("initramfs-").removesuffix(".img")
        if (modules / kernel).is_dir() and image not in images:
            images.append(image)
    return images


def inspect_image(image: Path) -> list[str]:
    if shutil.which("lsinitrd") is None:
        return ["lsinitrd is unavailable"]
    listing = run_text(["lsinitrd", str(image)], timeout=60)
    defaults = run_text(
        ["lsinitrd", "-f", "/usr/share/plymouth/plymouthd.defaults", str(image)],
        timeout=60,
    )
    logo = run_optional(
        ["lsinitrd", "-f", "/usr/share/pixmaps/system-logo-white.png", str(image)],
        capture_output=True,
        timeout=60,
    )
    errors: list[str] = []
    if listing is None or listing.returncode:
        return [f"unable to inspect refreshed initramfs: {image}"]
    if defaults is None or defaults.returncode:
        errors.append(f"refreshed initramfs is missing Plymouth defaults: {image}")
    if logo is None or logo.returncode:
        errors.append(f"refreshed initramfs is missing transparent Plymouth system logo: {image}")
    for entry in REQUIRED_ENTRIES:
        if entry not in listing.stdout:
            errors.append(f"refreshed initramfs is missing {entry}: {image}")
    if any(f"usr/share/plymouth/themes/{theme}/" in listing.stdout for theme in FALLBACK_THEMES):
        errors.append(f"Plymouth fallback theme leaked into refreshed initramfs: {image}")
    if defaults is not None:
        for setting in ("Theme=kyth", "ShowDelay=0", "DeviceTimeout=8"):
            if setting not in defaults.stdout.splitlines():
                errors.append(f"refreshed initramfs Plymouth defaults are missing {setting}: {image}")
    watermark = Path("/usr/share/kyth/branding/transparent-watermark.png")
    if logo is not None and logo.returncode == 0:
        try:
            if logo.stdout != watermark.read_bytes():
                errors.append(f"refreshed initramfs contains the wrong Plymouth system logo: {image}")
        except OSError:
            errors.append("transparent Plymouth watermark is unavailable")
    return errors


def image_needs_refresh(image: Path) -> bool:
    return bool(inspect_image(image))


def ensure_dracut_config(path: Path = Path("/etc/dracut.conf.d/99-kyth.conf")) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = 'add_dracutmodules+=" ostree drm plymouth kyth-plymouth "\n'
    if "add_dracutmodules" not in text or "kyth-plymouth" not in text:
        text += '\nadd_dracutmodules+=" kyth-plymouth "\n'
    if "force_add_dracutmodules" not in text or "kyth-plymouth" not in text.partition("force_add_dracutmodules")[2]:
        text += 'force_add_dracutmodules+=" kyth-plymouth "\n'
    # Atomic tmp+fsync+replace
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        with open(tmp, "rb") as fh:
            os.fsync(fh.fileno())
    except OSError:
        pass
    tmp.replace(path)
    try:
        dfd = os.open(str(path.parent), os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass


def _prepare_include(root: Path) -> None:
    config = root / "etc/plymouth/plymouthd.conf"
    defaults = root / "usr/share/plymouth/plymouthd.defaults"
    logo = root / "usr/share/pixmaps/system-logo-white.png"
    themes = root / "usr/share/plymouth/themes"
    for path in (config.parent, defaults.parent, logo.parent, themes):
        path.mkdir(parents=True, exist_ok=True)
    config.write_text(PLYMOUTH_CONFIG, encoding="utf-8")
    shutil.copy2(config, defaults)
    source_logo = Path("/usr/share/kyth/branding/transparent-watermark.png")
    logo.write_bytes(source_logo.read_bytes() if source_logo.is_file() else TRANSPARENT_PNG)
    shutil.copytree(Path("/usr/share/plymouth/themes/kyth"), themes / "kyth", symlinks=True)
    (themes / "default.plymouth").symlink_to("kyth/kyth.plymouth")


def _refresh_image(image: Path, include: Path) -> None:
    kernel = image.name.removeprefix("initramfs-").removesuffix(".img")
    result = run(
        [
            "dracut", "--tmpdir", "/var/tmp", "--no-hostonly", "--kver", kernel,
            "--reproducible", "--force", "--add", "drm plymouth ostree kyth-plymouth",
            "--include", include / "etc/plymouth", "/etc/plymouth",
            "--include", include / "usr/share/plymouth", "/usr/share/plymouth",
            "--include", include / "usr/share/pixmaps/system-logo-white.png",
            "/usr/share/pixmaps/system-logo-white.png", image, kernel,
        ],
        env={**os.environ, "TMPDIR": "/var/tmp"},
    )
    if result.returncode:
        raise RuntimeError(f"dracut failed for {image}")
    errors = inspect_image(image)
    if errors:
        raise RuntimeError("\n".join(errors))


def _refresh_writable() -> int:
    state = Path("/var/lib/kyth")
    state.mkdir(parents=True, exist_ok=True)
    fp_file = state / "boot-splash-initramfs.sha256"
    marker = state / "boot-splash-initramfs-v17"
    run_optional(["plymouth-set-default-theme", THEME])
    for guard in (
        "/usr/libexec/kyth-boot-branding-guard",
        "/usr/libexec/kyth-plymouth-branding-guard",
    ):
        if Path(guard).is_file():
            run_optional([guard])
    try:
        ensure_dracut_config()
    except OSError:
        pass
    current = fingerprint()
    images = collect_images()
    old = fp_file.read_text(encoding="utf-8").strip() if fp_file.is_file() else ""
    if marker.exists() and old == current and images and not any(map(image_needs_refresh, images)):
        return 0
    with tempfile.TemporaryDirectory(prefix="kyth-plymouth-initramfs-", dir="/tmp") as tmp:
        include = Path(tmp)
        _prepare_include(include)
        if images:
            for image in images:
                _refresh_image(image, include)
        else:
            result = run([
                "dracut", "--tmpdir", "/var/tmp", "--regenerate-all", "--force",
                "--add", "drm plymouth ostree kyth-plymouth",
                "--include", include / "etc/plymouth", "/etc/plymouth",
                "--include", include / "usr/share/plymouth", "/usr/share/plymouth",
                "--include", include / "usr/share/pixmaps/system-logo-white.png",
                "/usr/share/pixmaps/system-logo-white.png",
            ], env={**os.environ, "TMPDIR": "/var/tmp"})
            if result.returncode:
                raise RuntimeError("dracut --regenerate-all failed")
            for image in collect_images():
                errors = inspect_image(image)
                if errors:
                    raise RuntimeError("\n".join(errors))
    fp_file.write_text(current + "\n", encoding="utf-8")
    marker.touch()
    return 0


def refresh() -> int:
    """Refresh while preserving an initially read-only /boot mount."""
    options = run_text(["findmnt", "-no", "OPTIONS", "/boot"], timeout=10)
    boot_was_readonly = (
        options is not None
        and options.returncode == 0
        and "ro" in options.stdout.strip().split(",")
    )
    if boot_was_readonly:
        remount = run_optional(["mount", "-o", "remount,bind,rw", "/boot"])
        if remount is None or remount.returncode:
            remount = run_optional(["mount", "-o", "remount,rw", "/boot"])
        if remount is None or remount.returncode:
            print(
                "WARNING: /boot is read-only and could not be remounted; "
                "skipping initramfs refresh",
                file=sys.stderr,
            )
            return 0
    try:
        return _refresh_writable()
    finally:
        if boot_was_readonly:
            run_optional(["mount", "-o", "remount,ro", "/boot"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", choices=("refresh", "verify"), default="refresh")
    parser.add_argument("image", nargs="?")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            if not args.image:
                parser.error("verify requires an image")
            errors = inspect_image(Path(args.image))
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1 if errors else 0
        return refresh()
    except (OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
