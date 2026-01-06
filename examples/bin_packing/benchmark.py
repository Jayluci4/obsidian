#!/usr/bin/env python3
"""
Benchmark for Bin Packing Heuristics

Evaluates the discovered heuristic against baselines:
- First Fit
- Best Fit
- Worst Fit

Scoring:
- Based on efficiency compared to L2 lower bound
- Higher score = fewer excess bins
- Score of 1.0 = optimal packing

Output: {"score": float, "metrics": {...}}
"""

import json
import random
import sys
from pathlib import Path
from typing import Callable


def generate_instance(n: int, distribution: str, bin_capacity: int = 100) -> list[int]:
    """Generate a bin packing instance."""
    if distribution == "uniform_small":
        return [random.randint(1, 30) for _ in range(n)]
    elif distribution == "uniform_medium":
        return [random.randint(20, 60) for _ in range(n)]
    elif distribution == "uniform_large":
        return [random.randint(50, 90) for _ in range(n)]
    elif distribution == "uniform_full":
        return [random.randint(1, bin_capacity) for _ in range(n)]
    elif distribution == "bimodal":
        small = [random.randint(5, 20) for _ in range(n // 2)]
        large = [random.randint(60, 90) for _ in range(n - n // 2)]
        items = small + large
        random.shuffle(items)
        return items
    elif distribution == "triplet":
        # Classic hard case: 1/2+e, 1/4+e, 1/4+e
        items = []
        for _ in range(n // 3):
            items.extend([51, 26, 26])
        return items[:n]
    elif distribution == "weibull":
        # Weibull distribution (used in FunSearch paper)
        import math
        items = []
        for _ in range(n):
            # Weibull with shape=2, scale=40
            u = random.random()
            x = 40 * ((-math.log(1 - u)) ** 0.5)
            items.append(max(1, min(bin_capacity, int(x))))
        return items
    else:
        return [random.randint(1, bin_capacity) for _ in range(n)]


def l2_lower_bound(items: list[int], bin_capacity: int) -> float:
    """
    Compute lower bound on optimal bin count.

    Uses multiple bounds and takes the max:
    - L1: Simple volume bound = sum(items) / C
    - L2: Items > C/2 need their own bins, plus volume for rest
    """
    if not items:
        return 0

    total = sum(items)
    C = bin_capacity

    # L1 bound (simple volume bound)
    l1 = total / C

    # L2 bound: count large items (> C/2) that can't share bins
    large_items = [s for s in items if s > C / 2]
    small_items = [s for s in items if s <= C / 2]

    # Large items each need a bin; remaining space can hold small items
    large_count = len(large_items)
    remaining_in_large = sum(C - s for s in large_items)
    small_total = sum(small_items)

    # Small items that don't fit in large item bins
    overflow = max(0, small_total - remaining_in_large)
    l2 = large_count + overflow / C

    return max(l1, l2)


def solve_with_priority(
    items: list[int],
    priority_func: Callable,
    bin_capacity: int = 100
) -> list[list[int]]:
    """Solve bin packing using a priority function."""
    bins_remaining = []
    bins_contents = []

    for item in items:
        if not bins_remaining:
            bins_remaining.append(bin_capacity - item)
            bins_contents.append([item])
            continue

        scores = priority_func(item, bins_remaining)

        best_bin = -1
        best_score = float('-inf')
        for i, score in enumerate(scores):
            if score > best_score and bins_remaining[i] >= item:
                best_score = score
                best_bin = i

        if best_bin >= 0:
            bins_remaining[best_bin] -= item
            bins_contents[best_bin].append(item)
        else:
            bins_remaining.append(bin_capacity - item)
            bins_contents.append([item])

    return bins_contents


# Baseline heuristics
def first_fit_priority(item: int, bins: list[int]) -> list[float]:
    return [float('-inf') if r < item else -i for i, r in enumerate(bins)]


def best_fit_priority(item: int, bins: list[int]) -> list[float]:
    return [float('-inf') if r < item else -(r - item) for r in bins]


def worst_fit_priority(item: int, bins: list[int]) -> list[float]:
    return [float('-inf') if r < item else (r - item) for r in bins]


def evaluate_instance(
    items: list[int],
    priority_func: Callable,
    bin_capacity: int = 100
) -> dict:
    """Evaluate a heuristic on a single instance."""
    bins = solve_with_priority(items, priority_func, bin_capacity)
    num_bins = len(bins)
    lb = l2_lower_bound(items, bin_capacity)

    # Efficiency: lower_bound / num_bins (capped at 1.0)
    # 1.0 = optimal, lower = worse
    efficiency = min(1.0, lb / num_bins) if num_bins > 0 else 0

    # Excess ratio: how many extra bins beyond lower bound
    excess_ratio = (num_bins - lb) / lb if lb > 0 else 0

    return {
        "num_bins": num_bins,
        "lower_bound": lb,
        "excess_ratio": excess_ratio,
        "efficiency": efficiency,
    }


def run_benchmark(priority_func: Callable, seed: int = 42) -> dict:
    """Run full benchmark suite."""
    random.seed(seed)

    test_cases = [
        # (name, n_items, distribution, weight)
        ("uniform_small_50", 50, "uniform_small", 1.0),
        ("uniform_small_100", 100, "uniform_small", 1.0),
        ("uniform_medium_50", 50, "uniform_medium", 1.0),
        ("uniform_medium_100", 100, "uniform_medium", 1.0),
        ("uniform_large_30", 30, "uniform_large", 1.0),
        ("uniform_full_50", 50, "uniform_full", 1.0),
        ("uniform_full_100", 100, "uniform_full", 1.5),
        ("bimodal_50", 50, "bimodal", 1.0),
        ("bimodal_100", 100, "bimodal", 1.0),
        ("triplet_30", 30, "triplet", 1.5),  # Hard case
        ("triplet_60", 60, "triplet", 1.5),
        ("weibull_50", 50, "weibull", 1.0),
        ("weibull_100", 100, "weibull", 1.5),
    ]

    results = {}
    total_weight = 0
    weighted_efficiency = 0

    for name, n, dist, weight in test_cases:
        items = generate_instance(n, dist)
        result = evaluate_instance(items, priority_func)
        results[name] = result
        weighted_efficiency += result["efficiency"] * weight
        total_weight += weight

    avg_efficiency = weighted_efficiency / total_weight if total_weight > 0 else 0

    return {
        "instances": results,
        "average_efficiency": avg_efficiency,
    }


def main():
    # Load solution
    solution_path = Path(__file__).parent / "solution.py"
    if not solution_path.exists():
        print(json.dumps({"score": 0.0, "error": "solution.py not found"}))
        return

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("solution", solution_path)
        solution = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(solution)
        priority_func = solution.priority
    except Exception as e:
        print(json.dumps({"score": 0.0, "error": f"Failed to load solution: {e}"}))
        return

    # Verify basic functionality
    try:
        test_scores = priority_func(25, [50, 30, 20])
        if len(test_scores) != 3:
            raise ValueError("priority must return one score per bin")
    except Exception as e:
        print(json.dumps({"score": 0.0, "error": f"Priority function failed: {e}"}))
        return

    # Run benchmarks
    solution_results = run_benchmark(priority_func)

    # Run baselines for comparison
    first_fit_results = run_benchmark(first_fit_priority)
    best_fit_results = run_benchmark(best_fit_priority)
    worst_fit_results = run_benchmark(worst_fit_priority)

    solution_eff = solution_results["average_efficiency"]
    first_fit_eff = first_fit_results["average_efficiency"]
    best_fit_eff = best_fit_results["average_efficiency"]
    worst_fit_eff = worst_fit_results["average_efficiency"]

    # Score: how much better than baselines
    # 0.85 = First Fit level, 0.90 = Best Fit level, 0.95+ = beating all
    score = solution_eff

    # Determine approach
    if solution_eff > best_fit_eff + 0.02:
        approach = "beats_best_fit"
    elif solution_eff > first_fit_eff + 0.02:
        approach = "beats_first_fit"
    elif solution_eff >= best_fit_eff - 0.01:
        approach = "best_fit_level"
    elif solution_eff >= first_fit_eff - 0.01:
        approach = "first_fit_level"
    else:
        approach = "below_baseline"

    result = {
        "score": score,
        "metrics": {
            "average_efficiency": solution_eff,
            "first_fit_efficiency": first_fit_eff,
            "best_fit_efficiency": best_fit_eff,
            "worst_fit_efficiency": worst_fit_eff,
            "vs_first_fit": solution_eff - first_fit_eff,
            "vs_best_fit": solution_eff - best_fit_eff,
            "approach": approach,
            "instances": len(solution_results["instances"]),
        }
    }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
