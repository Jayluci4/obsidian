"""Logging infrastructure for Obsidian plugin."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


# Global logger instance
_logger: logging.Logger | None = None


def setup_logging(
    state_dir: Path,
    level: str = "INFO",
    log_file: str = "obsidian.log",
    max_size_mb: int = 10,
    backup_count: int = 3,
    json_format: bool = False,
) -> logging.Logger:
    """
    Set up logging for Obsidian.

    Args:
        state_dir: Directory to store log files
        level: Log level (DEBUG, INFO, WARN, ERROR)
        log_file: Log file name
        max_size_mb: Max size before rotation
        backup_count: Number of backup files to keep
        json_format: Use JSON format for logs

    Returns:
        Configured logger instance
    """
    global _logger

    if _logger is not None:
        return _logger

    # Create logger
    logger = logging.getLogger("obsidian")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    logger.handlers.clear()

    # Create formatters
    if json_format:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # File handler with rotation
    log_path = state_dir / log_file
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_size_mb * 1024 * 1024,
        backupCount=backup_count,
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Stderr handler for errors only
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    """Get the Obsidian logger instance."""
    global _logger
    if _logger is None:
        # Return a null logger if not initialized
        return logging.getLogger("obsidian.null")
    return _logger


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_data = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        return json.dumps(log_data)


class ObsidianLogger:
    """
    Structured logger for Obsidian events.

    Provides methods for logging specific event types with
    consistent formatting and optional metrics tracking.
    """

    def __init__(self, logger: logging.Logger | None = None):
        self._logger = logger or get_logger()
        self._metrics: dict[str, Any] = {}

    def evaluation(
        self,
        evaluator: str,
        passed: bool,
        score: float,
        duration_ms: float,
        details: dict | None = None,
    ) -> None:
        """Log an evaluation result."""
        status = "PASS" if passed else "FAIL"
        self._logger.info(
            f"Evaluation [{evaluator}] {status}: score={score:.3f}, duration={duration_ms:.0f}ms"
        )
        if details and not passed:
            self._logger.debug(f"Evaluation details: {details}")

    def state_change(
        self,
        component: str,
        old_state: str,
        new_state: str,
        reason: str = "",
    ) -> None:
        """Log a state transition."""
        msg = f"State change [{component}]: {old_state} -> {new_state}"
        if reason:
            msg += f" ({reason})"
        self._logger.info(msg)

    def circuit_breaker(
        self,
        state: str,
        action: str,
        loop_number: int,
        reason: str = "",
    ) -> None:
        """Log circuit breaker events."""
        msg = f"Circuit breaker [{state}]: {action} at loop {loop_number}"
        if reason:
            msg += f" - {reason}"

        if state == "OPEN":
            self._logger.warning(msg)
        else:
            self._logger.info(msg)

    def strategy_change(
        self,
        old_mode: str,
        new_mode: str,
        reward_trend: float,
        is_stuck: bool,
    ) -> None:
        """Log strategy mode changes."""
        stuck_str = " (stuck detected)" if is_stuck else ""
        self._logger.info(
            f"Strategy change: {old_mode} -> {new_mode}, trend={reward_trend:+.3f}{stuck_str}"
        )

    def episode_added(
        self,
        attempt_number: int,
        reward: float,
        metrics: dict[str, float],
    ) -> None:
        """Log new episode added."""
        metrics_str = ", ".join(f"{k}={v:.2f}" for k, v in sorted(metrics.items()))
        self._logger.info(
            f"Episode #{attempt_number}: reward={reward:.3f} [{metrics_str}]"
        )

    def context_budget(
        self,
        tokens_used: int,
        budget: int,
        episodes_included: int,
    ) -> None:
        """Log context budget usage."""
        pct = (tokens_used / budget) * 100 if budget > 0 else 0
        self._logger.info(
            f"Context budget: {tokens_used}/{budget} tokens ({pct:.1f}%), {episodes_included} episodes"
        )

    def error(
        self,
        component: str,
        message: str,
        exception: Exception | None = None,
    ) -> None:
        """Log an error."""
        if exception:
            self._logger.error(f"Error [{component}]: {message}", exc_info=exception)
        else:
            self._logger.error(f"Error [{component}]: {message}")

    def warning(self, component: str, message: str) -> None:
        """Log a warning."""
        self._logger.warning(f"Warning [{component}]: {message}")

    def debug(self, component: str, message: str) -> None:
        """Log debug info."""
        self._logger.debug(f"Debug [{component}]: {message}")

    def hook_start(self, hook_name: str, session_id: str) -> None:
        """Log hook invocation start."""
        self._logger.info(f"Hook [{hook_name}] starting for session {session_id}")

    def hook_end(
        self,
        hook_name: str,
        duration_ms: float,
        result: str,
    ) -> None:
        """Log hook invocation end."""
        self._logger.info(
            f"Hook [{hook_name}] completed in {duration_ms:.0f}ms: {result}"
        )
