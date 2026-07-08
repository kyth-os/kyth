import os
import re
import shlex
import shutil
import subprocess
from datetime import datetime

from ..core_base import (
    _run_command, _command_stdout, _branch_display_name, _current_branch,
    _has_rollback_deployment, _has_staged_update
)
from .hardware import _collect_hardware_probes, HardwareProbe

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
            "System Hub", "err",
            "System Hub executable is missing or not runnable.",
            "\n".join(details),
            "Reinstall /usr/bin/kyth-welcome from the current image or repository checkout.",
        )

    if not launcher_ok or not desktop_uses_launcher or not autostart_uses_launcher:
        return HardwareProbe(
            "System Hub", "warn",
            "System Hub is installed, but the launcher diagnostics wrapper is not fully active.",
            "\n".join(details),
            "Install kyth-welcome-launch and refresh the desktop entry so launch failures are logged.",
        )

    if _system_hub_log_has_self_error(log_tail):
        return HardwareProbe(
            "System Hub", "warn",
            "Recent System Hub launch log contains an error.",
            "\n".join(details),
            "Review the recent launch log included above.",
        )

    return HardwareProbe(
        "System Hub", "ok",
        "System Hub launcher and diagnostics wrapper are installed.",
        "\n".join(details),
    )
 # _system_hub_probe

def _diagnostics_report(probes: list[HardwareProbe]) -> str:
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    kernel = _command_stdout(["uname", "-r"], timeout=5) or "unknown"
    hostname = _command_stdout(["hostnamectl", "--static"], timeout=5) or _command_stdout(["hostname"], timeout=5) or "unknown"
    branch = _branch_display_name(_current_branch())
    staged = "yes" if _has_staged_update() else "no"
    rollback = "yes" if _has_rollback_deployment() else "no"
    fwupd = _run_command(["fwupdmgr", "get-updates"], timeout=20)
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
    checks: list[tuple[str, list[str], int]] = [
        ("Daily-driver smoke check", ["/usr/bin/kyth-smoke-check", "--verbose"], 90),
        ("Post-update confidence", ["/usr/bin/kyth-post-update-check", "--force", "--no-notify"], 45),
        ("NVIDIA status", ["/usr/bin/kyth-nvidia-status"], 30),
        ("Controller readiness", ["/usr/bin/kyth-controller-check"], 30),
        ("Suspend/resume readiness", ["/usr/bin/kyth-resume-check"], 45),
        ("Raw support snapshot", ["/usr/bin/kyth-device-info"], 60),
    ]

    sections = ["", "KythOS Health Command Output", "==========================", ""]
    env = os.environ.copy()
    env.setdefault("SUDO_ASKPASS", "/usr/bin/ksshaskpass")
    for title, cmd, timeout in checks:
        sections.append(f"== {title} ==")
        exe = cmd[0]
        if not os.path.exists(exe) and shutil.which(exe) is None:
            sections.extend([f"missing: {exe}", ""])
            continue
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            output = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
            sections.append(f"command: {' '.join(shlex.quote(part) for part in cmd)}")
            sections.append(f"exit: {r.returncode}")
            if output:
                sections.append(output)
            if err:
                sections.append("")
                sections.append("stderr:")
                sections.append(err)
        except subprocess.TimeoutExpired:
            sections.append(f"timed out after {timeout}s")
        except Exception as exc:
            sections.append(f"failed to run: {exc}")
        sections.append("")
    return "\n".join(sections)
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
