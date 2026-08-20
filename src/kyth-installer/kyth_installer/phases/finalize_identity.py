"""Installed-system identity and account configuration."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .compat import phase_dependency


def configure_hostname_timezone(etc, state, log, *, format_error) -> None:
    run_command = phase_dependency("run_command")
    as_root = phase_dependency("_as_root")
    hostname_path = str(Path(etc, "hostname"))
    try:
        run_command(
            as_root(["/usr/bin/tee", hostname_path]),
            input=f"{state['hostname']}\n", text=True,
            stdout=subprocess.DEVNULL, check=True,
        )
    except OSError as exc:
        raise OSError(format_error(exc, path=hostname_path)) from exc
    log(f"Hostname : {state['hostname']}")

    localtime_path = str(Path(etc, "localtime"))
    try:
        run_command(
            as_root(["ln", "-snf", f"/usr/share/zoneinfo/{state['timezone']}", localtime_path]),
            check=True,
        )
    except OSError as exc:
        raise OSError(format_error(exc, path=localtime_path)) from exc
    log(f"Timezone : {state['timezone']}")

    locale = state.get("locale", "en_US.UTF-8")
    keymap = state.get("keymap", "us")
    run_command(
        as_root(["/usr/bin/tee", str(Path(etc, "locale.conf"))]),
        input=f"LANG={locale}\n", text=True, stdout=subprocess.DEVNULL, check=True,
    )
    run_command(
        as_root(["/usr/bin/tee", str(Path(etc, "vconsole.conf"))]),
        input=f"KEYMAP={keymap}\n", text=True, stdout=subprocess.DEVNULL, check=True,
    )
    log(f"Locale   : {locale}")
    log(f"Keyboard : {keymap}")


def create_installer_user(
    config_root, deploy_root, username, password_hash, log, progress,
    *, creator, ensure_accounts, format_error,
) -> None:
    run_command = phase_dependency("run_command")
    as_root = phase_dependency("_as_root")
    log(f"Creating user: {username}")
    try:
        creator(
            deploy_root, config_root, username, password_hash, log,
            run=lambda argv, **kw: run_command(as_root(argv), **kw),
        )
        ensure_accounts(deploy_root, log)
        progress(97)
    except OSError as exc:
        log(f"Warning: user creation failed: {format_error(exc)}")
        log("You can create a user after first boot with: sudo useradd -m -G wheel USERNAME")
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
        log(f"Warning: user creation failed: {exc}")
        log("You can create a user after first boot with: sudo useradd -m -G wheel USERNAME")
