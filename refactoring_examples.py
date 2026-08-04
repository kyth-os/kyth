"""Demonstration of refactored code with improved stability and type safety.

This file shows concrete examples of how to apply the recommendations from
CODE_REVIEW_RECOMMENDATIONS.md to actual KythOS code.
"""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

# ============================================================================
# Example 1: Improved Type Safety and Error Handling
# ============================================================================

_logger = logging.getLogger(__name__)


class SizeConfig(TypedDict, total=False):
    """Type-safe configuration for size parsing."""
    default_unit: str
    allow_iec: bool
    max_value: int


def parse_size_bytes(
    size_str: str,
    config: SizeConfig | None = None,
) -> int:
    """Parse size strings with proper error handling and logging.
    
    Args:
        size_str: String like '8.3 GB', '500 MB', or '2 GiB'
        config: Optional configuration for parsing behavior
        
    Returns:
        Size in bytes, or 0 if parsing fails (logged)
        
    Raises:
        ValueError: If size exceeds configured maximum
    """
    cfg: SizeConfig = config or {}
    default_unit = cfg.get('default_unit', '')
    allow_iec = cfg.get('allow_iec', True)
    max_value = cfg.get('max_value', 1024**4)  # Default 1 TB
    
    try:
        parts = size_str.strip().split()
        if not parts:
            _logger.debug("Empty size string")
            return 0
            
        value = float(parts[0])
        unit = parts[1].upper().rstrip("B") if len(parts) > 1 else default_unit
        
        if allow_iec:
            unit = unit.replace("I", "")  # GiB/MiB → GB/MB
            
        mult = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
        multiplier = mult.get(unit, 0)
        
        if multiplier == 0:
            _logger.warning("Unknown size unit: %r in %r", unit, size_str)
            return 0
            
        result = int(value * multiplier)
        
        if result > max_value:
            raise ValueError(f"Size {result} exceeds maximum {max_value}")
            
        return result
        
    except (ValueError, IndexError, KeyError) as exc:
        _logger.debug("Failed to parse size %r: %s", size_str, exc)
        return 0
    except Exception as exc:  # pylint: disable=broad-except
        _logger.exception("Unexpected error parsing size %r", size_str)
        return 0


# ============================================================================
# Example 2: Enhanced Configuration with Validation
# ============================================================================


class AutoUpdateConfig(TypedDict, total=False):
    """Type-safe auto-update configuration."""
    enabled: bool
    rollout_ring: str
    quiet_hours_start: str
    quiet_hours_end: str
    skip_if_metered: bool
    skip_if_gaming: bool
    startup_grace_minutes: int
    bootc_timeout: int


DEFAULT_AUTO_UPDATE_CONFIG: AutoUpdateConfig = {
    "enabled": True,
    "rollout_ring": "follow-image",
    "quiet_hours_start": "02:00",
    "quiet_hours_end": "07:00",
    "skip_if_metered": True,
    "skip_if_gaming": True,
    "startup_grace_minutes": 20,
    "bootc_timeout": 1800,
}

VALID_ROLLOUT_RINGS = frozenset({
    "follow-image", "canary", "testing", "stable"
})


def validate_auto_update_config(config: dict[str, Any]) -> AutoUpdateConfig:
    """Validate and coerce auto-update configuration.
    
    Args:
        config: Raw configuration dictionary
        
    Returns:
        Validated configuration with safe defaults
        
    Raises:
        ValueError: If critical configuration values are invalid
    """
    validated: AutoUpdateConfig = {}
    
    # Boolean fields
    validated["enabled"] = bool(config.get("enabled", True))
    validated["skip_if_metered"] = bool(config.get("skip_if_metered", True))
    validated["skip_if_gaming"] = bool(config.get("skip_if_gaming", True))
    
    # Ring validation
    ring = config.get("rollout_ring", "follow-image")
    if not isinstance(ring, str) or ring not in VALID_ROLLOUT_RINGS:
        raise ValueError(f"Invalid rollout_ring: {ring!r}")
    validated["rollout_ring"] = ring
    
    # Time format validation (HH:MM)
    time_pattern = re.compile(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
    for key in ("quiet_hours_start", "quiet_hours_end"):
        value = config.get(key, DEFAULT_AUTO_UPDATE_CONFIG[key])  # type: ignore[literal-required]
        if not isinstance(value, str) or not time_pattern.match(value):
            raise ValueError(f"Invalid {key}: {value!r}")
        validated[key] = value  # type: ignore[literal-required]
    
    # Numeric fields with bounds checking
    startup_grace = int(config.get("startup_grace_minutes", 20))
    if not 0 <= startup_grace <= 120:
        raise ValueError(f"startup_grace_minutes out of range: {startup_grace}")
    validated["startup_grace_minutes"] = startup_grace
    
    bootc_timeout = int(config.get("bootc_timeout", 1800))
    if not 60 <= bootc_timeout <= 7200:
        raise ValueError(f"bootc_timeout out of range: {bootc_timeout}")
    validated["bootc_timeout"] = bootc_timeout
    
    return validated


# ============================================================================
# Example 3: Enhanced Daemon with Restart Protection
# ============================================================================


@dataclass
class DaemonMetrics:
    """Track daemon health and restart patterns."""
    start_count: int = 0
    crash_count: int = 0
    last_start_time: float = 0.0
    last_crash_time: float = 0.0
    uptime_seconds: float = 0.0
    _rapid_restart_window: float = field(default=60.0, repr=False)
    _max_rapid_restarts: int = field(default=5, repr=False)
    
    def record_start(self, now: float) -> bool:
        """Record a daemon start attempt.
        
        Returns:
            True if start is allowed, False if too many rapid restarts
        """
        self.start_count += 1
        self.last_start_time = now
        
        # Check for rapid restart pattern
        if now - self.last_crash_time < self._rapid_restart_window:
            if self.crash_count >= self._max_rapid_restarts:
                return False
                
        return True
    
    def record_crash(self, now: float) -> None:
        """Record a daemon crash."""
        self.crash_count += 1
        self.last_crash_time = now
        
    def record_uptime(self, duration: float) -> None:
        """Record successful uptime."""
        self.uptime_seconds += duration
        # Reset crash count after sustained uptime
        if duration > 300:  # 5 minutes
            self.crash_count = max(0, self.crash_count - 1)


class ResilientDaemon:
    """Daemon base class with restart protection and metrics."""
    
    def __init__(
        self,
        name: str,
        *,
        max_rapid_restarts: int = 5,
        rapid_restart_window: float = 60.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.name = name
        self.clock = clock or time.monotonic
        self.metrics = DaemonMetrics(
            _rapid_restart_window=rapid_restart_window,
            _max_rapid_restarts=max_rapid_restarts,
        )
        self.logger = logging.getLogger(name)
        self.running = False
        
    def run(self) -> int:
        """Run daemon with restart protection."""
        now = self.clock()
        
        if not self.metrics.record_start(now):
            self.logger.critical(
                "Too many rapid restarts (%d in %.1fs), refusing to start",
                self.metrics.crash_count,
                self.metrics._rapid_restart_window,
            )
            return 1
            
        start_time = now
        
        try:
            self.logger.info("Starting %s (attempt %d)", self.name, self.metrics.start_count)
            self.running = True
            self.on_start()
            
            while self.running:
                try:
                    self.poll()
                except Exception as exc:  # pylint: disable=broad-except
                    self.logger.exception("Exception in poll loop: %s", exc)
                    self.metrics.record_crash(self.clock())
                    raise
                    
        except Exception:
            self.metrics.record_crash(self.clock())
            raise
        finally:
            uptime = self.clock() - start_time
            self.metrics.record_uptime(uptime)
            self.on_stop()
            self.logger.info(
                "%s stopped after %.1fs (total uptime: %.1fs)",
                self.name,
                uptime,
                self.metrics.uptime_seconds,
            )
            
        return 0
    
    def on_start(self) -> None:
        """Override in subclass for initialization."""
        pass
        
    def poll(self) -> None:
        """Override in subclass for main loop logic."""
        pass
        
    def on_stop(self) -> None:
        """Override in subclass for cleanup."""
        pass


# ============================================================================
# Example 4: Structured Logging
# ============================================================================


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        import json  # pylint: disable=import-outside-toplevel
        
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add contextual fields
        if hasattr(record, 'component'):
            log_data['component'] = record.component
        if hasattr(record, 'operation'):
            log_data['operation'] = record.operation
            
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
            log_data['exception_type'] = type(record.exc_info[0]).__name__
            
        return json.dumps(log_data, sort_keys=True)


def setup_structured_logging(
    level: int = logging.INFO,
    include_caller: bool = False,
) -> None:
    """Configure structured JSON logging.
    
    Args:
        level: Minimum log level to capture
        include_caller: Whether to include caller information (adds overhead)
    """
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Remove existing handlers
    logger.handlers.clear()
    
    handler = logging.StreamHandler()
    formatter = JSONFormatter()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    if include_caller:
        # This adds performance overhead but provides better debugging
        logging.getLogger().addFilter(lambda record: setattr(
            record, 'caller', f"{record.pathname}:{record.lineno}"
        ) or True)


# ============================================================================
# Example 5: Circuit Breaker for External Services
# ============================================================================


@dataclass
class CircuitBreakerState:
    """Track circuit breaker state for external service calls."""
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    state: str = "closed"  # closed, open, half-open
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3


class CircuitBreaker:
    """Prevent cascading failures when calling external services."""
    
    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.name = name
        self.clock = clock or time.monotonic
        self.state = CircuitBreakerState(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        self.logger = logging.getLogger(f"circuit.{name}")
        
    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute function with circuit breaker protection.
        
        Raises:
            RuntimeError: If circuit is open
        """
        if not self._allow_request():
            raise RuntimeError(f"Circuit breaker {self.name} is open")
            
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:  # pylint: disable=broad-except
            self._on_failure()
            raise
            
    def _allow_request(self) -> bool:
        """Check if request should be allowed."""
        now = self.clock()
        
        if self.state.state == "closed":
            return True
            
        if self.state.state == "open":
            # Check if recovery timeout has elapsed
            if now - self.state.last_failure_time >= self.state.recovery_timeout:
                self.state.state = "half-open"
                self.state.success_count = 0
                self.logger.info("Circuit %s entering half-open state", self.name)
                return True
            return False
            
        if self.state.state == "half-open":
            # Allow limited calls to test recovery
            return self.state.success_count < self.state.half_open_max_calls
            
        return False
        
    def _on_success(self) -> None:
        """Record successful call."""
        if self.state.state == "half-open":
            self.state.success_count += 1
            if self.state.success_count >= self.state.half_open_max_calls:
                self.state.state = "closed"
                self.state.failure_count = 0
                self.logger.info("Circuit %s closed after successful recovery", self.name)
        else:
            self.state.success_count += 1
            # Reset failure count on sustained success
            if self.state.success_count >= 10:
                self.state.failure_count = 0
                
    def _on_failure(self) -> None:
        """Record failed call."""
        now = self.clock()
        self.state.failure_count += 1
        self.state.last_failure_time = now
        self.state.success_count = 0
        
        if self.state.state == "half-open":
            self.state.state = "open"
            self.logger.warning("Circuit %s opened after half-open failure", self.name)
        elif self.state.failure_count >= self.state.failure_threshold:
            self.state.state = "open"
            self.logger.warning(
                "Circuit %s opened after %d failures",
                self.name,
                self.state.failure_count,
            )


# ============================================================================
# Usage Examples
# ============================================================================

if __name__ == "__main__":
    # Setup structured logging
    setup_structured_logging(level=logging.DEBUG)
    
    # Example: Parse size with validation
    size = parse_size_bytes("8.3 GB")
    print(f"Parsed size: {size} bytes")
    
    # Example: Validate config
    try:
        config = validate_auto_update_config({
            "enabled": True,
            "rollout_ring": "stable",
            "quiet_hours_start": "02:00",
            "quiet_hours_end": "07:00",
        })
        print(f"Validated config: {config}")
    except ValueError as e:
        print(f"Config validation failed: {e}")
    
    # Example: Use circuit breaker
    breaker = CircuitBreaker("github-api", failure_threshold=3)
    try:
        # Simulated API call
        result = breaker.call(lambda: "success")
        print(f"Circuit breaker result: {result}")
    except RuntimeError as e:
        print(f"Circuit breaker blocked call: {e}")
