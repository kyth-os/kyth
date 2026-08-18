"""Repair account databases on an offline (unbooted) target root.

Both install entry points that write a fresh KythOS deployment — the graphical
kyth-installer and the kyth-partition-install CLI — must
apply the exact same fix-up to a target tree's /etc/{passwd,group,shadow}
after `bootc install`: merge in any system accounts missing from the base
image's actual /etc (falling back to fixed records for accounts like sddm
that may not exist yet), complete /etc/shadow for any of them, and lock the
account database down to the same permissions a booted system would have.

This used to be reimplemented independently in Python and Bash and had already
drifted in minor ways. This module is the single canonical implementation.
Every installer entry point now reaches it through kyth_installer's allowlisted
command runner (see kyth_installer.system).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

RunFn = Callable[..., subprocess.CompletedProcess]

SYSTEM_GROUP_FALLBACKS = {"sddm": "sddm:x:959:"}

SYSTEM_PASSWD_FALLBACKS = {
    "sddm": "sddm:x:959:959:SDDM Greeter Account:/var/lib/sddm:/usr/sbin/nologin",
}


def _default_run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    kwargs.setdefault("timeout", 30)
    return subprocess.run(argv, **kwargs)


def _read_lines(path: Path, run: RunFn) -> list[str]:
    """Read a target-tree file via elevated cat (never host open())."""
    result = run(["cat", str(path)], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return []
    return result.stdout.splitlines()


def _write_lines(path: Path, lines: list[str], mode: int, run: RunFn) -> None:
    """Write a target-tree file via elevated mkdir/tee/chmod.

    passwd uses the literal "x" placeholder; shadow records contain hashes.
    Always go through ``run`` so account databases never depend on this
    process being able to open the mounted deploy tree itself.
    """
    path_str = str(path)
    content = "\n".join(lines) + "\n"
    run(["mkdir", "-p", str(path.parent)], check=True)
    run(["tee", path_str], input=content, text=True, stdout=subprocess.DEVNULL, check=True)
    # mode is an integer permission (e.g. 0o644); chmod wants octal digits.
    run(["chmod", f"{mode:o}", path_str], check=True)


def _path_exists(path: Path, run: RunFn) -> bool:
    result = run(["test", "-e", str(path)], check=False, capture_output=True)
    return result.returncode == 0


def _chmod_path(path: Path, mode: int, run: RunFn) -> None:
    run(["chmod", f"{mode:o}", str(path)], check=True)


def _append_missing_records(
    dest: Path, sources: list[Path], fallbacks: dict[str, str], run: RunFn,
) -> bool:
    lines = _read_lines(dest, run)
    names = {line.split(":", 1)[0] for line in lines if line and ":" in line}
    changed = False

    for source in sources:
        for line in _read_lines(source, run):
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
        _write_lines(dest, lines, 0o644, run)
    return changed


def ensure_system_accounts(deploy_root: str, log: Callable[[str], None], *, run: RunFn) -> None:
    root = Path(deploy_root)
    etc = root / "etc"

    group_changed = _append_missing_records(
        etc / "group", [root / "usr/lib/group"], SYSTEM_GROUP_FALLBACKS, run,
    )
    passwd_changed = _append_missing_records(
        etc / "passwd", [root / "usr/lib/passwd"], SYSTEM_PASSWD_FALLBACKS, run,
    )

    passwd_names = {
        line.split(":", 1)[0] for line in _read_lines(etc / "passwd", run) if line and ":" in line
    }
    shadow = etc / "shadow"
    shadow_lines = _read_lines(shadow, run)
    shadow_names = {
        line.split(":", 1)[0] for line in shadow_lines if line and ":" in line
    }
    shadow_changed = False
    for name in sorted(passwd_names - shadow_names):
        if name == "root" or not name:
            continue
        shadow_lines.append(f"{name}:!*:19700:0:99999:7:::")
        shadow_changed = True
    if shadow_changed:
        _write_lines(shadow, shadow_lines, 0o000, run)
    elif _path_exists(shadow, run):
        _chmod_path(shadow, 0o000, run)

    sddm_home = root / "var/lib/sddm"
    run(["mkdir", "-p", str(sddm_home)], check=True)

    # Read the actual sddm UID/GID from the target's etc/passwd to support
    # dynamic allocation and ensure numeric chown works even if the host
    # environment has no sddm user/group of its own.
    sddm_uid, sddm_gid = "959", "959"
    for line in _read_lines(etc / "passwd", run):
        if line.startswith("sddm:"):
            parts = line.split(":")
            if len(parts) >= 4:
                sddm_uid, sddm_gid = parts[2], parts[3]
                break
    run(["chown", f"{sddm_uid}:{sddm_gid}", str(sddm_home)], check=False)
    restorecon = shutil.which("restorecon")
    if restorecon:
        run(
            [restorecon, str(etc / "passwd"), str(etc / "group"), str(shadow), str(sddm_home)],
            check=False,
        )

    if group_changed or passwd_changed or shadow_changed:
        log("Repaired installed system account databases for SDDM/D-Bus")


def create_installer_user(
    deploy_root: str,
    target_root: str,
    username: str,
    password_hash: str,
    log: Callable[[str], None],
    *,
    run: RunFn,
) -> None:
    """Create the primary user account on an offline (unbooted) target tree.

    deploy_root is the ostree deploy commit's own root (dirname of its etc/);
    target_root is the mounted disk root under which
    ostree/deploy/default/var/home actually lives — the same mount, just
    referenced above the deploy-commit directory rather than inside it.
    Callers must run ensure_system_accounts again afterward to re-lock
    /etc/shadow permissions once this user's entry exists.
    """
    root = Path(deploy_root)
    etc = root / "etc"

    run(
        ["useradd", "--root", str(root), "-M", "-G", "wheel,video,audio,render",
         "-s", "/bin/bash", username],
        check=True,
    )

    shadow_lines = _read_lines(etc / "shadow", run)
    new_lines = []
    hash_written = False
    for line in shadow_lines:
        if line.startswith(f"{username}:"):
            fields = line.split(":")
            fields[1] = password_hash
            new_lines.append(":".join(fields))
            hash_written = True
        else:
            new_lines.append(line)
    if not hash_written:
        raise RuntimeError(f"User '{username}' not found in shadow after useradd")
    # Plain overwrite, not _write_lines: shadow already exists with whatever
    # permissions useradd/a prior ensure_system_accounts left it at, and
    # callers are required to run ensure_system_accounts again afterward to
    # re-lock it down — this just replaces the content in place.
    content = "\n".join(new_lines) + "\n"
    run(["tee", str(etc / "shadow")], input=content, text=True, stdout=subprocess.DEVNULL, check=True)

    uid, gid = "1000", "1000"
    for line in _read_lines(etc / "passwd", run):
        if line.startswith(f"{username}:"):
            parts = line.split(":")
            uid, gid = parts[2], parts[3]
            break

    var_home = Path(target_root) / "ostree/deploy/default/var/home" / username
    run(["mkdir", "-p", str(var_home)], check=True)
    run(["chown", f"{uid}:{gid}", str(var_home)], check=True)
    run(["chmod", "700", str(var_home)], check=True)

    skel = root / "etc/skel"
    if run(["test", "-d", str(skel)], check=False, capture_output=True).returncode == 0:
        run(["cp", "-rT", str(skel), str(var_home)], check=True)
        run(["chown", "-R", f"{uid}:{gid}", str(var_home)], check=True)

    run(["restorecon", "-RF", str(var_home)], check=False)
    log(f"User '{username}' created (uid={uid})")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 1:
        ensure_system_accounts(args[0], print, run=_default_run)
        return 0
    if len(args) == 5 and args[0] == "create-user":
        _, deploy_root, target_root, username, password_hash = args
        create_installer_user(deploy_root, target_root, username, password_hash, print, run=_default_run)
        return 0
    print(
        "Usage: python3 -m kyth_shared.accounts DEPLOY_ROOT\n"
        "       python3 -m kyth_shared.accounts create-user DEPLOY_ROOT TARGET_ROOT USERNAME PASSWORD_HASH",
        file=sys.stderr,
    )
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
