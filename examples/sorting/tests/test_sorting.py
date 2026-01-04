"""Tests for sorting algorithm correctness."""

import random
import sys
from pathlib import Path

# Add solution to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from solution import sort


def test_empty_list():
    """Empty list should return empty list."""
    assert sort([]) == []


def test_single_element():
    """Single element list should return same."""
    assert sort([42]) == [42]


def test_already_sorted():
    """Already sorted list should remain sorted."""
    assert sort([1, 2, 3, 4, 5]) == [1, 2, 3, 4, 5]


def test_reverse_sorted():
    """Reverse sorted list should be sorted."""
    assert sort([5, 4, 3, 2, 1]) == [1, 2, 3, 4, 5]


def test_random_list():
    """Random list should be sorted."""
    arr = [3, 1, 4, 1, 5, 9, 2, 6]
    assert sort(arr) == [1, 1, 2, 3, 4, 5, 6, 9]


def test_negative_numbers():
    """Should handle negative numbers."""
    assert sort([-3, 1, -4, 1, 5]) == [-4, -3, 1, 1, 5]


def test_duplicates():
    """Should handle duplicates correctly."""
    assert sort([3, 3, 3, 1, 1, 2]) == [1, 1, 2, 3, 3, 3]


def test_large_numbers():
    """Should handle large numbers."""
    arr = [1000000, -1000000, 0, 500000]
    assert sort(arr) == [-1000000, 0, 500000, 1000000]


def test_does_not_modify_input():
    """Should not modify the input list."""
    original = [3, 1, 4, 1, 5]
    input_copy = original.copy()
    sort(original)
    assert original == input_copy


def test_random_large():
    """Should correctly sort larger random list."""
    random.seed(42)
    arr = [random.randint(-1000, 1000) for _ in range(100)]
    result = sort(arr)
    assert result == sorted(arr)


def test_all_same():
    """Should handle all same elements."""
    assert sort([7, 7, 7, 7, 7]) == [7, 7, 7, 7, 7]


def test_two_elements():
    """Should handle two element lists."""
    assert sort([2, 1]) == [1, 2]
    assert sort([1, 2]) == [1, 2]
