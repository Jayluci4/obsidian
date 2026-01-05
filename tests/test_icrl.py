"""Tests for the ICRL module."""

import tempfile
from pathlib import Path

import pytest

from obsidian.icrl import (
    ICRLContextBuilder,
    EXPERIENCE_BUFFER_TEMPLATE,
    META_INSTRUCTION_TEMPLATE,
    format_attempt,
    format_experience_buffer,
    format_meta_instruction,
    EpisodeFilter,
    FilteredEpisode,
    filter_episodes_for_context,
    ContextBudgetManager,
    BudgetResult,
    estimate_tokens,
    estimate_episode_tokens,
    compress_episode,
)
from obsidian.memory import MemoryStore, EpisodicMemory


class TestFormatAttempt:
    """Tests for format_attempt function."""

    def test_basic_formatting(self):
        """Test basic attempt formatting."""
        result = format_attempt(
            attempt_number=1,
            reward=0.75,
            action_summary="Fixed failing tests",
            metrics={"pytest": 0.8, "coverage": 0.7},
        )

        assert '<attempt id="1" reward="0.750">' in result
        assert "Fixed failing tests" in result
        assert "pytest=0.80" in result
        assert "coverage=0.70" in result
        assert "</attempt>" in result

    def test_best_attempt_marker(self):
        """Test best attempt is marked correctly."""
        result = format_attempt(
            attempt_number=3,
            reward=0.9,
            action_summary="Best version",
            metrics={},
            is_best=True,
        )

        assert 'best="true"' in result

    def test_with_failures(self):
        """Test formatting with failure messages."""
        result = format_attempt(
            attempt_number=1,
            reward=0.5,
            action_summary="Work in progress",
            metrics={},
            failures=["test_foo failed", "test_bar failed"],
        )

        assert "Issues:" in result
        assert "test_foo failed" in result
        assert "test_bar failed" in result

    def test_failures_limited_to_three(self):
        """Test that only first 3 failures are included."""
        result = format_attempt(
            attempt_number=1,
            reward=0.3,
            action_summary="Many failures",
            metrics={},
            failures=[f"failure_{i}" for i in range(10)],
        )

        assert "failure_0" in result
        assert "failure_2" in result
        assert "failure_3" not in result


class TestFormatExperienceBuffer:
    """Tests for format_experience_buffer function."""

    def test_empty_attempts(self):
        """Test with empty attempts list."""
        result = format_experience_buffer([])
        assert result == ""

    def test_single_attempt(self):
        """Test with single attempt."""
        attempts = [{
            "attempt_number": 1,
            "reward": 0.6,
            "action_summary": "Initial attempt",
            "metrics": {"pytest": 0.6},
        }]

        result = format_experience_buffer(attempts)

        assert "<experience_buffer>" in result
        assert "</experience_buffer>" in result
        assert '<attempt id="1"' in result

    def test_multiple_attempts(self):
        """Test with multiple attempts."""
        attempts = [
            {"attempt_number": 1, "reward": 0.5, "action_summary": "First", "metrics": {}},
            {"attempt_number": 2, "reward": 0.7, "action_summary": "Second", "metrics": {}},
            {"attempt_number": 3, "reward": 0.9, "action_summary": "Third", "metrics": {}},
        ]

        result = format_experience_buffer(attempts, best_attempt_id=3)

        assert "First" in result
        assert "Second" in result
        assert "Third" in result
        assert 'best="true"' in result


class TestFormatMetaInstruction:
    """Tests for format_meta_instruction function."""

    def test_exploit_mode(self):
        """Test EXPLOIT mode instruction."""
        result = format_meta_instruction(mode="EXPLOIT")

        assert "<meta_instruction>" in result
        assert "Mode: EXPLOIT" in result
        assert "Build on" in result or "Refine" in result

    def test_explore_mode(self):
        """Test EXPLORE mode instruction."""
        result = format_meta_instruction(mode="EXPLORE")

        assert "Mode: EXPLORE" in result
        assert "different" in result.lower()

    def test_autonomous_mode(self):
        """Test AUTONOMOUS mode instruction."""
        result = format_meta_instruction(mode="AUTONOMOUS")

        assert "Mode: AUTONOMOUS" in result

    def test_with_best_attempt(self):
        """Test with best attempt info."""
        best = {"attempt_number": 5, "reward": 0.85}
        result = format_meta_instruction(
            mode="EXPLOIT",
            best_attempt=best,
        )

        assert "#5" in result
        assert "0.85" in result

    def test_with_trend(self):
        """Test with trend information."""
        result = format_meta_instruction(
            mode="AUTONOMOUS",
            trend=0.15,
        )

        assert "+0.15" in result or "0.15" in result

    def test_with_stuck_warning(self):
        """Test with stuck warning."""
        result = format_meta_instruction(
            mode="EXPLORE",
            is_stuck=True,
        )

        assert "WARNING" in result or "stuck" in result.lower()

    def test_with_custom_instruction(self):
        """Test with custom instruction."""
        result = format_meta_instruction(
            mode="AUTONOMOUS",
            custom_instruction="Focus on the login tests.",
        )

        assert "Focus on the login tests" in result


class TestFilteredEpisode:
    """Tests for FilteredEpisode dataclass."""

    def test_creation(self):
        """Test creating FilteredEpisode."""
        fe = FilteredEpisode(
            episode_id="ep_1",
            attempt_number=1,
            reward=0.8,
            metrics={"pytest": 0.9},
            action_summary="Fixed tests",
            failures=[],
            inclusion_reason="top_performer",
            diversity_score=0.7,
            informativeness=0.8,
        )

        assert fe.episode_id == "ep_1"
        assert fe.inclusion_reason == "top_performer"


class TestEpisodeFilter:
    """Tests for EpisodeFilter."""

    def create_episodes(self, rewards):
        """Create test episodes with given rewards."""
        return [
            {
                "attempt_number": i + 1,
                "reward": r,
                "metrics": {"pytest": r},
                "action_summary": f"Attempt {i + 1}",
                "failures": ["test_x failed"] if r < 0.5 else [],
            }
            for i, r in enumerate(rewards)
        ]

    def test_empty_episodes(self):
        """Test filtering empty episode list."""
        f = EpisodeFilter()
        result = f.filter([])
        assert result == []

    def test_selects_top_performers(self):
        """Test that top performers are selected."""
        f = EpisodeFilter(max_episodes=3, top_k_ratio=1.0, failure_ratio=0.0)
        episodes = self.create_episodes([0.3, 0.9, 0.5, 0.8, 0.2])

        result = f.filter(episodes)

        # Should select top 3 (0.9, 0.8, 0.5)
        rewards = [e.reward for e in result]
        assert 0.9 in rewards
        assert 0.8 in rewards

    def test_includes_failures(self):
        """Test that informative failures are included."""
        f = EpisodeFilter(
            max_episodes=5,
            top_k_ratio=0.4,
            failure_ratio=0.4,
            min_reward_for_top=0.6,
            max_reward_for_failure=0.4,
        )
        episodes = self.create_episodes([0.3, 0.9, 0.2, 0.8, 0.1])

        result = f.filter(episodes)

        # Should include some low-reward episodes
        inclusion_reasons = [e.inclusion_reason for e in result]
        assert "informative_failure" in inclusion_reasons

    def test_respects_max_episodes(self):
        """Test max_episodes limit is respected."""
        f = EpisodeFilter(max_episodes=3)
        episodes = self.create_episodes([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])

        result = f.filter(episodes)

        assert len(result) <= 3

    def test_filter_episodes_for_context_convenience(self):
        """Test convenience function."""
        episodes = self.create_episodes([0.3, 0.7, 0.5, 0.9])

        result = filter_episodes_for_context(episodes, max_episodes=3)

        assert len(result) <= 3
        # Returns dicts, not FilteredEpisode
        assert isinstance(result[0], dict)
        assert "inclusion_reason" in result[0]


class TestEstimateTokens:
    """Tests for token estimation functions."""

    def test_estimate_tokens(self):
        """Test basic token estimation."""
        text = "Hello world"  # 11 chars
        tokens = estimate_tokens(text)
        assert tokens == 2  # 11 // 4 = 2

    def test_estimate_episode_tokens(self):
        """Test episode token estimation."""
        episode = {
            "attempt_number": 1,
            "reward": 0.8,
            "action_summary": "Fixed all failing tests",
            "metrics": {"pytest": 0.9, "coverage": 0.8},
            "failures": [],
        }

        tokens = estimate_episode_tokens(episode)

        # Should be positive and reasonable
        assert tokens > 30
        assert tokens < 500

    def test_episode_with_failures_has_more_tokens(self):
        """Test that failures increase token count."""
        base = {
            "attempt_number": 1,
            "reward": 0.5,
            "action_summary": "Test",
            "metrics": {},
            "failures": [],
        }

        with_failures = {
            **base,
            "failures": ["failure 1", "failure 2", "failure 3"],
        }

        tokens_base = estimate_episode_tokens(base)
        tokens_with = estimate_episode_tokens(with_failures)

        assert tokens_with > tokens_base


class TestCompressEpisode:
    """Tests for compress_episode function."""

    def test_level_1_compression(self):
        """Test level 1 compression."""
        episode = {
            "attempt_number": 1,
            "reward": 0.7,
            "action_summary": "A" * 200,  # Long summary
            "metrics": {"test": 0.7},
            "failures": ["f1", "f2", "f3", "f4"],
        }

        compressed = compress_episode(episode, level=1)

        assert len(compressed["action_summary"]) <= 100
        assert len(compressed.get("failures", [])) <= 1

    def test_level_2_compression(self):
        """Test level 2 compression."""
        episode = {
            "attempt_number": 1,
            "reward": 0.7,
            "action_summary": "A" * 200,
            "metrics": {"test": 0.7},
            "failures": ["f1", "f2"],
        }

        compressed = compress_episode(episode, level=2)

        assert len(compressed["action_summary"]) <= 50
        assert "failures" not in compressed

    def test_level_3_compression(self):
        """Test level 3 compression (metrics only)."""
        episode = {
            "attempt_number": 1,
            "reward": 0.7,
            "action_summary": "Long summary text",
            "metrics": {"test": 0.7},
            "failures": ["f1"],
        }

        compressed = compress_episode(episode, level=3)

        assert "action_summary" not in compressed
        assert "failures" not in compressed
        assert compressed["metrics"] == {"test": 0.7}


class TestBudgetResult:
    """Tests for BudgetResult dataclass."""

    def test_creation(self):
        """Test creating BudgetResult."""
        result = BudgetResult(
            episodes_included=5,
            tokens_used=1500,
            budget=10000,
            budget_exceeded=False,
            compression_applied=True,
        )

        assert result.episodes_included == 5
        assert result.budget_exceeded is False


class TestContextBudgetManager:
    """Tests for ContextBudgetManager."""

    def create_episodes(self, n, attempt_start=1):
        """Create test episodes."""
        return [
            {
                "attempt_number": attempt_start + i,
                "reward": 0.5 + (i * 0.05),
                "action_summary": f"Action for attempt {attempt_start + i}",
                "metrics": {"pytest": 0.6},
                "failures": [],
            }
            for i in range(n)
        ]

    def test_allocate_within_budget(self):
        """Test allocation within budget."""
        manager = ContextBudgetManager(max_tokens=5000)
        episodes = self.create_episodes(3)

        allocated, result = manager.allocate_episodes(episodes)

        assert len(allocated) == 3
        assert result.budget_exceeded is False

    def test_allocate_over_budget_compresses(self):
        """Test that over-budget triggers compression."""
        manager = ContextBudgetManager(max_tokens=500, compression_threshold=1)
        episodes = self.create_episodes(20)

        allocated, result = manager.allocate_episodes(episodes, current_attempt=25)

        # Should include fewer episodes or compressed versions
        assert result.compression_applied or len(allocated) < 20

    def test_get_adaptive_top_k(self):
        """Test adaptive top-k calculation."""
        manager = ContextBudgetManager(max_tokens=5000)

        # Early session
        k_early = manager.get_adaptive_top_k(total_episodes=5, base_k=5)
        assert k_early >= 5

        # Mid session
        k_mid = manager.get_adaptive_top_k(total_episodes=25, base_k=5)
        assert k_mid > 0

        # Late session
        k_late = manager.get_adaptive_top_k(total_episodes=100, base_k=5)
        assert k_late <= 5

    def test_get_usage(self):
        """Test usage tracking."""
        manager = ContextBudgetManager(max_tokens=1000)
        episodes = self.create_episodes(2)

        manager.allocate_episodes(episodes)
        usage = manager.get_usage()

        assert "tokens_used" in usage
        assert "utilization" in usage
        assert usage["budget"] == 1000

    def test_reset(self):
        """Test reset clears usage."""
        manager = ContextBudgetManager(max_tokens=1000)
        episodes = self.create_episodes(3)

        manager.allocate_episodes(episodes)
        assert manager._tokens_used > 0

        manager.reset()
        assert manager._tokens_used == 0
        assert manager._episodes_included == 0


class TestICRLContextBuilder:
    """Tests for ICRLContextBuilder."""

    def create_builder(self, tmpdir, session_id="test_session"):
        """Create a context builder in temp directory."""
        state_dir = Path(tmpdir)
        state_dir.mkdir(exist_ok=True)
        return ICRLContextBuilder(
            state_dir,
            session_id,
            top_k=5,
            include_failures=True,
        )

    def seed_episodes(self, builder, rewards):
        """Seed episodes for testing."""
        for i, reward in enumerate(rewards):
            builder._memory.add_episode(
                session_id=builder.session_id,
                attempt_number=i + 1,
                reward=reward,
                metrics={"pytest": reward},
                action_summary=f"Attempt {i + 1} action",
            )
            builder._memory.update_session_state(
                builder.session_id,
                reward=reward,
            )

    def test_empty_context(self):
        """Test builder with no episodes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = self.create_builder(tmpdir)

            context = builder.build_full_context()

            # Should return minimal context for first attempt
            assert "AUTONOMOUS" in context or context != ""
            builder.close()

    def test_get_top_attempts(self):
        """Test retrieving top attempts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = self.create_builder(tmpdir)
            self.seed_episodes(builder, [0.3, 0.9, 0.5, 0.8, 0.6])

            attempts = builder.get_top_attempts()

            assert len(attempts) > 0
            # Top attempt should have high reward
            rewards = [a["reward"] for a in attempts]
            assert max(rewards) == 0.9
            builder.close()

    def test_get_best_attempt(self):
        """Test getting the best attempt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = self.create_builder(tmpdir)
            self.seed_episodes(builder, [0.3, 0.7, 0.5])

            best = builder.get_best_attempt()

            assert best is not None
            assert best["reward"] == 0.7
            builder.close()

    def test_get_session_state(self):
        """Test getting session state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = self.create_builder(tmpdir)
            self.seed_episodes(builder, [0.4, 0.5, 0.6])

            state = builder.get_session_state()

            assert state["attempt_count"] == 3
            assert state["best_reward"] == 0.6
            assert len(state["reward_history"]) == 3
            builder.close()

    def test_compute_trend(self):
        """Test trend computation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = self.create_builder(tmpdir)
            self.seed_episodes(builder, [0.3, 0.4, 0.5, 0.6, 0.7])

            trend = builder.compute_trend(window=5)

            assert trend > 0  # Positive trend
            builder.close()

    def test_is_stuck(self):
        """Test stuck detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = self.create_builder(tmpdir)
            self.seed_episodes(builder, [0.5, 0.5, 0.5, 0.5])

            stuck = builder.is_stuck()

            assert stuck is True
            builder.close()

    def test_determine_mode_exploit(self):
        """Test mode determination for EXPLOIT."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = self.create_builder(tmpdir)
            self.seed_episodes(builder, [0.3, 0.4, 0.5, 0.6, 0.7])

            mode = builder.determine_mode()

            assert mode == "EXPLOIT"
            builder.close()

    def test_determine_mode_explore(self):
        """Test mode determination for EXPLORE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = self.create_builder(tmpdir)
            self.seed_episodes(builder, [0.7, 0.6, 0.5, 0.4, 0.3])

            mode = builder.determine_mode()

            assert mode == "EXPLORE"
            builder.close()

    def test_determine_mode_stuck(self):
        """Test mode determination when stuck."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = self.create_builder(tmpdir)
            self.seed_episodes(builder, [0.5, 0.5, 0.5, 0.5, 0.5])

            mode = builder.determine_mode()

            assert mode == "EXPLORE"
            builder.close()

    def test_build_experience_buffer(self):
        """Test building experience buffer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = self.create_builder(tmpdir)
            self.seed_episodes(builder, [0.4, 0.6, 0.8])

            buffer = builder.build_experience_buffer()

            assert "<experience_buffer>" in buffer
            assert "</experience_buffer>" in buffer
            builder.close()

    def test_build_meta_instruction(self):
        """Test building meta instruction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = self.create_builder(tmpdir)
            self.seed_episodes(builder, [0.3, 0.4, 0.5, 0.6, 0.7])

            instruction = builder.build_meta_instruction()

            assert "<meta_instruction>" in instruction
            assert "EXPLOIT" in instruction
            builder.close()

    def test_build_full_context(self):
        """Test building full ICRL context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = self.create_builder(tmpdir)
            self.seed_episodes(builder, [0.5, 0.6, 0.7])

            context = builder.build_full_context()

            assert "<experience_buffer>" in context
            assert "<meta_instruction>" in context
            builder.close()

    def test_build_session_start_context(self):
        """Test building session start context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = self.create_builder(tmpdir)
            self.seed_episodes(builder, [0.5, 0.6])

            context = builder.build_session_start_context()

            assert "OBSIDIAN LEARNING CONTEXT" in context
            assert "test_session" in context
            assert "Previous attempts: 2" in context
            builder.close()

    def test_session_start_context_empty(self):
        """Test session start context with no history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = self.create_builder(tmpdir)

            context = builder.build_session_start_context()

            assert context == ""  # No history = no context
            builder.close()
