"""Standard daemon lifecycle and execution class for KythOS daemons."""
from __future__ import annotations

import logging
import os
import signal
import sys
import time
from abc import ABC, abstractmethod
from typing import Any

from kyth_shared.config import load_toml_config


class DaemonRestartError(Exception):
    """Raised when daemon exceeds restart threshold to prevent crash loops."""


class BaseDaemon(ABC):
    """Abstract base class for unifying signals, loops, and configs in daemons.
    
    Includes restart protection to prevent rapid crash loops that could
    exhaust system resources or fill logs.
    """

    def __init__(
        self,
        name: str,
        *,
        config_filename: str | None = None,
        config_section: str | None = None,
        default_config: dict[str, Any] | None = None,
        poll_interval_key: str = "poll_interval",
        default_poll_interval: float = 10.0,
        oneshot: bool = False,
        max_restarts: int = 5,
        restart_window: float = 60.0,
    ) -> None:
        self.name = name
        self.config_filename = config_filename
        self.config_section = config_section
        self.default_config = default_config or {}
        self.poll_interval_key = poll_interval_key
        self.default_poll_interval = default_poll_interval
        self.oneshot = oneshot
        self.max_restarts = max_restarts
        self.restart_window = restart_window

        self.logger = logging.getLogger(name)
        self.config: dict[str, Any] = self.default_config.copy()

        self.running = False
        self.should_poll = True
        self._exit_code = 0
        
        # Restart protection metrics
        self._restart_count = 0
        self._first_restart_time: float | None = None
        self._last_exit_time: float | None = None

    def setup_logging(self, level: int = logging.INFO) -> None:
        """Configure standard logging format on stderr."""
        logging.basicConfig(
            level=level,
            format="%(name)s: %(levelname)s %(message)s",
            stream=sys.stderr,
        )

    def load_config(self) -> None:
        """Load and merge TOML configuration file."""
        if self.config_filename:
            self.config = load_toml_config(
                self.config_filename,
                default_config=self.default_config,
                section_name=self.config_section,
            )
            self.logger.info("Configuration loaded/reloaded.")
        else:
            self.config = self.default_config.copy()

    def handle_sighup(self, signum: int, frame: Any) -> None:
        """Handle configuration reload signal."""
        self.logger.info("SIGHUP received. Reloading configuration...")
        self.load_config()
        self.on_config_reloaded()
        self.wakeup()

    def handle_sigterm(self, signum: int, frame: Any) -> None:
        """Handle termination signals."""
        self.logger.info("Termination signal received. Shutting down...")
        self.running = False
        self.wakeup()

    def on_config_reloaded(self) -> None:
        """Hook for subclasses to handle configuration reloading."""

    def setup_signals(self) -> None:
        """Register signal handlers for SIGHUP, SIGTERM, and SIGINT."""
        signal.signal(signal.SIGHUP, self.handle_sighup)
        signal.signal(signal.SIGTERM, self.handle_sigterm)
        signal.signal(signal.SIGINT, self.handle_sigterm)

    def wakeup(self) -> None:
        """Interrupt current sleeping/polling delay to cycle the loop immediately."""
        self.should_poll = True

    def get_poll_interval(self) -> float:
        """Get the current polling loop interval duration."""
        val = self.config.get(self.poll_interval_key, self.default_poll_interval)
        try:
            return float(val)
        except (ValueError, TypeError):
            return self.default_poll_interval

    @abstractmethod
    def on_start(self) -> None:
        """Hook called exactly once before the main loop starts."""

    @abstractmethod
    def poll(self) -> None:
        """Hook called periodically in the main loop."""

    def on_stop(self) -> None:
        """Hook called exactly once after the main loop exits."""

    def _check_restart_protection(self) -> None:
        """Check if daemon is crash-looping and raise if threshold exceeded.
        
        Prevents rapid restart cycles that could exhaust system resources
        or fill logs. Tracks restarts within a sliding time window.
        """
        now = time.monotonic()
        
        # Reset counter if outside the restart window
        if self._first_restart_time is not None:
            if now - self._first_restart_time > self.restart_window:
                self._restart_count = 0
                self._first_restart_time = None
        
        # Track this restart
        self._restart_count += 1
        if self._first_restart_time is None:
            self._first_restart_time = now
        
        # Check if we've exceeded the threshold
        if self._restart_count > self.max_restarts:
            raise DaemonRestartError(
                f"Daemon {self.name} exceeded max restarts "
                f"({self._restart_count} in {self.restart_window}s). "
                f"Manual intervention required."
            )
        
        self.logger.warning(
            "Daemon %s restart %d/%d within monitoring window",
            self.name, self._restart_count, self.max_restarts
        )

    def run(self) -> int:
        """Start the daemon execution flow. Returns process exit code.
        
        Includes restart protection to prevent crash loops. If the daemon
        crashes too many times within the restart window, it will raise
        DaemonRestartError instead of continuing to restart.
        """
        # Check restart protection at startup (for systemd restart scenarios)
        if self._last_exit_time is not None:
            self._check_restart_protection()
        
        self.setup_logging()
        self.load_config()
        self.setup_signals()

        self.logger.info("Starting %s...", self.name)
        try:
            self.on_start()
        except Exception as exc:
            self.logger.exception("Failed during daemon startup: %s", exc)
            self._last_exit_time = time.monotonic()
            return 1

        self.running = True
        while self.running:
            self.should_poll = False
            try:
                self.poll()
            except Exception as exc:
                self.logger.exception("Exception in poll loop: %s", exc)

            if self.oneshot:
                self.running = False
                break

            poll_interval = self.get_poll_interval()
            steps = int(poll_interval * 2)
            for _ in range(max(1, steps)):
                if not self.running or self.should_poll:
                    break
                time.sleep(0.5)

        # Record exit time for restart protection tracking
        self._last_exit_time = time.monotonic()
        
        try:
            self.on_stop()
        except Exception as exc:
            self.logger.exception("Failed during daemon shutdown: %s", exc)

        self.logger.info("%s stopped.", self.name)
        return self._exit_code
