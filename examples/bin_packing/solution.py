"""
Online Bin Packing Heuristic Discovery

Goal: Discover a priority function that beats First Fit and Best Fit.

The priority function determines which bin to place each item in.
Higher priority = more preferred bin.

Starting point: Best Fit heuristic (baseline to improve upon)
"""

import math


def priority(item: int, bins: list[int]) -> list[float]:
    """
    Compute priority score for placing item in each bin.

    Args:
        item: Size of item to place (1 to bin_capacity)
        bins: List of remaining capacities of open bins

    Returns:
        List of priority scores (one per bin)
        Higher score = more preferred
        Return -inf for bins where item doesn't fit

    Current implementation: FunSearch-Inspired Threshold Heuristic
    Key insight: Sometimes prefer opening new bin over bad fits.
    """
    scores = []

    for remaining in bins:
        if remaining < item:
            scores.append(float('-inf'))
            continue

        gap = remaining - item

        # Exact fit is always best
        if gap == 0:
            scores.append(1e9)

        # "Good" fits: gap is useful (can fit common item sizes)
        elif gap >= 25:
            # Large gap - can likely fit another item
            # Prefer tighter among good fits
            scores.append(1000 - gap)

        # "Acceptable" fits: small gap but not wasteful
        elif gap >= 10:
            scores.append(500 - gap * 2)

        # "Bad" fits: small gaps (1-9) that waste space
        # These are worse than opening a new bin!
        else:
            # Penalize small gaps heavily - they're often unfillable
            scores.append(-1000 + gap * 10)

    return scores


# ============================================================================
# SOLVER (DO NOT MODIFY - this is the skeleton that uses your priority function)
# ============================================================================

def solve(items: list[int], bin_capacity: int = 100) -> list[list[int]]:
    """
    Solve online bin packing using the priority heuristic.

    Args:
        items: List of item sizes to pack (in arrival order)
        bin_capacity: Capacity of each bin

    Returns:
        List of bins, where each bin is a list of item sizes
    """
    bins_remaining = []  # Remaining capacity of each bin
    bins_contents = []   # Contents of each bin

    for item in items:
        if item > bin_capacity:
            raise ValueError(f"Item {item} exceeds bin capacity {bin_capacity}")

        if not bins_remaining:
            # First item - create new bin
            bins_remaining.append(bin_capacity - item)
            bins_contents.append([item])
            continue

        # Get priority scores
        scores = priority(item, bins_remaining)

        # Find best valid bin (highest score where item fits)
        best_bin = -1
        best_score = float('-inf')
        for i, score in enumerate(scores):
            if score > best_score and bins_remaining[i] >= item:
                best_score = score
                best_bin = i

        if best_bin >= 0:
            # Place in existing bin
            bins_remaining[best_bin] -= item
            bins_contents[best_bin].append(item)
        else:
            # Create new bin
            bins_remaining.append(bin_capacity - item)
            bins_contents.append([item])

    return bins_contents


# ============================================================================
# BASELINE IMPLEMENTATIONS (for comparison)
# ============================================================================

def first_fit_priority(item: int, bins: list[int]) -> list[float]:
    """First Fit: prefer earlier bins."""
    return [float('-inf') if r < item else -i for i, r in enumerate(bins)]


def best_fit_priority(item: int, bins: list[int]) -> list[float]:
    """Best Fit: prefer tighter fits."""
    return [float('-inf') if r < item else -(r - item) for r in bins]


def worst_fit_priority(item: int, bins: list[int]) -> list[float]:
    """Worst Fit: prefer looser fits."""
    return [float('-inf') if r < item else (r - item) for r in bins]


# ============================================================================
# EVALUATION HELPERS
# ============================================================================

def l2_lower_bound(items: list[int], bin_capacity: int) -> float:
    """
    Compute L2 lower bound on optimal number of bins.

    This is a theoretical lower bound - no algorithm can do better.
    """
    total_size = sum(items)
    sum_squared = sum(x * x for x in items)

    # L2 bound formula
    bound = (total_size * total_size + sum_squared) / (2 * bin_capacity * bin_capacity)
    return max(bound, total_size / bin_capacity)


def evaluate_packing(bins: list[list[int]], items: list[int], bin_capacity: int) -> dict:
    """Evaluate a bin packing solution."""
    num_bins = len(bins)
    total_items = sum(len(b) for b in bins)
    total_size = sum(sum(b) for b in bins)
    total_capacity = num_bins * bin_capacity
    waste = total_capacity - total_size

    # Efficiency metrics
    utilization = total_size / total_capacity if total_capacity > 0 else 0
    lower_bound = l2_lower_bound(items, bin_capacity)
    excess_ratio = (num_bins - lower_bound) / lower_bound if lower_bound > 0 else 0

    return {
        "num_bins": num_bins,
        "total_items": total_items,
        "utilization": utilization,
        "waste": waste,
        "lower_bound": lower_bound,
        "excess_ratio": excess_ratio,
    }
