"""Tests for the evaluator module."""

import tempfile
from pathlib import Path

from obsidian.evaluator.base import EvalResult, compute_composite_reward


def test_eval_result_creation():
    """Test EvalResult dataclass."""
    result = EvalResult(
        name="pytest",
        score=0.8,
        passed=True,
        raw_value=(8, 10),
        details={"passed": 8, "failed": 2},
    )

    assert result.name == "pytest"
    assert result.score == 0.8
    assert result.passed is True
    assert not result.failed


def test_eval_result_failed():
    """Test EvalResult with error."""
    result = EvalResult(
        name="pytest",
        score=0.0,
        passed=False,
        error="Command timed out",
    )

    assert result.failed is True
    assert result.error is not None


def test_compute_composite_reward():
    """Test composite reward calculation."""
    results = [
        EvalResult(name="pytest", score=0.8, passed=True),
        EvalResult(name="coverage", score=0.6, passed=True),
    ]

    weights = {"pytest": 0.6, "coverage": 0.4}

    reward = compute_composite_reward(results, weights)

    # 0.8 * 0.6 + 0.6 * 0.4 = 0.48 + 0.24 = 0.72
    assert abs(reward - 0.72) < 0.001


def test_compute_composite_reward_with_error():
    """Test composite reward ignores errored results."""
    results = [
        EvalResult(name="pytest", score=0.8, passed=True),
        EvalResult(name="coverage", score=0.0, passed=False, error="Failed"),
    ]

    weights = {"pytest": 0.6, "coverage": 0.4}

    reward = compute_composite_reward(results, weights)

    # Only pytest counts: 0.8 (weight normalized to 1.0)
    assert abs(reward - 0.8) < 0.001


def test_compute_composite_reward_empty():
    """Test composite reward with no results."""
    reward = compute_composite_reward([], {})
    assert reward == 0.0
