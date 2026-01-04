"""Tests for context budget management."""

import pytest

from obsidian.icrl.context_budget import (
    ContextBudgetManager,
    BudgetResult,
    estimate_tokens,
    estimate_episode_tokens,
    compress_episode,
    CHARS_PER_TOKEN,
)


class TestEstimateTokens:
    """Tests for token estimation."""

    def test_empty_string(self):
        """Empty string should return 0 tokens."""
        assert estimate_tokens("") == 0

    def test_short_string(self):
        """Short string token estimation."""
        # 8 chars / 4 = 2 tokens
        assert estimate_tokens("12345678") == 2

    def test_longer_string(self):
        """Longer string token estimation."""
        text = "a" * 100
        assert estimate_tokens(text) == 100 // CHARS_PER_TOKEN


class TestEstimateEpisodeTokens:
    """Tests for episode token estimation."""

    def test_minimal_episode(self):
        """Minimal episode should have base tokens."""
        episode = {
            "attempt_number": 1,
            "reward": 0.5,
            "metrics": {},
        }
        tokens = estimate_episode_tokens(episode)
        # Base structure (20) + attempt/reward (10) = 30 minimum
        assert tokens >= 30

    def test_episode_with_summary(self):
        """Episode with action summary should have more tokens."""
        episode = {
            "attempt_number": 1,
            "reward": 0.5,
            "action_summary": "Fixed a bug in the parser module",
            "metrics": {"pytest": 0.9, "coverage": 0.7},
        }
        tokens = estimate_episode_tokens(episode)
        # Should be more than minimal (30 base tokens)
        assert tokens > 35

    def test_episode_with_failures(self):
        """Episode with failures should include failure tokens."""
        episode = {
            "attempt_number": 1,
            "reward": 0.3,
            "action_summary": "Attempted fix",
            "metrics": {"pytest": 0.5},
            "failures": ["Test1 failed", "Test2 failed", "Test3 failed"],
        }
        tokens = estimate_episode_tokens(episode)
        # Should include failure tokens (more than base)
        assert tokens > 40


class TestCompressEpisode:
    """Tests for episode compression."""

    def test_level1_truncates_summary(self):
        """Level 1 should truncate long summaries."""
        episode = {
            "attempt_number": 1,
            "reward": 0.5,
            "action_summary": "x" * 200,
            "metrics": {"pytest": 0.8},
            "failures": ["fail1", "fail2", "fail3", "fail4"],
        }
        compressed = compress_episode(episode, level=1)

        # Summary truncated to 100 chars
        assert len(compressed["action_summary"]) <= 100
        # Only first failure kept
        assert len(compressed.get("failures", [])) <= 1

    def test_level2_removes_failures(self):
        """Level 2 should remove failures."""
        episode = {
            "attempt_number": 1,
            "reward": 0.5,
            "action_summary": "x" * 200,
            "metrics": {"pytest": 0.8},
            "failures": ["fail1", "fail2"],
        }
        compressed = compress_episode(episode, level=2)

        assert len(compressed["action_summary"]) <= 50
        assert "failures" not in compressed

    def test_level3_metrics_only(self):
        """Level 3 should keep only metrics."""
        episode = {
            "attempt_number": 1,
            "reward": 0.5,
            "action_summary": "detailed action summary",
            "metrics": {"pytest": 0.8, "coverage": 0.7},
            "failures": ["fail1"],
        }
        compressed = compress_episode(episode, level=3)

        assert "action_summary" not in compressed
        assert "failures" not in compressed
        assert compressed["metrics"] == episode["metrics"]


class TestContextBudgetManager:
    """Tests for ContextBudgetManager."""

    def test_initialization(self):
        """Budget manager should initialize with defaults."""
        manager = ContextBudgetManager()
        assert manager.max_tokens == 10_000
        assert manager.compression_threshold == 20

    def test_custom_initialization(self):
        """Budget manager should accept custom values."""
        manager = ContextBudgetManager(max_tokens=5000, compression_threshold=10)
        assert manager.max_tokens == 5000
        assert manager.compression_threshold == 10

    def test_allocate_single_episode(self):
        """Should allocate a single episode."""
        manager = ContextBudgetManager(max_tokens=1000)
        episodes = [{
            "attempt_number": 1,
            "reward": 0.5,
            "action_summary": "Test action",
            "metrics": {"pytest": 0.8},
        }]

        allocated, result = manager.allocate_episodes(episodes)

        assert len(allocated) == 1
        assert result.episodes_included == 1
        assert result.tokens_used > 0
        assert not result.budget_exceeded

    def test_allocate_within_budget(self):
        """Should allocate multiple episodes within budget."""
        manager = ContextBudgetManager(max_tokens=2000)
        episodes = [
            {
                "attempt_number": i,
                "reward": 0.5 + i * 0.1,
                "action_summary": f"Action {i}",
                "metrics": {"pytest": 0.8},
            }
            for i in range(5)
        ]

        allocated, result = manager.allocate_episodes(episodes)

        assert result.tokens_used <= 2000
        assert not result.budget_exceeded

    def test_compression_applied_for_old_episodes(self):
        """Should compress old episodes."""
        manager = ContextBudgetManager(
            max_tokens=2000,
            compression_threshold=5,
        )
        episodes = [
            {
                "attempt_number": i,
                "reward": 0.5,
                "action_summary": "x" * 200,
                "metrics": {"pytest": 0.8},
                "failures": ["fail1", "fail2"],
            }
            for i in range(10)
        ]

        allocated, result = manager.allocate_episodes(episodes, current_attempt=20)

        # Old episodes should be compressed
        assert result.compression_applied

    def test_get_adaptive_top_k_early_session(self):
        """Early in session, should include more episodes."""
        manager = ContextBudgetManager(max_tokens=10000)

        k = manager.get_adaptive_top_k(total_episodes=5, base_k=5)
        assert k == 5  # All available

    def test_get_adaptive_top_k_late_session(self):
        """Late in session, should be more selective."""
        manager = ContextBudgetManager(max_tokens=10000)

        k = manager.get_adaptive_top_k(total_episodes=100, base_k=5)
        assert k <= 5  # More selective

    def test_get_usage(self):
        """Should return usage statistics."""
        manager = ContextBudgetManager(max_tokens=1000)
        episodes = [{
            "attempt_number": 1,
            "reward": 0.5,
            "metrics": {},
        }]

        manager.allocate_episodes(episodes)
        usage = manager.get_usage()

        assert "tokens_used" in usage
        assert "budget" in usage
        assert "utilization" in usage
        assert "episodes_included" in usage
        assert "remaining" in usage

    def test_reset(self):
        """Should reset usage tracking."""
        manager = ContextBudgetManager()
        episodes = [{"attempt_number": 1, "reward": 0.5, "metrics": {}}]
        manager.allocate_episodes(episodes)

        manager.reset()
        usage = manager.get_usage()

        assert usage["tokens_used"] == 0
        assert usage["episodes_included"] == 0
