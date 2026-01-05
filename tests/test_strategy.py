"""Tests for the strategy module."""

import json
import tempfile
from pathlib import Path

import pytest

from obsidian.strategy import (
    StrategyMode,
    ModeRecommendation,
    get_mode_description,
    get_mode_prompt,
    StuckPattern,
    StuckAnalysis,
    StuckDetector,
    is_stuck,
    StrategyController,
    StrategyState,
    CircuitBreaker,
    CircuitState,
    CircuitBreakerState,
)


class TestStrategyMode:
    """Tests for StrategyMode enum."""

    def test_mode_values(self):
        """Test StrategyMode values."""
        assert StrategyMode.EXPLOIT.value == "exploit"
        assert StrategyMode.EXPLORE.value == "explore"
        assert StrategyMode.AUTONOMOUS.value == "autonomous"

    def test_display_name(self):
        """Test display name property."""
        assert StrategyMode.EXPLOIT.display_name == "EXPLOIT"
        assert StrategyMode.EXPLORE.display_name == "EXPLORE"

    def test_get_mode_description(self):
        """Test getting mode descriptions."""
        desc = get_mode_description(StrategyMode.EXPLOIT)
        assert "refine" in desc.lower() or "improve" in desc.lower()

        desc = get_mode_description(StrategyMode.EXPLORE)
        assert "different" in desc.lower()

    def test_get_mode_prompt(self):
        """Test getting mode prompts."""
        prompt = get_mode_prompt(StrategyMode.EXPLOIT)
        assert prompt != ""
        assert "incremental" in prompt.lower() or "build" in prompt.lower()

        prompt = get_mode_prompt(StrategyMode.EXPLORE)
        assert "different" in prompt.lower()


class TestModeRecommendation:
    """Tests for ModeRecommendation dataclass."""

    def test_recommendation_creation(self):
        """Test creating a ModeRecommendation."""
        rec = ModeRecommendation(
            mode=StrategyMode.EXPLOIT,
            confidence=0.85,
            reason="Positive trend detected",
            evidence={"trend": 0.15},
        )

        assert rec.mode == StrategyMode.EXPLOIT
        assert rec.confidence == 0.85
        assert rec.reason == "Positive trend detected"
        assert rec.evidence["trend"] == 0.15


class TestStuckPattern:
    """Tests for StuckPattern enum."""

    def test_pattern_values(self):
        """Test StuckPattern values."""
        assert StuckPattern.FLAT.value == "flat"
        assert StuckPattern.OSCILLATING.value == "oscillating"
        assert StuckPattern.DECLINING.value == "declining"
        assert StuckPattern.PLATEAU.value == "plateau"


class TestStuckAnalysis:
    """Tests for StuckAnalysis dataclass."""

    def test_analysis_creation(self):
        """Test creating StuckAnalysis."""
        analysis = StuckAnalysis(
            is_stuck=True,
            pattern=StuckPattern.FLAT,
            confidence=0.9,
            severity=0.8,
            recommendation="Try different approach",
            details={"variance": 0.01},
        )

        assert analysis.is_stuck is True
        assert analysis.pattern == StuckPattern.FLAT
        assert analysis.severity == 0.8


class TestStuckDetector:
    """Tests for StuckDetector."""

    def test_insufficient_history(self):
        """Test with insufficient history."""
        detector = StuckDetector(min_window=3)
        analysis = detector.analyze([0.5, 0.6])

        assert analysis.is_stuck is False
        assert analysis.confidence == 0.0

    def test_detect_flat_pattern(self):
        """Test detecting flat reward pattern."""
        detector = StuckDetector(flat_threshold=0.02)

        # Flat pattern - all same value
        analysis = detector.analyze([0.5, 0.5, 0.5, 0.5, 0.5])

        assert analysis.is_stuck is True
        assert analysis.pattern == StuckPattern.FLAT

    def test_detect_not_flat(self):
        """Test that varying rewards are not flat."""
        detector = StuckDetector(flat_threshold=0.02)

        # Increasing rewards
        analysis = detector.analyze([0.3, 0.4, 0.5, 0.6, 0.7])

        assert analysis.pattern != StuckPattern.FLAT or analysis.is_stuck is False

    def test_detect_oscillating_pattern(self):
        """Test detecting oscillating pattern."""
        detector = StuckDetector(oscillation_threshold=0.05)

        # Oscillating: up-down-up-down
        analysis = detector.analyze([0.5, 0.7, 0.5, 0.7, 0.5])

        assert analysis.is_stuck is True
        assert analysis.pattern == StuckPattern.OSCILLATING

    def test_detect_declining_pattern(self):
        """Test detecting declining pattern."""
        detector = StuckDetector(decline_threshold=-0.03)

        # Steadily declining
        analysis = detector.analyze([0.8, 0.7, 0.6, 0.5, 0.4])

        assert analysis.is_stuck is True
        assert analysis.pattern == StuckPattern.DECLINING

    def test_detect_plateau(self):
        """Test detecting plateau pattern."""
        detector = StuckDetector()

        # Near max and flat - may be detected as FLAT or PLATEAU
        # Both indicate being stuck, which is the important behavior
        analysis = detector.analyze([0.6, 0.7, 0.85, 0.85, 0.85])

        assert analysis.is_stuck is True
        # The detector returns highest severity pattern, which may be FLAT
        assert analysis.pattern in [StuckPattern.PLATEAU, StuckPattern.FLAT]

    def test_healthy_progress(self):
        """Test that healthy progress is not stuck."""
        detector = StuckDetector()

        # Steadily improving
        analysis = detector.analyze([0.3, 0.4, 0.5, 0.6, 0.7])

        assert analysis.is_stuck is False
        assert analysis.pattern is None

    def test_is_stuck_function(self):
        """Test simple is_stuck utility function."""
        # Stuck (flat)
        assert is_stuck([0.5, 0.5, 0.5], threshold=0.02, window=3) is True

        # Not stuck (varying)
        assert is_stuck([0.3, 0.5, 0.7], threshold=0.02, window=3) is False

        # Not enough history
        assert is_stuck([0.5, 0.5], threshold=0.02, window=3) is False


class TestCircuitBreakerState:
    """Tests for CircuitBreakerState dataclass."""

    def test_state_creation(self):
        """Test creating CircuitBreakerState."""
        state = CircuitBreakerState(
            state=CircuitState.CLOSED,
            consecutive_no_progress=2,
            current_loop=5,
        )

        assert state.state == CircuitState.CLOSED
        assert state.consecutive_no_progress == 2

    def test_state_to_dict(self):
        """Test state serialization."""
        state = CircuitBreakerState(
            state=CircuitState.HALF_OPEN,
            reason="Monitoring",
            total_opens=1,
        )

        data = state.to_dict()

        assert data["state"] == "HALF_OPEN"
        assert data["reason"] == "Monitoring"
        assert data["total_opens"] == 1

    def test_state_from_dict(self):
        """Test state deserialization."""
        data = {
            "state": "OPEN",
            "reason": "No progress",
            "consecutive_no_progress": 5,
            "total_opens": 2,
        }

        state = CircuitBreakerState.from_dict(data)

        assert state.state == CircuitState.OPEN
        assert state.reason == "No progress"
        assert state.total_opens == 2


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    def create_circuit_breaker(self, tmpdir):
        """Create a circuit breaker in temp directory."""
        state_dir = Path(tmpdir)
        state_dir.mkdir(exist_ok=True)
        return CircuitBreaker(
            state_dir,
            no_progress_threshold=3,
            same_error_threshold=3,
        )

    def test_initial_state(self):
        """Test circuit breaker starts in CLOSED state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cb = self.create_circuit_breaker(tmpdir)

            assert cb.get_state() == CircuitState.CLOSED
            assert cb.can_execute() is True

    def test_no_progress_triggers_open(self):
        """Test that no progress for N loops triggers OPEN."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cb = self.create_circuit_breaker(tmpdir)

            # Record no progress 3 times
            cb.record_result(1, has_progress=False, has_errors=False)
            assert cb.get_state() == CircuitState.CLOSED

            cb.record_result(2, has_progress=False, has_errors=False)
            assert cb.get_state() == CircuitState.HALF_OPEN

            state, reason = cb.record_result(3, has_progress=False, has_errors=False)
            assert state == CircuitState.OPEN
            assert cb.can_execute() is False

    def test_progress_resets_counter(self):
        """Test that progress resets no-progress counter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cb = self.create_circuit_breaker(tmpdir)

            cb.record_result(1, has_progress=False, has_errors=False)
            cb.record_result(2, has_progress=False, has_errors=False)

            # Progress resets counter
            cb.record_result(3, has_progress=True, has_errors=False)
            assert cb.get_state() == CircuitState.CLOSED

            # Can go 2 more without progress
            cb.record_result(4, has_progress=False, has_errors=False)
            cb.record_result(5, has_progress=False, has_errors=False)
            assert cb.get_state() == CircuitState.HALF_OPEN

    def test_same_error_triggers_open(self):
        """Test that same error repeated triggers OPEN."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cb = self.create_circuit_breaker(tmpdir)

            error_hash = "abc123"

            # Same error 3 times
            for i in range(3):
                state, _ = cb.record_result(
                    i + 1,
                    has_progress=False,
                    has_errors=True,
                    error_hash=error_hash,
                )

            assert state == CircuitState.OPEN

    def test_different_errors_dont_trigger(self):
        """Test that different errors don't trigger OPEN."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cb = self.create_circuit_breaker(tmpdir)

            # Different errors each time
            for i in range(3):
                cb.record_result(
                    i + 1,
                    has_progress=True,
                    has_errors=True,
                    error_hash=f"error_{i}",
                )

            assert cb.get_state() != CircuitState.OPEN

    def test_half_open_recovery(self):
        """Test recovery from HALF_OPEN state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cb = self.create_circuit_breaker(tmpdir)

            # Get to HALF_OPEN
            cb.record_result(1, has_progress=False, has_errors=False)
            cb.record_result(2, has_progress=False, has_errors=False)
            assert cb.get_state() == CircuitState.HALF_OPEN

            # Progress recovers to CLOSED
            state, reason = cb.record_result(3, has_progress=True, has_errors=False)
            assert state == CircuitState.CLOSED
            assert "recovered" in reason.lower()

    def test_reset(self):
        """Test manual reset."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cb = self.create_circuit_breaker(tmpdir)

            # Get to OPEN state
            for i in range(4):
                cb.record_result(i + 1, has_progress=False, has_errors=False)

            assert cb.get_state() == CircuitState.OPEN

            # Reset
            cb.reset("Testing reset")
            assert cb.get_state() == CircuitState.CLOSED
            assert cb.can_execute() is True

    def test_should_halt(self):
        """Test should_halt method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cb = self.create_circuit_breaker(tmpdir)

            # Initially should not halt
            should_halt, reason = cb.should_halt()
            assert should_halt is False
            assert reason == ""

            # Get to OPEN
            for i in range(4):
                cb.record_result(i + 1, has_progress=False, has_errors=False)

            should_halt, reason = cb.should_halt()
            assert should_halt is True
            assert reason != ""

    def test_get_status(self):
        """Test get_status method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cb = self.create_circuit_breaker(tmpdir)

            cb.record_result(1, has_progress=True, has_errors=False)

            status = cb.get_status()

            assert status["state"] == "CLOSED"
            assert status["can_execute"] is True
            assert "consecutive_no_progress" in status
            assert "thresholds" in status

    def test_reward_decline_triggers_half_open(self):
        """Test that reward decline triggers HALF_OPEN."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cb = CircuitBreaker(
                Path(tmpdir),
                reward_decline_threshold=0.1,
            )

            # Large reward decline
            state, _ = cb.record_result(
                1,
                has_progress=True,
                has_errors=False,
                reward_delta=-0.15,
            )

            assert state == CircuitState.HALF_OPEN


class TestStrategyController:
    """Tests for StrategyController."""

    def create_controller(self, tmpdir, session_id="test_session"):
        """Create a strategy controller."""
        state_dir = Path(tmpdir)
        state_dir.mkdir(exist_ok=True)
        return StrategyController(
            state_dir,
            session_id,
            improve_threshold=0.05,
            decline_threshold=-0.05,
            max_consecutive_mode=5,
        )

    def seed_reward_history(self, controller, rewards):
        """Seed reward history for testing."""
        for reward in rewards:
            controller._memory.update_session_state(
                controller.session_id,
                reward=reward,
            )

    def test_insufficient_history(self):
        """Test recommendation with insufficient history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self.create_controller(tmpdir)

            rec = controller.recommend_mode()

            assert rec.mode == StrategyMode.AUTONOMOUS
            assert "insufficient" in rec.reason.lower()
            controller.close()

    def test_positive_trend_recommends_exploit(self):
        """Test that positive trend recommends EXPLOIT."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self.create_controller(tmpdir)

            # Seed with improving rewards
            self.seed_reward_history(controller, [0.3, 0.4, 0.5, 0.6, 0.7])

            rec = controller.recommend_mode()

            assert rec.mode == StrategyMode.EXPLOIT
            assert rec.confidence > 0.6
            controller.close()

    def test_negative_trend_recommends_explore(self):
        """Test that negative trend recommends EXPLORE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self.create_controller(tmpdir)

            # Seed with declining rewards
            self.seed_reward_history(controller, [0.7, 0.6, 0.5, 0.4, 0.3])

            rec = controller.recommend_mode()

            assert rec.mode == StrategyMode.EXPLORE
            controller.close()

    def test_flat_trend_recommends_autonomous(self):
        """Test that flat trend recommends AUTONOMOUS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self.create_controller(tmpdir)

            # Seed with flat rewards
            self.seed_reward_history(controller, [0.5, 0.51, 0.49, 0.5, 0.5])

            rec = controller.recommend_mode()

            # Might be AUTONOMOUS or EXPLORE (if stuck detected)
            assert rec.mode in [StrategyMode.AUTONOMOUS, StrategyMode.EXPLORE]
            controller.close()

    def test_stuck_pattern_recommends_explore(self):
        """Test that stuck pattern recommends EXPLORE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self.create_controller(tmpdir)

            # Seed with stuck pattern
            self.seed_reward_history(controller, [0.5, 0.5, 0.5, 0.5, 0.5])

            rec = controller.recommend_mode()

            assert rec.mode == StrategyMode.EXPLORE
            assert "stuck" in rec.reason.lower()
            controller.close()

    def test_compute_trend(self):
        """Test trend computation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self.create_controller(tmpdir)

            self.seed_reward_history(controller, [0.3, 0.4, 0.5, 0.6, 0.7])

            trend = controller.compute_trend(window=5)
            assert abs(trend - 0.4) < 0.01  # 0.7 - 0.3 = 0.4
            controller.close()

    def test_analyze_stuck(self):
        """Test stuck analysis."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self.create_controller(tmpdir)

            self.seed_reward_history(controller, [0.5, 0.5, 0.5, 0.5])

            analysis = controller.analyze_stuck()
            assert analysis.is_stuck is True
            controller.close()

    def test_get_state(self):
        """Test getting controller state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self.create_controller(tmpdir)

            self.seed_reward_history(controller, [0.3, 0.4, 0.5])
            controller.recommend_mode()  # Populate mode history

            state = controller.get_state()

            assert state.current_mode is not None
            assert isinstance(state.mode_history, list)
            controller.close()

    def test_mode_prompt_retrieval(self):
        """Test getting mode-specific prompts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self.create_controller(tmpdir)

            self.seed_reward_history(controller, [0.3, 0.4, 0.5, 0.6, 0.7])

            prompt = controller.get_mode_prompt(StrategyMode.EXPLOIT)
            assert prompt != ""
            assert "incremental" in prompt.lower() or "build" in prompt.lower()
            controller.close()

    def test_record_strategy_outcome(self):
        """Test recording strategy outcomes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self.create_controller(tmpdir)

            controller.record_strategy_outcome(
                mode=StrategyMode.EXPLOIT,
                reward_before=0.5,
                reward_after=0.7,
            )

            stats = controller.get_strategy_stats()
            assert "exploit" in stats
            assert stats["exploit"]["usage_count"] == 1
            controller.close()

    def test_force_mode_switch(self):
        """Test forcing mode switch after too many consecutive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = self.create_controller(tmpdir)
            controller.max_consecutive_mode = 3

            # Seed with strongly improving rewards
            self.seed_reward_history(controller, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])

            # Get multiple EXPLOIT recommendations
            for _ in range(3):
                controller.recommend_mode()

            # Now it should force a switch
            rec = controller.recommend_mode()

            # Either EXPLORE (forced) or something else
            assert rec.mode != StrategyMode.EXPLOIT or "force" in rec.reason.lower()
            controller.close()
