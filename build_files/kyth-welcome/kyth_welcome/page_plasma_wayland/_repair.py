# __KYTH_GENERATED_IMPORTS__
from ..services.launch import open_settings_module
from ..services.process import run_command


class _RepairMixin:
    def _open_kcm(self, label: str, module: str):
        if open_settings_module(module):
            return
        self._repair_result.set_result("err", f"Could not open {label}.", f"Tried: kcmshell6 {module}, systemsettings {module}")

    @staticmethod
    def _command_details(cmd: list[str], result=None, exc: Exception | None = None) -> str:
        lines = ["Command:", "  " + " ".join(cmd)]
        if exc is not None:
            lines.extend(["", "Error:", str(exc)])
            return "\n".join(lines)
        if result is None:
            return "\n".join(lines)
        lines.extend(["", f"Exit code: {result.returncode}"])
        if result.stdout:
            lines.extend(["", "stdout:", result.stdout.strip()])
        if result.stderr:
            lines.extend(["", "stderr:", result.stderr.strip()])
        return "\n".join(lines)

    def _run_repair_command(self, label: str, success: str, cmd: list[str]):
        self._repair_result.set_running(label, self._command_details(cmd))
        result = run_command(cmd, timeout=20)
        if result is None:
            self._repair_result.set_result("err", f"{label} failed: command failed to start", self._command_details(cmd))
            return
        if result.returncode == 0:
            self._repair_result.set_result("ok", success, self._command_details(cmd, result))
            self.refresh()
        else:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            self._repair_result.set_result("err", f"{label} failed: {detail}", self._command_details(cmd, result))

    def _restart_capture_stack(self):
        self._run_repair_command(
            "Restarting PipeWire and desktop portals",
            "Capture stack restarted. Try screen sharing again.",
            [
                "bash", "-lc",
                "systemctl --user restart pipewire wireplumber xdg-desktop-portal; "
                "if systemctl --user list-unit-files plasma-xdg-desktop-portal-kde.service --no-legend | grep -q '^plasma-xdg-desktop-portal-kde\\.service'; then "
                "systemctl --user restart plasma-xdg-desktop-portal-kde.service; "
                "else systemctl --user restart xdg-desktop-portal-kde.service; fi",
            ],
        )

    def _test_desktop_portal(self):
        self._run_repair_command(
            "Testing the desktop portal",
            "Desktop portal responded.",
            [
                "bash", "-lc",
                "busctl --user call org.freedesktop.portal.Desktop /org/freedesktop/portal/desktop org.freedesktop.DBus.Peer Ping "
                "|| { qdbus_cmd=''; for candidate in qdbus6 qdbus-qt6 qdbus; do command -v \"$candidate\" >/dev/null 2>&1 && qdbus_cmd=\"$candidate\" && break; done; "
                "[ -n \"$qdbus_cmd\" ] && \"$qdbus_cmd\" org.freedesktop.portal.Desktop /org/freedesktop/portal/desktop org.freedesktop.DBus.Peer.Ping; }",
            ],
        )

    def _restart_plasma_shell(self):
        self._run_repair_command(
            "Restarting Plasma Shell",
            "Plasma Shell restart requested.",
            ["bash", "-lc", "kquitapp6 plasmashell; kstart6 plasmashell"],
        )
