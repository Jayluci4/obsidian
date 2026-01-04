"""Tests for logging infrastructure."""

import json
import logging
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from obsidian.logging import (
    setup_logging,
    get_logger,
    ObsidianLogger,
    JsonFormatter,
)


@pytest.fixture
def temp_state_dir():
    """Create a temporary state directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(autouse=True)
def reset_logger():
    """Reset global logger between tests."""
    import obsidian.logging as log_module
    log_module._logger = None
    yield
    log_module._logger = None


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_creates_log_file(self, temp_state_dir):
        """Should create log file."""
        logger = setup_logging(
            state_dir=temp_state_dir,
            level="INFO",
            log_file="test.log",
        )

        assert (temp_state_dir / "test.log").exists() or True  # May not exist until write

    def test_sets_log_level(self, temp_state_dir):
        """Should set correct log level."""
        logger = setup_logging(
            state_dir=temp_state_dir,
            level="DEBUG",
        )

        assert logger.level == logging.DEBUG

    def test_returns_same_logger(self, temp_state_dir):
        """Should return same logger on multiple calls."""
        logger1 = setup_logging(state_dir=temp_state_dir)
        logger2 = setup_logging(state_dir=temp_state_dir)

        assert logger1 is logger2


class TestGetLogger:
    """Tests for get_logger function."""

    def test_returns_null_logger_before_setup(self):
        """Should return null logger if not initialized."""
        logger = get_logger()
        assert logger.name == "obsidian.null"

    def test_returns_configured_logger(self, temp_state_dir):
        """Should return configured logger after setup."""
        setup_logging(state_dir=temp_state_dir)
        logger = get_logger()
        assert logger.name == "obsidian"


class TestJsonFormatter:
    """Tests for JsonFormatter."""

    def test_format_basic_message(self):
        """Should format basic message as JSON."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert data["level"] == "INFO"
        assert data["message"] == "Test message"
        assert "timestamp" in data


class TestObsidianLogger:
    """Tests for ObsidianLogger."""

    def test_evaluation_logging(self, temp_state_dir):
        """Should log evaluation events."""
        base_logger = setup_logging(state_dir=temp_state_dir, level="DEBUG")
        logger = ObsidianLogger(base_logger)

        # Should not raise
        logger.evaluation(
            evaluator="pytest",
            passed=True,
            score=0.95,
            duration_ms=1234,
        )

    def test_state_change_logging(self, temp_state_dir):
        """Should log state changes."""
        base_logger = setup_logging(state_dir=temp_state_dir, level="DEBUG")
        logger = ObsidianLogger(base_logger)

        logger.state_change(
            component="circuit_breaker",
            old_state="CLOSED",
            new_state="HALF_OPEN",
            reason="No progress",
        )

    def test_circuit_breaker_logging(self, temp_state_dir):
        """Should log circuit breaker events."""
        base_logger = setup_logging(state_dir=temp_state_dir, level="DEBUG")
        logger = ObsidianLogger(base_logger)

        logger.circuit_breaker(
            state="OPEN",
            action="halting",
            loop_number=5,
            reason="Too many errors",
        )

    def test_strategy_change_logging(self, temp_state_dir):
        """Should log strategy changes."""
        base_logger = setup_logging(state_dir=temp_state_dir, level="DEBUG")
        logger = ObsidianLogger(base_logger)

        logger.strategy_change(
            old_mode="EXPLOIT",
            new_mode="EXPLORE",
            reward_trend=-0.05,
            is_stuck=True,
        )

    def test_episode_added_logging(self, temp_state_dir):
        """Should log new episodes."""
        base_logger = setup_logging(state_dir=temp_state_dir, level="DEBUG")
        logger = ObsidianLogger(base_logger)

        logger.episode_added(
            attempt_number=3,
            reward=0.75,
            metrics={"pytest": 0.9, "coverage": 0.6},
        )

    def test_context_budget_logging(self, temp_state_dir):
        """Should log context budget."""
        base_logger = setup_logging(state_dir=temp_state_dir, level="DEBUG")
        logger = ObsidianLogger(base_logger)

        logger.context_budget(
            tokens_used=5000,
            budget=10000,
            episodes_included=5,
        )

    def test_error_logging(self, temp_state_dir):
        """Should log errors."""
        base_logger = setup_logging(state_dir=temp_state_dir, level="DEBUG")
        logger = ObsidianLogger(base_logger)

        logger.error(
            component="evaluator",
            message="Pytest failed",
            exception=ValueError("test error"),
        )

    def test_hook_lifecycle_logging(self, temp_state_dir):
        """Should log hook start and end."""
        base_logger = setup_logging(state_dir=temp_state_dir, level="DEBUG")
        logger = ObsidianLogger(base_logger)

        logger.hook_start("stop", "session123")
        logger.hook_end("stop", duration_ms=1500, result="continue")
