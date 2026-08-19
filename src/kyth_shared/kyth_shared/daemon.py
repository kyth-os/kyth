"""Standard daemon lifecycle and execution class for KythOS daemons."""
from __future__ import annotations

import logging
import signal
import sys
import time
from abc import ABC, abstractmethod
from typing import Any

from kyth_shared.config import load_toml_config


class BaseDaemon(ABC):
    """Abstract base class for unifying signals, loops, and configs in daemons."""

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
    ) -> None:
        self.name = name
        self.config_filename = config_filename
        self.config_section = config_section
        self.default_config = default_config or {}
        self.poll_interval_key = poll_interval_key
        self.default_poll_interval = default_poll_interval
        self.oneshot = oneshot

        self.logger = logging.getLogger(name)
        self.config: dict[str, Any] = self.default_config.copy()

        self.running = False
        self.should_poll = True
        self._exit_code = 0

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

    def run(self) -> int:
        """Start the daemon execution flow. Returns process exit code."""
        self.setup_logging()
        self.load_config()
        self.setup_signals()

        self.logger.info("Starting %s...", self.name)
        try:
            self.on_start()
        except (OSError, RuntimeError) as exc:
            self.logger.exception("Failed during daemon startup: %s", exc)
            return 1

        self.running = True
        while self.running:
            self.should_poll = False
            try:
                self.poll()
            except (OSError, RuntimeError) as exc:
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

        try:
            self.on_stop()
        except (OSError, RuntimeError) as exc:
            self.logger.exception("Failed during daemon shutdown: %s", exc)

        self.logger.info("%s stopped.", self.name)
        return self._exit_code