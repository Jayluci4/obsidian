"""Tests for error handling infrastructure."""

import pytest
import time
from unittest.mock import Mock, patch

from obsidian.errors import (
    ObsidianError,
    EvaluatorError,
    MemoryError,
    ConfigurationError,
    TimeoutError,
    HookError,
    ErrorSeverity,
    ErrorCategory,
    RetryConfig,
    with_retry,
    retry,
    GracefulDegradation,
    safe_execute,
)


class TestObsidianError:
    """Tests for base ObsidianError."""

    def test_basic_error(self):
        """Should create basic error."""
        error = ObsidianError(
            message="Something failed",
            category=ErrorCategory.INTERNAL,
        )
        assert "Something failed" in str(error)
        assert error.severity == ErrorSeverity.RECOVERABLE

    def test_error_with_cause(self):
        """Should include cause in string."""
        cause = ValueError("original error")
        error = ObsidianError(
            message="Wrapped error",
            category=ErrorCategory.INTERNAL,
            cause=cause,
        )
        assert "original error" in str(error)

    def test_error_severity(self):
        """Should set severity correctly."""
        error = ObsidianError(
            message="Fatal error",
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.FATAL,
        )
        assert error.severity == ErrorSeverity.FATAL


class TestEvaluatorError:
    """Tests for EvaluatorError."""

    def test_evaluator_error(self):
        """Should create evaluator error."""
        error = EvaluatorError(
            evaluator_name="pytest",
            message="Tests failed",
        )
        assert "pytest" in str(error)
        assert error.evaluator_name == "pytest"
        assert error.category == ErrorCategory.EVALUATION


class TestMemoryError:
    """Tests for MemoryError."""

    def test_memory_error(self):
        """Should create memory error."""
        error = MemoryError(
            operation="save_episode",
            message="Database locked",
        )
        assert "save_episode" in str(error)
        assert error.operation == "save_episode"


class TestConfigurationError:
    """Tests for ConfigurationError."""

    def test_configuration_error(self):
        """Should create configuration error with fatal severity."""
        error = ConfigurationError(
            message="Invalid config",
            config_key="max_attempts",
        )
        assert error.severity == ErrorSeverity.FATAL
        assert error.config_key == "max_attempts"


class TestTimeoutError:
    """Tests for TimeoutError."""

    def test_timeout_error(self):
        """Should create timeout error."""
        error = TimeoutError(
            operation="pytest",
            timeout_seconds=120,
        )
        assert "pytest" in str(error)
        assert "120" in str(error)


class TestHookError:
    """Tests for HookError."""

    def test_hook_error(self):
        """Should create hook error."""
        error = HookError(
            hook_name="stop",
            message="Hook failed",
        )
        assert "stop" in str(error)
        assert error.hook_name == "stop"


class TestRetryDecorator:
    """Tests for with_retry decorator."""

    def test_success_first_try(self):
        """Should return result on first success."""
        @with_retry()
        def successful_func():
            return "success"

        assert successful_func() == "success"

    def test_retry_on_failure(self):
        """Should retry on failure."""
        call_count = 0

        @with_retry(RetryConfig(max_attempts=3, delay_seconds=0.01))
        def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success"

        result = failing_then_success()
        assert result == "success"
        assert call_count == 3

    def test_max_retries_exceeded(self):
        """Should raise after max retries."""
        @with_retry(RetryConfig(max_attempts=2, delay_seconds=0.01))
        def always_fails():
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            always_fails()

    def test_on_retry_callback(self):
        """Should call on_retry callback."""
        retry_log = []

        def log_retry(e, attempt):
            retry_log.append((str(e), attempt))

        call_count = 0

        @with_retry(
            RetryConfig(max_attempts=3, delay_seconds=0.01),
            on_retry=log_retry,
        )
        def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"Fail {call_count}")
            return "ok"

        fails_twice()
        assert len(retry_log) == 2
        assert "Fail 1" in retry_log[0][0]


class TestRetryFunction:
    """Tests for retry function."""

    def test_retry_success(self):
        """Should return result on success."""
        result = retry(lambda: "success", max_attempts=1, delay_seconds=0.01)
        assert result == "success"

    def test_retry_with_failures(self):
        """Should retry on failures."""
        attempts = []

        def flaky():
            attempts.append(1)
            if len(attempts) < 2:
                raise ValueError("Temporary")
            return "ok"

        result = retry(flaky, max_attempts=3, delay_seconds=0.01)
        assert result == "ok"
        assert len(attempts) == 2


class TestGracefulDegradation:
    """Tests for GracefulDegradation helper."""

    def test_try_with_fallback_success(self):
        """Should return primary result on success."""
        degradation = GracefulDegradation()
        result = degradation.try_with_fallback(
            primary=lambda: "primary",
            fallback="fallback",
        )
        assert result == "primary"
        assert not degradation.has_failures

    def test_try_with_fallback_failure(self):
        """Should return fallback on failure."""
        degradation = GracefulDegradation()
        result = degradation.try_with_fallback(
            primary=lambda: 1 / 0,  # ZeroDivisionError
            fallback="fallback",
        )
        assert result == "fallback"
        assert degradation.has_failures
        assert len(degradation.failures) == 1

    def test_try_all_partial_success(self):
        """Should continue on partial failures."""
        degradation = GracefulDegradation()

        operations = [
            ("op1", lambda: "result1"),
            ("op2", lambda: 1 / 0),  # Fails
            ("op3", lambda: "result3"),
        ]

        results = degradation.try_all(operations, continue_on_failure=True)

        assert len(results) == 3
        assert results[0] == ("op1", "result1", None)
        assert results[1][0] == "op2"
        assert results[1][1] is None
        assert results[1][2] is not None
        assert results[2] == ("op3", "result3", None)

    def test_clear_failures(self):
        """Should clear collected failures."""
        degradation = GracefulDegradation()
        degradation.try_with_fallback(
            primary=lambda: 1 / 0,
            fallback="fallback",
        )
        assert degradation.has_failures

        degradation.clear_failures()
        assert not degradation.has_failures


class TestSafeExecute:
    """Tests for safe_execute function."""

    def test_safe_execute_success(self):
        """Should return result on success."""
        result = safe_execute(lambda: "success", fallback="fallback")
        assert result == "success"

    def test_safe_execute_failure(self):
        """Should return fallback on failure."""
        result = safe_execute(lambda: 1 / 0, fallback="fallback")
        assert result == "fallback"

    def test_safe_execute_error_handler(self):
        """Should call error handler on failure."""
        errors = []
        result = safe_execute(
            func=lambda: 1 / 0,
            fallback="fallback",
            error_handler=lambda e: errors.append(e),
        )
        assert result == "fallback"
        assert len(errors) == 1
        assert isinstance(errors[0], ZeroDivisionError)
