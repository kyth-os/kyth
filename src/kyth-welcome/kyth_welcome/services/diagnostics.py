import os
import re
import shlex
import shutil
import subprocess

from kyth_shared.commands import APPLICATION_RUNNER, command_spec
from kyth_shared.boot_health import read_state as read_boot_health_state

from kyth_welcome.services.hardware.types import HardwareProbe
from kyth_welcome.services.command import run_sync
from datetime import datetime

from .bootc import (
    branch_display_name,
    current_branch,
    has_rollback_deployment,
    has_staged_update,
)
from .process import command_stdout, run_command


def _tail_file(path: str, max_lines: int = 80) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return ""
    return "".join(lines[-max_lines:]).strip()
 # _tail_file

def _system_hub_log_has_self_error(log_tail: str) -> bool:
    if not log_tail:
        return False
    sections = re.split(r"(?m)^==== .+ kyth-welcome launch ====$", log_tail)
    recent = sections[-1] if sections else log_tail
    # External tools opened from System Hub can inherit stderr into the launcher
    # log. Only flag messages that look like the Hub itself failed to start.
    hub_markers = (
        "kyth-welcome launch failed",
        "traceback (most recent call last)",
        'file "/usr/bin/kyth-welcome"',
        "qt.qpa.plugin",
        "could not load the qt platform plugin",
        "segmentation fault",
        "core dumped",
    )
    lowered = recent.lower()
    if any(marker in lowered for marker in hub_markers):
        return True
    return bool(re.search(r"(?m)^(error|failed|aborted):", recent, re.IGNORECASE))
 # _system_hub_log_has_self_error

def _system_hub_probe() -> HardwareProbe:
    app_path = "/usr/bin/kyth-welcome"
    launcher_path = "/usr/bin/kyth-welcome-launch"
    desktop_path = "/usr/share/applications/kyth-welcome.desktop"
    autostart_path = os.path.expanduser("~/.config/autostart/kyth-welcome.desktop")
    cache_home = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    log_path = os.path.join(cache_home, "kyth", "kyth-welcome.log")

    app_ok = os.path.isfile(app_path) and os.access(app_path, os.X_OK)
    launcher_ok = os.path.isfile(launcher_path) and os.access(launcher_path, os.X_OK)
    desktop_text = _tail_file(desktop_path, max_lines=40)
    desktop_uses_launcher = "Exec=/usr/bin/kyth-welcome-launch" in desktop_text
    autostart_text = _tail_file(autostart_path, max_lines=40)
    autostart_uses_launcher = (
        not os.path.exists(autostart_path)
        or "Exec=/usr/bin/kyth-welcome-launch" in autostart_text
    )
    log_tail = _tail_file(log_path)

    details = [
        f"{app_path}: {'executable' if app_ok else 'missing or not executable'}",
        f"{launcher_path}: {'executable' if launcher_ok else 'missing or not executable'}",
        f"{desktop_path}: {'uses launcher' if desktop_uses_launcher else 'missing or points directly at app'}",
        f"{autostart_path}: {'absent/complete' if not os.path.exists(autostart_path) else ('uses launcher' if autostart_uses_launcher else 'points directly at app')}",
        f"{log_path}: {'present' if log_tail else 'not present or empty'}",
    ]
    if log_tail:
        details.extend(["", "Recent launch log:", log_tail])

    if not app_ok:
        return HardwareProbe(
            "Pulse", "err",
            "Pulse executable is missing or not runnable.",
            "\n".join(details),
            "Reinstall /usr/bin/kyth-welcome from the current image or repository checkout.",
        )

    if not launcher_ok or not desktop_uses_launcher or not autostart_uses_launcher:
        return HardwareProbe(
            "Pulse", "warn",
            "Pulse is installed, but the launcher diagnostics wrapper is not fully active.",
            "\n".join(details),
            "Install kyth-welcome-launch and refresh the desktop entry so launch failures are logged.",
        )

    if _system_hub_log_has_self_error(log_tail):
        return HardwareProbe(
            "Pulse", "warn",
            "Recent Pulse launch log contains an error.",
            "\n".join(details),
            "Review the recent launch log included above.",
        )

    return HardwareProbe(
        "Pulse", "ok",
        "Pulse launcher and diagnostics wrapper are installed.",
        "\n".join(details),
    )
 # _system_hub_probe

def _diagnostics_report(probes: list[HardwareProbe]) -> str:
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    kernel = command_stdout(["uname", "-r"], timeout=5) or "unknown"
    hostname = command_stdout(["hostnamectl", "--static"], timeout=5) or command_stdout(["hostname"], timeout=5) or "unknown"
    branch = branch_display_name(current_branch())
    staged = "yes" if has_staged_update() else "no"
    rollback = "yes" if has_rollback_deployment() else "no"
    boot_health = read_boot_health_state()
    # Single-source fwupd via firmware.py helper
    try:
        from kyth_shared.system.firmware import firmware_updates_command
        from kyth_shared.commands import run as _fw_run
        _fw = _fw_run(firmware_updates_command(), capture_output=True, text=True, timeout=20, check=False)
        if _fw is None:
            fwupd_status = "fwupd unavailable"
        elif _fw.returncode == 0:
            fwupd_status = "updates available"
        elif _fw.returncode == 2:
            fwupd_status = "up to date"
        else:
            fwupd_status = f"check failed (exit {_fw.returncode})"
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        fwupd = run_command(["fwupdmgr", "get-updates"], timeout=20)
        if fwupd is None:
            fwupd_status = "fwupd unavailable"
        elif fwupd.returncode == 0:
            fwupd_status = "updates available"
        elif fwupd.returncode == 2:
            fwupd_status = "up to date"
        else:
            fwupd_status = f"check failed (exit {fwupd.returncode})"

    lines = [
        "KythOS Diagnostics Report",
        f"Generated: {timestamp}",
        "",
        "System",
        f"  Hostname:          {hostname}",
        f"  Kernel:            {kernel}",
        f"  Branch:            {branch}",
        f"  Update staged:     {staged}",
        f"  Rollback available:{rollback}",
        f"  Boot health:       {boot_health.status}",
        f"  Failed boots:      {boot_health.failures}",
        f"  Quarantined builds:{len(boot_health.quarantined)}",
        f"  Last recovery:     {boot_health.last_recovered_digest or 'none'}",
        f"  Firmware state:    {fwupd_status}",
        "",
        "Checks",
    ]
    for probe in probes:
        lines.append(f"  {probe.title}: [{probe.status.upper()}] {probe.summary}")
        if probe.action:
            lines.append(f"    Action: {probe.action}")
    lines += ["", "Details"]
    for probe in probes:
        lines.append(f"[{probe.title}]")
        lines.append(probe.details.strip() or "No extra details.")
        if probe.action:
            lines.append(f"Suggested action: {probe.action}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"
 # _diagnostics_report

def _health_command_report() -> str:
    import time
    checks: list[tuple[str, list[str], int]] = [
        ("Daily-driver health model", ["/usr/bin/kyth-smoke-check", "--json"], 90),
        ("Post-update confidence", ["/usr/bin/kyth-post-update-check", "--force", "--no-notify"], 45),
        ("NVIDIA status", ["/usr/bin/kyth-nvidia-status"], 30),
        ("Hardware policy", ["/usr/bin/kyth-hardware-policy", "status"], 30),
        ("Controller readiness", ["/usr/bin/kyth-controller-check"], 30),
        ("Suspend/resume readiness", ["/usr/bin/kyth-resume-check"], 45),
        ("Raw support snapshot", ["/usr/bin/kyth-device-info"], 60),
    ]

    env = os.environ.copy()
    env.setdefault("SUDO_ASKPASS", "/usr/bin/ksshaskpass")

    running_procs = []
    results = {}

    for title, cmd, timeout in checks:
        exe = cmd[0]
        if not os.path.exists(exe) and shutil.which(exe) is None:
            results[title] = {"error": f"missing: {exe}", "cmd": cmd}
            continue
        try:
            p = APPLICATION_RUNNER.spawn(
                command_spec(cmd, name=f"health-{title.lower().replace(' ', '-')}", timeout=None),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            running_procs.append((title, p, cmd, timeout, time.monotonic()))
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
            results[title] = {"error": f"failed to run: {exc}", "cmd": cmd}

    for title, p, cmd, timeout, start_time in running_procs:
        elapsed = time.monotonic() - start_time
        remaining = max(0.1, timeout - elapsed)
        try:
            out, err = p.communicate(timeout=remaining)
            results[title] = {
                "cmd": cmd,
                "exit": p.returncode,
                "stdout": out,
                "stderr": err,
            }
        except subprocess.TimeoutExpired:
            p.kill()
            out, err = p.communicate()
            results[title] = {
                "cmd": cmd,
                "error": f"timed out after {timeout}s",
                "stdout": out,
                "stderr": err,
            }
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
            results[title] = {
                "cmd": cmd,
                "error": f"failed to read: {exc}",
            }

    sections = ["", "KythOS Health Command Output", "==========================", ""]
    for title, cmd, timeout in checks:
        sections.append(f"== {title} ==")
        res = results.get(title)
        if not res:
            continue
        if "error" in res and not res.get("stdout") and not res.get("stderr"):
            sections.extend([res["error"], ""])
            continue
        
        sections.append(f"command: {' '.join(shlex.quote(part) for part in res['cmd'])}")
        if "error" in res:
            sections.append(res["error"])
        else:
            sections.append(f"exit: {res['exit']}")
        
        output = (res.get("stdout") or "").strip()
        err = (res.get("stderr") or "").strip()
        if output:
            sections.append(output)
        if err:
            sections.append("")
            sections.append("stderr:")
            sections.append(err)
        sections.append("")
    text = "\n".join(sections)
    # Scrub at source — all consumers (Copy/Save/Issue) get PII-free text (S13)
    try:
        from kyth_shared.diagnostics_scrub import scrub_logs

        text = scrub_logs(text)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path  # nosec B110 -- best-effort, failure here is non-fatal by design
        pass
    return text
 # _health_command_report

def _health_recommendations(report: str) -> str:
    checks: list[tuple[str, str]] = [
        ("kyth-default-flatpaks.service", "Default game apps are incomplete. Open Repair and click Retry Game Apps."),
        ("Vulkan", "Vulkan reported trouble. Open Hardware and check Graphics; reboot if a GPU driver was just updated."),
        ("PipeWire", "Desktop audio is not fully active. Open Repair and click Restart Audio."),
        ("WirePlumber", "Audio session management is not fully active. Open Repair and click Restart Audio."),
        ("Rollback deployment not visible", "Rollback is not visible yet. Run one OS update, reboot, then verify the previous deployment appears."),
        ("NVIDIA setup has failures", "NVIDIA setup needs attention. Open NVIDIA Drivers or Repair and retry the NVIDIA build."),
        ("NVIDIA setup needs attention", "NVIDIA may need a reboot or driver build. Open NVIDIA Drivers for the exact state."),
        ("Controller readiness has warnings", "Controller support is partially unverified. Open Controllers, pair or plug in a gamepad, then run ujust controller-check."),
        ("resume readiness has warnings", "Suspend/resume has warnings. Test Wi-Fi, Bluetooth, audio, display, and Vulkan after waking."),
        ("not daily-driver ready", "Daily-driver smoke check found a blocker. Review the FAIL lines below first."),
        ("PC drives", "A PC drive needs care. Use Move Files and fully shut down the other system before copying files."),
    ]
    recs: list[str] = []
    lower_report = report.lower()
    for needle, message in checks:
        if needle.lower() in lower_report and message not in recs:
            recs.append(message)

    if not recs:
        return ""

    lines = ["", "Recommended Fixes", "=================", ""]
    lines.extend(f"- {rec}" for rec in recs[:8])
    lines.append("")
    return "\n".join(lines)
 # _health_recommendations


def storage_sense_enabled() -> bool:
    result = run_command(
        ["systemctl", "--user", "is-enabled", "kyth-storage-sense.timer"],
        timeout=5,
    )
    return bool(result and result.stdout.strip() == "enabled")


_storage_sense_enabled = storage_sense_enabled


def storage_sense_set(enable: bool) -> tuple[bool, str]:
    action = "enable" if enable else "disable"
    result = run_command(
        ["systemctl", "--user", action, "--now", "kyth-storage-sense.timer"],
        timeout=15,
    )
    if result is None:
        return False, "systemctl not available"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return False, detail or f"Could not {action} timer"
    return True, ""


def storage_sense_run_now() -> tuple[bool, str]:
    try:
        APPLICATION_RUNNER.spawn(
            command_spec(
                ["systemd-run", "--user", "--collect", "/usr/bin/kyth-storage-sense"],
                name="storage-sense", timeout=None,
            ),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True, ""
    except OSError as exc:
        return False, str(exc)


def collect_security_status() -> list[tuple[str, str, str]]:
    """Security overview rows: (status, area, text)."""
    from kyth_shared import SystemProbe
    rows: list[tuple[str, str, str]] = []

    fw_active = SystemProbe.get_firewall_status() == "active"
    rows.append((
        "ok" if fw_active else "warn", "Firewall",
        "firewalld is running — inbound connections are filtered."
        if fw_active else "firewalld is not running — check Repair if you didn't disable it yourself.",
    ))

    enforce = SystemProbe.get_selinux_status()
    rows.append((
        "ok" if enforce == "Enforcing" else "warn", "Access control",
        "SELinux is enforcing — system files and services are isolated."
        if enforce == "Enforcing" else f"SELinux is {enforce or 'unavailable'} (expected: Enforcing).",
    ))

    sb = SystemProbe.get_secure_boot_status()
    if "enabled" in sb:
        rows.append(("ok", "Secure Boot", "Firmware verifies the boot chain before KythOS starts."))
    elif "disabled" in sb:
        rows.append(("warn", "Secure Boot", "Disabled. Optional — enable in firmware and run 'ujust enroll-secureboot'."))
    else:
        rows.append(("dim", "Secure Boot", "State unknown (no EFI variables — likely a VM or legacy BIOS boot)."))

    rows.append((
        "ok", "App sandboxing",
        "Store apps run as Flatpaks in sandboxes — permissions are reviewable in Flatseal.",
    ))

    staged = has_staged_update()
    rows.append((
        "ok", "Updates",
        "An update is downloaded and staged — it applies on the next restart."
        if staged else "OS updates download automatically in the background and apply on restart.",
    ))

    rows.append((
        "ok" if has_rollback_deployment() else "dim", "Recovery",
        "The previous OS version is kept — one-click rollback from Repair."
        if has_rollback_deployment() else "A rollback point appears automatically after your first update.",
    ))

    rows.append((
        "ok", "Antivirus",
        "No Defender needed: the OS is read-only and cryptographically verified on "
        "every update, and apps are sandboxed. There is nothing to subscribe to.",
    ))
    return rows


_collect_security_status = collect_security_status


def collect_signin_status() -> list[tuple[str, str, str]]:
    """Account and sign-in overview (fingerprint, lock, autologin)."""
    from kyth_shared import SystemProbe
    import getpass

    rows: list[tuple[str, str, str]] = []
    user = getpass.getuser()

    try:
        result = run_sync(
            ["fprintd-list", user], capture_output=True, text=True, timeout=12, check=False,
        )
        detail = (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        result = None
        detail = "fprintd is not installed"
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
        result = None
        detail = str(exc)
    lower = detail.lower()
    if result is not None and result.returncode == 0 and "finger" in lower:
        rows.append(("ok", "Fingerprint", "A fingerprint is enrolled for this account."))
    elif "no devices available" in lower or "no devices" in lower:
        rows.append(("dim", "Fingerprint", "No supported fingerprint reader was detected."))
    elif "no fingerprints" in lower or "not enrolled" in lower:
        rows.append(("warn", "Fingerprint", "Reader detected, but no fingerprint is enrolled yet."))
    else:
        rows.append(("dim", "Fingerprint", f"Fingerprint state unavailable: {detail or 'unknown state'}."))

    autolock_enabled, lock_resume_enabled = SystemProbe.get_screen_lock_status()
    lock_ok = autolock_enabled and lock_resume_enabled
    rows.append((
        "ok" if lock_ok else "warn", "Screen lock",
        "Automatic locking and lock-on-resume are enabled."
        if lock_ok else "Automatic locking or lock-on-resume is disabled; review Screen Lock settings.",
    ))

    autologin_user = SystemProbe.get_autologin_user()
    autologin = autologin_user == user
    rows.append((
        "warn" if autologin else "ok", "Automatic login",
        "Enabled for this account — convenient, but anyone with the PC can enter the desktop."
        if autologin else "Off for this account; a sign-in is required after startup.",
    ))

    wallet_enabled = SystemProbe.get_kwallet_enabled()
    rows.append((
        "ok" if wallet_enabled else "warn", "Credential vault",
        "KWallet is enabled for saved app and network credentials."
        if wallet_enabled else "KWallet is disabled; apps may store credentials less conveniently.",
    ))

    rows.append((
        "ok", "Passkeys",
        "Passkeys are managed by your browser or password manager and protected by its sign-in controls.",
    ))
    return rows


_collect_signin_status = collect_signin_status


def fingerprint_enroll_shell_command() -> str:
    import getpass

    user = shlex.quote(getpass.getuser())
    return (
        f"fprintd-enroll {user}; code=$?; echo; "
        "if [ $code -eq 0 ]; then echo 'Fingerprint enrollment complete.'; "
        "else echo 'Fingerprint enrollment did not complete.'; fi; "
        "read -rp 'Press Enter to close…'"
    )
