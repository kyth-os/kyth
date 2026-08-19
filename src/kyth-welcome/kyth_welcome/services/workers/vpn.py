"""Qt worker for openconnect VPN sessions."""
from __future__ import annotations

import os
import subprocess

from kyth_shared.commands import APPLICATION_RUNNER, EnvironmentPolicy, command_spec

from ...qt import Signal
from ..runtime import TrackedThread
from ..vpn import saml_url_from_log_line


class VpnConnectWorker(TrackedThread):
    line = Signal(str)
    done = Signal(int)
    saml_required = Signal(str)

    def __init__(self, cmd: list[str], password: str = ""):
        super().__init__()
        self._cmd = cmd
        self._password = password
        self._proc: subprocess.Popen | None = None

    def run(self) -> None:
        env = os.environ.copy()
        env.setdefault("SUDO_ASKPASS", "/usr/bin/ksshaskpass")
        env.setdefault("SUDO_PROMPT", "Password:")
        stdin_pipe = subprocess.PIPE if self._password else subprocess.DEVNULL
        try:
            self._proc = APPLICATION_RUNNER.spawn(
                command_spec(
                    self._cmd, name="vpn-connect", timeout=None,
                    environment=EnvironmentPolicy.DESKTOP,
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=stdin_pipe,
                text=True,
                bufsize=1,
                env=env,
                cwd="/tmp",  # noqa: S108 — subprocess cwd only, nothing opened here at a predictable path
            )
            if self._password and self._proc.stdin:
                self._proc.stdin.write(self._password + "\n")
                self._proc.stdin.close()
            assert self._proc.stdout
            for ln in self._proc.stdout:
                clean = ln.rstrip()
                self.line.emit(clean)
                url = saml_url_from_log_line(clean)
                if url:
                    self.saml_required.emit(url)
            self._proc.wait()
            self.done.emit(self._proc.returncode)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            import logging

            logging.getLogger(__name__).debug("VpnConnectWorker.run failed: %s", exc, exc_info=True)
            self.line.emit(f"Error: {exc}")
            self.done.emit(1)

    def stop(self) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            import os, signal
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            proc.terminate()
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            import logging

            logging.getLogger(__name__).debug("VpnConnectWorker.stop terminate failed: %s", exc, exc_info=True)
        # ensure dead
        try:
            import time

            time.sleep(0.05)
            if proc.poll() is None:
                proc.kill()
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            import logging

            logging.getLogger(__name__).debug("VpnConnectWorker.stop kill failed: %s", exc, exc_info=True)
        self._proc = None


_VpnConnectWorker = VpnConnectWorker
