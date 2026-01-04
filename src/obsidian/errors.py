"""Error handling infrastructure for Obsidian plugin.

Provides structured error types, retry logic, and graceful degradation.
"""

import functools
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class ErrorSeverity(Enum):
    """Severity levels for errors."""

    FATAL = "fatal"  # Cannot continue, must halt
    RECOVERABLE = "recoverable"  # Can retry or degrade gracefully
    WARNING = "warning"  # Can continue with partial results
    INFO = "info"  # Informational only


class ErrorCategory(Enum):
    """Categories for error classification."""

    EVALUATION = "evaluation"  # Evaluator failures
    MEMORY = "memory"  # Database/storage errors
    CONFIGURATION = "configuration"  # Config loading errors
    HOOK = "hook"  # Hook execution errors
    TIMEOUT = "timeout"  # Timeout errors
    NETWORK = "network"  # Network/subprocess errors
    INTERNAL = "internal"  # Internal logic errors


@dataclass
class ObsidianError(Exception):
    """Base error class for Obsidian."""

    message: str
    category: ErrorCategory
    severity: ErrorSeverity = ErrorSeverity.RECOVERABLE
    details: dict[str, Any] | None = None
    cause: Exception | None = None

    def __str__(self) -> str:
        base = f"[{self.category.value}] {self.message}"
        if self.cause:
            base += f" (caused by: {self.cause})"
        return base


class EvaluatorError(ObsidianError):
    """Error during evaluation."""

    def __init__(
        self,
        evaluator_name: str,
        message: str,
        cause: Exception | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=f"Evaluator '{evaluator_name}': {message}",
            category=ErrorCategory.EVALUATION,
            severity=ErrorSeverity.RECOVERABLE,
            details=details,
            cause=cause,
        )
        self.evaluator_name = evaluator_name


class MemoryError(ObsidianError):
    """Error in memory system."""

    def __init__(
        self,
        operation: str,
        message: str,
        cause: Exception | None = None,
    ):
        super().__init__(
            message=f"Memory operation '{operation}': {message}",
            category=ErrorCategory.MEMORY,
            severity=ErrorSeverity.RECOVERABLE,
            cause=cause,
        )
        self.operation = operation


class ConfigurationError(ObsidianError):
    """Error in configuration."""

    def __init__(
        self,
        message: str,
        config_key: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(
            message=message,
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.FATAL,
            cause=cause,
        )
        self.config_key = config_key


class TimeoutError(ObsidianError):
    """Timeout error."""

    def __init__(
        self,
        operation: str,
        timeout_seconds: float,
        cause: Exception | None = None,
    ):
        super().__init__(
            message=f"Operation '{operation}' timed out after {timeout_seconds}s",
            category=ErrorCategory.TIMEOUT,
            severity=ErrorSeverity.RECOVERABLE,
            cause=cause,
        )
        self.operation = operation
        self.timeout_seconds = timeout_seconds


class HookError(ObsidianError):
    """Error in hook execution."""

    def __init__(
        self,
        hook_name: str,
        message: str,
        cause: Exception | None = None,
    ):
        super().__init__(
            message=f"Hook '{hook_name}': {message}",
            category=ErrorCategory.HOOK,
            severity=ErrorSeverity.RECOVERABLE,
            cause=cause,
        )
        self.hook_name = hook_name


@dataclass
class RetryConfig:
    """Configuration for retry logic."""

    max_attempts: int = 3
    delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 30.0
    retryable_exceptions: tuple = (Exception,)


def with_retry(
    config: RetryConfig | None = None,
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retry logic.

    Args:
        config: Retry configuration
        on_retry: Callback when retry occurs (exception, attempt_number)

    Returns:
        Decorated function with retry logic
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None
            delay = config.delay_seconds

            for attempt in range(1, config.max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt < config.max_attempts:
                        if on_retry:
                            on_retry(e, attempt)

                        time.sleep(delay)
                        delay = min(
                            delay * config.backoff_multiplier,
                            config.max_delay_seconds,
                        )

            # All retries exhausted
            raise last_exception  # type: ignore

        return wrapper

    return decorator


def retry(
    func: Callable[..., T],
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff_multiplier: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
) -> T:
    """
    Execute a function with retry logic.

    Args:
        func: Function to execute
        max_attempts: Maximum number of attempts
        delay_seconds: Initial delay between retries
        backoff_multiplier: Multiply delay by this after each retry
        retryable_exceptions: Tuple of exceptions to retry on
        on_retry: Callback when retry occurs

    Returns:
        Result of the function

    Raises:
        Last exception if all retries fail
    """
    last_exception: Exception | None = None
    delay = delay_seconds

    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except retryable_exceptions as e:
            last_exception = e

            if attempt < max_attempts:
                if on_retry:
                    on_retry(e, attempt)
                time.sleep(delay)
                delay = min(delay * backoff_multiplier, 30.0)

    raise last_exception  # type: ignore


class GracefulDegradation:
    """
    Helper for graceful degradation when operations fail.

    Allows continuing with partial or fallback results.
    """

    def __init__(self, logger: Any = None):
        self._logger = logger
        self._failures: list[ObsidianError] = []

    def try_with_fallback(
        self,
        primary: Callable[[], T],
        fallback: T,
        operation_name: str = "operation",
        log_failure: bool = True,
    ) -> T:
        """
        Try primary operation, return fallback on failure.

        Args:
            primary: Primary operation to try
            fallback: Fallback value if primary fails
            operation_name: Name for logging
            log_failure: Whether to log failures

        Returns:
            Result of primary or fallback
        """
        try:
            return primary()
        except Exception as e:
            error = ObsidianError(
                message=f"Failed: {operation_name}",
                category=ErrorCategory.INTERNAL,
                severity=ErrorSeverity.WARNING,
                cause=e,
            )
            self._failures.append(error)

            if log_failure and self._logger:
                self._logger.warning("degradation", str(error))

            return fallback

    def try_all(
        self,
        operations: list[tuple[str, Callable[[], Any]]],
        continue_on_failure: bool = True,
    ) -> list[tuple[str, Any | None, Exception | None]]:
        """
        Try multiple operations, collecting results and failures.

        Args:
            operations: List of (name, callable) tuples
            continue_on_failure: Continue even if some fail

        Returns:
            List of (name, result, exception) tuples
        """
        results = []

        for name, operation in operations:
            try:
                result = operation()
                results.append((name, result, None))
            except Exception as e:
                if not continue_on_failure:
                    raise
                results.append((name, None, e))
                self._failures.append(
                    ObsidianError(
                        message=f"Operation '{name}' failed",
                        category=ErrorCategory.INTERNAL,
                        cause=e,
                    )
                )

        return results

    @property
    def failures(self) -> list[ObsidianError]:
        """Get list of collected failures."""
        return self._failures

    @property
    def has_failures(self) -> bool:
        """Check if any failures occurred."""
        return len(self._failures) > 0

    def clear_failures(self) -> None:
        """Clear collected failures."""
        self._failures.clear()


def safe_execute(
    func: Callable[[], T],
    fallback: T,
    error_handler: Callable[[Exception], None] | None = None,
) -> T:
    """
    Safely execute a function with fallback.

    Args:
        func: Function to execute
        fallback: Value to return on failure
        error_handler: Optional handler for the exception

    Returns:
        Result or fallback
    """
    try:
        return func()
    except Exception as e:
        if error_handler:
            error_handler(e)
        return fallback
