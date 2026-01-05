"""
Correctness tests for bin packing heuristics.

These tests verify that any discovered heuristic produces valid packings.
"""

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from solution import priority, solve, evaluate_packing


class TestPriorityFunction:
    """Tests for the priority function interface."""

    def test_returns_correct_length(self):
        """Priority must return one score per bin."""
        bins = [50, 30, 20, 80]
        scores = priority(25, bins)
        assert len(scores) == len(bins)

    def test_returns_numeric_values(self):
        """All scores must be numeric."""
        bins = [50, 30, 20]
        scores = priority(15, bins)
        for s in scores:
            assert isinstance(s, (int, float))

    def test_infeasible_bins_have_low_scores(self):
        """Bins that can't fit the item should have very low scores."""
        bins = [50, 10, 30]  # Bin 1 (capacity 10) can't fit item of size 25
        scores = priority(25, bins)

        # Score for infeasible bin should be lower than all feasible bins
        feasible_scores = [scores[0], scores[2]]
        infeasible_score = scores[1]

        assert all(infeasible_score < s for s in feasible_scores)

    def test_handles_empty_bins_list(self):
        """Should handle empty bins list gracefully."""
        scores = priority(25, [])
        assert scores == []

    def test_handles_single_bin(self):
        """Should work with single bin."""
        scores = priority(25, [50])
        assert len(scores) == 1
        assert scores[0] > float('-inf')  # Should be feasible


class TestSolver:
    """Tests for the solve function."""

    def test_packs_all_items(self):
        """All items must be packed."""
        items = [30, 40, 20, 50, 10]
        bins = solve(items, bin_capacity=100)

        packed_items = []
        for bin_contents in bins:
            packed_items.extend(bin_contents)

        assert sorted(packed_items) == sorted(items)

    def test_respects_capacity(self):
        """No bin should exceed capacity."""
        items = [30, 40, 20, 50, 10, 35, 45, 25]
        bins = solve(items, bin_capacity=100)

        for bin_contents in bins:
            assert sum(bin_contents) <= 100

    def test_uses_reasonable_bins(self):
        """Should not use excessively many bins."""
        items = [30, 40, 20, 50, 10]  # Total: 150, needs at least 2 bins
        bins = solve(items, bin_capacity=100)

        # Should use at most one bin per item (worst case)
        assert len(bins) <= len(items)
        # Should use at least ceiling of total/capacity bins
        assert len(bins) >= 2

    def test_handles_exact_fit(self):
        """Items that exactly fill a bin."""
        items = [50, 50, 100, 25, 25, 50]
        bins = solve(items, bin_capacity=100)

        packed = sum(sum(b) for b in bins)
        assert packed == sum(items)

    def test_handles_single_item(self):
        """Single item packing."""
        bins = solve([50], bin_capacity=100)
        assert len(bins) == 1
        assert bins[0] == [50]

    def test_handles_many_small_items(self):
        """Many small items."""
        items = [10] * 20  # 20 items of size 10 = 200 total
        bins = solve(items, bin_capacity=100)

        # Optimal: 2 bins (10 items each)
        # Should use at most 4 bins (reasonable heuristic)
        assert len(bins) <= 4
        assert len(bins) >= 2

    def test_handles_large_items(self):
        """Items close to bin capacity."""
        items = [90, 85, 95, 80]
        bins = solve(items, bin_capacity=100)

        # Each large item needs its own bin
        assert len(bins) == 4

    def test_deterministic(self):
        """Same input should give same output."""
        items = [30, 40, 20, 50, 10]
        bins1 = solve(items, bin_capacity=100)
        bins2 = solve(items, bin_capacity=100)

        assert bins1 == bins2


class TestRandomInstances:
    """Tests on random instances."""

    @pytest.fixture(autouse=True)
    def setup(self):
        random.seed(42)

    def test_uniform_small(self):
        """Uniform distribution, small items."""
        items = [random.randint(1, 30) for _ in range(50)]
        bins = solve(items, bin_capacity=100)

        # Verify correctness
        packed = []
        for b in bins:
            assert sum(b) <= 100
            packed.extend(b)
        assert sorted(packed) == sorted(items)

    def test_uniform_medium(self):
        """Uniform distribution, medium items."""
        items = [random.randint(20, 60) for _ in range(30)]
        bins = solve(items, bin_capacity=100)

        packed = []
        for b in bins:
            assert sum(b) <= 100
            packed.extend(b)
        assert sorted(packed) == sorted(items)

    def test_uniform_large(self):
        """Uniform distribution, large items."""
        items = [random.randint(50, 90) for _ in range(20)]
        bins = solve(items, bin_capacity=100)

        packed = []
        for b in bins:
            assert sum(b) <= 100
            packed.extend(b)
        assert sorted(packed) == sorted(items)

    def test_bimodal(self):
        """Bimodal distribution (small and large items)."""
        small = [random.randint(5, 15) for _ in range(25)]
        large = [random.randint(70, 90) for _ in range(10)]
        items = small + large
        random.shuffle(items)

        bins = solve(items, bin_capacity=100)

        packed = []
        for b in bins:
            assert sum(b) <= 100
            packed.extend(b)
        assert sorted(packed) == sorted(items)

    def test_adversarial(self):
        """Adversarial case: items that don't pack well together."""
        # Classic bad case: items of size 1/2 + epsilon, 1/4 + epsilon, 1/4 + epsilon
        items = [51, 26, 26] * 10  # 30 items
        bins = solve(items, bin_capacity=100)

        packed = []
        for b in bins:
            assert sum(b) <= 100
            packed.extend(b)
        assert sorted(packed) == sorted(items)


class TestEdgeCases:
    """Edge case tests."""

    def test_item_equals_capacity(self):
        """Item exactly equals bin capacity."""
        bins = solve([100, 100, 100], bin_capacity=100)
        assert len(bins) == 3

    def test_all_items_same_size(self):
        """All items same size."""
        items = [25] * 12  # 12 items, 4 per bin optimal
        bins = solve(items, bin_capacity=100)

        assert len(bins) >= 3  # At least 3 bins needed
        for b in bins:
            assert sum(b) <= 100

    def test_item_size_one(self):
        """Smallest possible items."""
        items = [1] * 100
        bins = solve(items, bin_capacity=100)

        # Should fit in 1 bin
        assert len(bins) == 1
        assert sum(bins[0]) == 100

    def test_decreasing_sizes(self):
        """Items in decreasing order (good for First Fit Decreasing)."""
        items = [90, 80, 70, 60, 50, 40, 30, 20, 10]
        bins = solve(items, bin_capacity=100)

        packed = sum(sum(b) for b in bins)
        assert packed == sum(items)

    def test_increasing_sizes(self):
        """Items in increasing order (can be tricky)."""
        items = [10, 20, 30, 40, 50, 60, 70, 80, 90]
        bins = solve(items, bin_capacity=100)

        packed = sum(sum(b) for b in bins)
        assert packed == sum(items)


class TestEvaluation:
    """Tests for evaluation metrics."""

    def test_utilization_calculation(self):
        """Test utilization metric."""
        bins = [[50, 50], [30, 20]]  # First bin full, second 50% full
        items = [50, 50, 30, 20]

        result = evaluate_packing(bins, items, 100)

        assert result["num_bins"] == 2
        assert result["utilization"] == 0.75  # 150 / 200
        assert result["waste"] == 50

    def test_perfect_packing(self):
        """Perfect packing has high utilization."""
        bins = [[50, 50], [50, 50]]  # Both bins full
        items = [50, 50, 50, 50]

        result = evaluate_packing(bins, items, 100)

        assert result["utilization"] == 1.0
        assert result["waste"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
