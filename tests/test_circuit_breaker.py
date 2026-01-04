"""Tests for circuit breaker."""

import json
import pytest
import tempfile
from pathlib import Path

from obsidian.strategy.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)


@pytest.fixture
def temp_state_dir():
    """Create a temporary state directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestCircuitState:
    """Tests for CircuitState enum."""

    def test_states_exist(self):
        """All expected states should exist."""
        assert CircuitState.CLOSED.value == "CLOSED"
        assert CircuitState.HALF_OPEN.value == "HALF_OPEN"
        assert CircuitState.OPEN.value == "OPEN"


class TestCircuitBreakerInitialization:
    """Tests for CircuitBreaker initialization."""

    def test_initial_state_closed(self, temp_state_dir):
        """Circuit should start in CLOSED state."""
        cb = CircuitBreaker(temp_state_dir)
        status = cb.get_status()
        assert status["state"] == "CLOSED"

    def test_load_existing_state(self, temp_state_dir):
        """Should load existing state from file."""
        # Create a state file
        state_file = temp_state_dir / "circuit_breaker.json"
        state_file.write_text(json.dumps({
            "state": "HALF_OPEN",
            "consecutive_no_progress": 2,
            "consecutive_same_error": 0,
            "current_loop": 5,
        }))

        cb = CircuitBreaker(temp_state_dir)
        status = cb.get_status()
        assert status["state"] == "HALF_OPEN"


class TestCircuitBreakerStateTransitions:
    """Tests for state transitions."""

    def test_closed_to_half_open_on_no_progress(self, temp_state_dir):
        """Should transition to HALF_OPEN after consecutive no progress."""
        cb = CircuitBreaker(temp_state_dir, no_progress_threshold=3)

        # Record no progress multiple times
        for i in range(1, 3):
            state, _ = cb.record_result(
                loop_number=i,
                has_progress=False,
                has_errors=True,
                error_hash="err1",
                reward_delta=0,
            )

        # Should be HALF_OPEN after 2 no-progress loops
        status = cb.get_status()
        assert status["state"] == "HALF_OPEN"

    def test_half_open_to_open_on_continued_no_progress(self, temp_state_dir):
        """Should transition to OPEN if no recovery in HALF_OPEN."""
        cb = CircuitBreaker(temp_state_dir, no_progress_threshold=3)

        # Get to HALF_OPEN
        for i in range(1, 4):
            cb.record_result(
                loop_number=i,
                has_progress=False,
                has_errors=True,
                error_hash="err1",
                reward_delta=0,
            )

        # Should be OPEN now
        status = cb.get_status()
        assert status["state"] == "OPEN"

    def test_half_open_to_closed_on_progress(self, temp_state_dir):
        """Should recover to CLOSED on progress in HALF_OPEN."""
        cb = CircuitBreaker(temp_state_dir, no_progress_threshold=3)

        # Get to HALF_OPEN
        cb.record_result(1, has_progress=False, has_errors=True, error_hash="e1", reward_delta=0)
        cb.record_result(2, has_progress=False, has_errors=True, error_hash="e1", reward_delta=0)

        assert cb.get_status()["state"] == "HALF_OPEN"

        # Make progress
        state, _ = cb.record_result(
            loop_number=3,
            has_progress=True,
            has_errors=False,
            error_hash="",
            reward_delta=0.1,
        )

        assert state == CircuitState.CLOSED

    def test_open_halts_execution(self, temp_state_dir):
        """Should halt when OPEN."""
        cb = CircuitBreaker(temp_state_dir, no_progress_threshold=2)

        # Force to OPEN
        for i in range(1, 4):
            cb.record_result(i, has_progress=False, has_errors=True, error_hash="e", reward_delta=0)

        should_halt, reason = cb.should_halt()
        assert should_halt
        assert reason  # Should have a reason


class TestCircuitBreakerSameError:
    """Tests for same error detection."""

    def test_same_error_triggers_open(self, temp_state_dir):
        """Should open on repeated same errors."""
        cb = CircuitBreaker(temp_state_dir, same_error_threshold=3)

        # Same error multiple times
        for i in range(1, 5):
            state, _ = cb.record_result(
                loop_number=i,
                has_progress=False,
                has_errors=True,
                error_hash="same_error_hash",
                reward_delta=0,
            )

        assert state == CircuitState.OPEN

    def test_different_errors_dont_trigger(self, temp_state_dir):
        """Different errors should not trigger same-error detection beyond threshold."""
        cb = CircuitBreaker(temp_state_dir, same_error_threshold=3, no_progress_threshold=10)

        # Different errors each time
        for i in range(1, 5):
            cb.record_result(
                loop_number=i,
                has_progress=False,
                has_errors=True,
                error_hash=f"error_{i}",
                reward_delta=0,
            )

        status = cb.get_status()
        # Each new error resets to 1, so should be 1 after last different error
        assert status["consecutive_same_error"] <= 1


class TestCircuitBreakerReset:
    """Tests for circuit breaker reset."""

    def test_reset(self, temp_state_dir):
        """Should reset to CLOSED state."""
        cb = CircuitBreaker(temp_state_dir, no_progress_threshold=2)

        # Get to OPEN
        for i in range(1, 4):
            cb.record_result(i, has_progress=False, has_errors=True, error_hash="e", reward_delta=0)

        assert cb.get_status()["state"] == "OPEN"

        # Reset
        cb.reset()
        status = cb.get_status()
        assert status["state"] == "CLOSED"
        assert status["consecutive_no_progress"] == 0


class TestCircuitBreakerPersistence:
    """Tests for state persistence."""

    def test_state_persists(self, temp_state_dir):
        """State should persist between instances."""
        cb1 = CircuitBreaker(temp_state_dir)
        cb1.record_result(1, has_progress=False, has_errors=True, error_hash="e", reward_delta=0)
        cb1.record_result(2, has_progress=False, has_errors=True, error_hash="e", reward_delta=0)

        # New instance should load persisted state
        cb2 = CircuitBreaker(temp_state_dir)
        status = cb2.get_status()
        assert status["consecutive_no_progress"] == 2
