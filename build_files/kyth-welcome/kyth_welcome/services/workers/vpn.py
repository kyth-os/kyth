"""Qt worker for openconnect VPN sessions."""
from __future__ import annotations

import os
import subprocess

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
            self._proc = subprocess.Popen(
                self._cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=stdin_pipe,
                text=True,
                bufsize=1,
                env=env,
                cwd="/tmp",
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
        except Exception as exc:
            self.line.emit(f"Error: {exc}")
            self.done.emit(1)

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


_VpnConnectWorker = VpnConnectWorker
