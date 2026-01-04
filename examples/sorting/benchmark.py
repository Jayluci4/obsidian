#!/usr/bin/env python3
"""
Benchmark for sorting algorithms.

Measures:
- Correctness on test cases
- Number of comparisons (via instrumented wrapper)
- Runtime performance
- Memory usage

Outputs JSON with score and details.
"""

import json
import random
import sys
import time
from pathlib import Path


class ComparisonCounter:
    """Wrapper to count comparisons."""

    def __init__(self, value):
        self.value = value
        self.comparisons = 0

    def __lt__(self, other):
        ComparisonCounter.total_comparisons += 1
        if isinstance(other, ComparisonCounter):
            return self.value < other.value
        return self.value < other

    def __le__(self, other):
        ComparisonCounter.total_comparisons += 1
        if isinstance(other, ComparisonCounter):
            return self.value <= other.value
        return self.value <= other

    def __gt__(self, other):
        ComparisonCounter.total_comparisons += 1
        if isinstance(other, ComparisonCounter):
            return self.value > other.value
        return self.value > other

    def __ge__(self, other):
        ComparisonCounter.total_comparisons += 1
        if isinstance(other, ComparisonCounter):
            return self.value >= other.value
        return self.value >= other

    def __eq__(self, other):
        ComparisonCounter.total_comparisons += 1
        if isinstance(other, ComparisonCounter):
            return self.value == other.value
        return self.value == other

    def __repr__(self):
        return str(self.value)

    total_comparisons = 0


def count_comparisons(sort_func, arr):
    """Run sort and count comparisons."""
    ComparisonCounter.total_comparisons = 0

    # Wrap values
    wrapped = [ComparisonCounter(x) for x in arr]

    # Sort
    result = sort_func(wrapped)

    # Unwrap
    if result:
        unwrapped = [x.value if isinstance(x, ComparisonCounter) else x for x in result]
    else:
        unwrapped = []

    return unwrapped, ComparisonCounter.total_comparisons


def theoretical_minimum(n):
    """Theoretical minimum comparisons for comparison-based sort: n*log2(n)."""
    if n <= 1:
        return 0
    import math
    return n * math.log2(n)


def run_benchmark(solution_path):
    """Run the benchmark."""
    # Import solution
    sys.path.insert(0, str(Path(solution_path).parent))

    try:
        # Clear any cached import
        if "solution" in sys.modules:
            del sys.modules["solution"]

        from solution import sort
    except ImportError as e:
        return {
            "score": 0.0,
            "error": f"Import error: {e}",
            "passed": False,
        }
    except Exception as e:
        return {
            "score": 0.0,
            "error": f"Error loading solution: {e}",
            "passed": False,
        }

    # Test cases with expected comparison counts
    test_cases = [
        # (input, name, weight)
        ([3, 1, 4, 1, 5, 9, 2, 6], "small_random", 0.2),
        (list(range(100)), "sorted_100", 0.1),
        (list(range(100, 0, -1)), "reverse_100", 0.2),
        ([random.randint(0, 1000) for _ in range(100)], "random_100", 0.3),
        ([random.randint(0, 10000) for _ in range(500)], "random_500", 0.2),
    ]

    random.seed(42)  # Reproducible

    results = []
    total_score = 0.0
    total_comparisons = 0
    total_theoretical = 0

    for arr, name, weight in test_cases:
        try:
            start_time = time.time()
            sorted_arr, comparisons = count_comparisons(sort, arr.copy())
            elapsed = time.time() - start_time

            # Check correctness
            expected = sorted(arr)
            correct = sorted_arr == expected

            if not correct:
                results.append({
                    "name": name,
                    "passed": False,
                    "error": "Incorrect output",
                })
                continue

            # Calculate efficiency score
            n = len(arr)
            theoretical = theoretical_minimum(n)
            total_theoretical += theoretical
            total_comparisons += comparisons

            # Score: ratio of theoretical to actual (capped at 1.0)
            if comparisons > 0:
                efficiency = min(1.0, theoretical / comparisons)
            else:
                efficiency = 1.0

            weighted_score = efficiency * weight
            total_score += weighted_score

            results.append({
                "name": name,
                "passed": True,
                "comparisons": comparisons,
                "theoretical": round(theoretical, 1),
                "efficiency": round(efficiency, 4),
                "time_ms": round(elapsed * 1000, 2),
                "weighted_score": round(weighted_score, 4),
            })

        except Exception as e:
            results.append({
                "name": name,
                "passed": False,
                "error": str(e),
            })

    # Overall efficiency
    if total_theoretical > 0 and total_comparisons > 0:
        overall_efficiency = min(1.0, total_theoretical / total_comparisons)
    else:
        overall_efficiency = 0.0

    return {
        "score": round(total_score, 4),
        "overall_efficiency": round(overall_efficiency, 4),
        "total_comparisons": total_comparisons,
        "total_theoretical": round(total_theoretical, 1),
        "passed": all(r.get("passed", False) for r in results),
        "details": results,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: benchmark.py <solution.py>"}))
        sys.exit(1)

    result = run_benchmark(sys.argv[1])
    print(json.dumps(result, indent=2))
