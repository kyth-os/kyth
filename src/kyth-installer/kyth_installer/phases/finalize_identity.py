"""Installed-system identity and account configuration."""

from __future__ import annotations

import subprocess
import json
import shutil
from pathlib import Path

from .compat import phase_dependency
from ..executor import ExecutorCommand, PrivilegedExecutor


def configure_hostname_timezone(etc, state, log, *, format_error) -> None:
    run_command = phase_dependency("run_command")
    as_root = phase_dependency("_as_root")
    if shutil.which("kyth-installer-exec"):
        payload = {
            "target_root": str(Path(etc).parent),
            "hostname": state["hostname"],
            "timezone": state["timezone"],
            "locale": state.get("locale", "en_US.UTF-8"),
            "keymap": state.get("keymap", "us"),
        }
        try:
            run_command(
                as_root(["kyth-installer-exec", "--operation", "configuration-write"]),
                input=json.dumps(payload, separators=(",", ":")),
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=True,
                timeout=30,
            )
        except OSError as exc:
            raise OSError(format_error(exc, path=etc)) from exc
        log(f"Hostname : {state['hostname']}")
        log(f"Timezone : {state['timezone']}")
        log(f"Locale   : {payload['locale']}")
        log(f"Keyboard : {payload['keymap']}")
        return
    executor = PrivilegedExecutor(run_command=run_command, as_root=as_root)
    hostname_path = str(Path(etc, "hostname"))
    try:
        executor.run(
            ExecutorCommand.from_argv(
                ["/usr/bin/tee", hostname_path], "write installed hostname"
            ),
            input=f"{state['hostname']}\n", text=True,
            stdout=subprocess.DEVNULL, check=True,
        )
    except OSError as exc:
        raise OSError(format_error(exc, path=hostname_path)) from exc
    log(f"Hostname : {state['hostname']}")

    localtime_path = str(Path(etc, "localtime"))
    try:
        executor.run(
            ExecutorCommand.from_argv(
                [
                    "ln", "-snf", f"/usr/share/zoneinfo/{state['timezone']}", localtime_path,
                ],
                "set installed timezone",
            ),
            check=True,
        )
    except OSError as exc:
        raise OSError(format_error(exc, path=localtime_path)) from exc
    log(f"Timezone : {state['timezone']}")

    locale = state.get("locale", "en_US.UTF-8")
    keymap = state.get("keymap", "us")
    executor.run(
        ExecutorCommand.from_argv(
            ["/usr/bin/tee", str(Path(etc, "locale.conf"))],
            "write installed locale",
        ),
        input=f"LANG={locale}\n", text=True, stdout=subprocess.DEVNULL, check=True,
    )
    executor.run(
        ExecutorCommand.from_argv(
            ["/usr/bin/tee", str(Path(etc, "vconsole.conf"))],
            "write installed keyboard layout",
        ),
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
    executor = PrivilegedExecutor(run_command=run_command, as_root=as_root)
    log(f"Creating user: {username}")
    try:
        creator(
            deploy_root, config_root, username, password_hash, log,
            run=lambda argv, **kw: executor.run(
                ExecutorCommand.from_argv(argv, "update installed account database"), **kw
            ),
        )
        ensure_accounts(deploy_root, log)
        progress(97)
    except OSError as exc:
        log(f"Warning: user creation failed: {format_error(exc)}")
        log("You can create a user after first boot with: sudo useradd -m -G wheel USERNAME")
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
        log(f"Warning: user creation failed: {exc}")
        log("You can create a user after first boot with: sudo useradd -m -G wheel USERNAME")
